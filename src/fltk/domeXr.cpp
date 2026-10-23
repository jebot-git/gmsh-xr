// SPDX-License-Identifier: GPL-2.0-or-later
// Gmsh's model stays in this process; DomeD owns OpenXR and per-eye composition.
#include "domeXr.h"
#include "domeDesktop.h"
#include "FlGui.h"
#include "openglWindow.h"
#include "graphicWindow.h"
#include "Context.h"
#include "GmshMessage.h"
#include <FL/Fl.H>
#include <FL/Fl_Gl_Window.H>
#include <FL/platform.H>
#include <FL/gl.h>
#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <unistd.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <vector>

namespace domeXr {
bool requested = false;
std::string capture;
namespace {
using Json = nlohmann::json;
const char *appId = "org.gmsh.Sbs";

int socketOwner(const std::string &path)
{
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  if(path.size() >= sizeof(address.sun_path)) throw std::runtime_error("Wayland socket path is too long");
  std::copy(path.begin(), path.end(), address.sun_path);
  int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if(fd < 0) throw std::runtime_error("Cannot inspect the DomeD Wayland socket");
  ucred peer{};
  socklen_t size = sizeof(peer);
  int status = connect(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address));
  if(!status) status = getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size);
  close(fd);
  char exe[4096];
  const std::string link = "/proc/" + std::to_string(peer.pid) + "/exe";
  auto n = status ? -1 : readlink(link.c_str(), exe, sizeof(exe));
  std::string name = n > 0 ? std::string(exe, n) : "";
  const std::string deleted = " (deleted)";
  if(name.size() >= deleted.size() && name.compare(name.size() - deleted.size(), deleted.size(), deleted) == 0)
    name.resize(name.size() - deleted.size());
  if(status || peer.uid != getuid() || name.substr(name.find_last_of('/') + 1) != "dome-compositor")
    throw std::runtime_error("Open Gmsh inside your DomeD Wayland session first");
  return peer.pid;
}

size_t receive(char *data, size_t size, size_t count, void *target)
{
  auto &body = *static_cast<std::string *>(target);
  const size_t bytes = size * count;
  if(bytes > 4096 || body.size() > 4096 - bytes) return 0;
  body.append(data, bytes);
  return bytes;
}

void requireSession()
{
  if(!fl_wl_display()) throw std::runtime_error("DomeD XR requires Gmsh's native Wayland backend");
  const char *runtime = getenv("XDG_RUNTIME_DIR");
  const char *display = getenv("WAYLAND_DISPLAY");
  if(!runtime || !display || !*display) throw std::runtime_error("No DomeD session was found");
  auto path = [runtime](const std::string &name) {
    return !name.empty() && name[0] == '/' ? name : std::string(runtime) + '/' + name;
  };
  const std::string socket = path(display), record = socket + ".dome-session.json";
  const int pid = socketOwner(socket);
  struct stat info{};
  if(lstat(record.c_str(), &info) || !S_ISREG(info.st_mode) || info.st_uid != getuid() ||
     (info.st_mode & 0022) || info.st_size > 4096)
    throw std::runtime_error("Invalid DomeD session record");
  std::ifstream input(record);
  Json context; input >> context;
  if(context.at("version") != 1 || context.at("compositor_pid") != pid ||
     !context.at("control_port").is_number_unsigned())
    throw std::runtime_error("Invalid DomeD session identity");
  const auto port = context.at("control_port").get<unsigned>();
  const std::string xr = context.at("xr_socket").get<std::string>();
  if(!port || port > 65535 || xr.empty() || socketOwner(path(xr)) != pid)
    throw std::runtime_error("Invalid DomeD XR socket");
  std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl(curl_easy_init(), curl_easy_cleanup);
  if(!curl) throw std::runtime_error("Cannot initialize DomeD session query");
  const std::string url = "http://127.0.0.1:" + std::to_string(port) + "/api/integrations/gmsh";
  std::string body;
  curl_easy_setopt(curl.get(), CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl.get(), CURLOPT_PROXY, "");
  curl_easy_setopt(curl.get(), CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(curl.get(), CURLOPT_TIMEOUT_MS, 500L);
  curl_easy_setopt(curl.get(), CURLOPT_WRITEFUNCTION, receive);
  curl_easy_setopt(curl.get(), CURLOPT_WRITEDATA, &body);
  long code = 0;
  auto result = curl_easy_perform(curl.get());
  curl_easy_getinfo(curl.get(), CURLINFO_RESPONSE_CODE, &code);
  if(result != CURLE_OK || code != 200)
    throw std::runtime_error("This DomeD compositor needs the Gmsh XR integration update");
  Json status = Json::parse(body);
  if(status.at("version") != 1 || status.at("compositor_pid") != pid ||
     status.at("xr_socket") != xr || status.at("sbs_app_id") != appId)
    throw std::runtime_error("DomeD XR integration identity does not match");
  if(status.at("xr_active") != true) throw std::runtime_error("Start XR in DomeD before opening the stereo mesh view");
}

class MeshWindow : public Fl_Gl_Window {
  std::unique_ptr<Fl_Widget_Tracker> source;
  drawContext ctx;
  int lastX = 0, lastY = 0;
  double baseline = .06;
  bool captured = false;
  openglWindow *owner() const {
    return source && !source->deleted() ? static_cast<openglWindow *>(source->widget()) : nullptr;
  }
  void draw() override {
    auto original = owner();
    if(!original) { hide(); return; }
    if(!context_valid()) {
      VertexArray::invalidateBuffers();
      glApi::reset();
      glShader::reset();
      glImmediate::resetMatrices();
      if(CTX::instance()->shaders && !glShader::available() &&
         (mode() & FL_OPENGL3) && !glShader::wanted()) {
        Fl::add_timeout(0., [](void *) { domeXr::redraw(); });
        return;
      }
    }
    glShader::setContext(context());
    ctx.copyViewAttributes(original->getDrawContext());
    ctx.setHighResolutionPixelFactor(w() ? double(pixel_w()) / w() : 1.);
    drawContext::global()->setPixelFactor(ctx.highResolutionPixelFactor());
    ctx.domeStereoBaseline = baseline;
    ctx.viewport[0] = ctx.viewport[1] = 0;
    ctx.viewport[2] = w(); ctx.viewport[3] = h();
    const int eyeWidth = pixel_w() / 2, height = pixel_h();
    if(eyeWidth < 1 || height < 1) return;
    glDrawBuffer(GL_BACK);
    glDisable(GL_SCISSOR_TEST);
    glDepthMask(GL_TRUE);
    glClearColor(CTX::instance()->unpackRed(CTX::instance()->color.bg) / 255.f,
                 CTX::instance()->unpackGreen(CTX::instance()->color.bg) / 255.f,
                 CTX::instance()->unpackBlue(CTX::instance()->color.bg) / 255.f, 1);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_SCISSOR_TEST);
    for(int eye = 0; eye < 2; ++eye) {
      const int x = eye ? pixel_w() - eyeWidth : 0;
      glViewport(x, 0, eyeWidth, height);
      glScissor(x, 0, eyeWidth, height);
      glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
      ctx.domeStereoEye = eye ? 1 : -1;
      ctx.draw3d();
      // Deferred primitives must finish before the next eye changes the viewport.
      glImmediate::flush();
      drawContext::global()->flushString();
    }
    ctx.domeStereoEye = 0;
    glDisable(GL_SCISSOR_TEST);
    drawContext::global()->flushString();
    if(!capture.empty() && !captured) {
      captured = true;
      std::vector<unsigned char> pixels(size_t(pixel_w()) * height * 3);
      glPixelStorei(GL_PACK_ALIGNMENT, 1);
      glReadBuffer(GL_BACK);
      glReadPixels(0, 0, pixel_w(), height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
      std::ofstream out(capture, std::ios::binary);
      out << "P6\n" << pixel_w() << ' ' << height << "\n255\n";
      for(int y = height - 1; y >= 0; --y)
        out.write(reinterpret_cast<char *>(pixels.data() + size_t(y) * pixel_w() * 3), size_t(pixel_w()) * 3);
      if(!out) { fprintf(stderr, "Cannot write stereo capture\n"); std::exit(1); }
      out.close();
      Fl::add_timeout(.1, [](void *) { FlGui::destroy(); std::exit(0); });
    }
  }
  int handle(int event) override {
    auto original = owner();
    if(!original) return Fl_Gl_Window::handle(event);
    auto view = original->getDrawContext();
    if(event == FL_FOCUS || event == FL_UNFOCUS) return 1;
    if(event == FL_PUSH) { take_focus(); lastX = Fl::event_x(); lastY = Fl::event_y(); return 1; }
    if(event == FL_DRAG) {
      const double dx = double(Fl::event_x() - lastX) / std::max(1, w());
      const double dy = double(Fl::event_y() - lastY) / std::max(1, h());
      if(Fl::event_state(FL_BUTTON1) && !Fl::event_state(FL_SHIFT)) {
        // Use Gmsh's native trackball path, including its camera-mode adapter.
        if(CTX::instance()->useTrackball || CTX::instance()->camera)
          view->addQuaternion(0., 0., 2. * dx, -2. * dy);
        else {
          view->r[0] += dy * 180.;
          view->r[1] += dx * 180.;
        }
      }
      else if(CTX::instance()->camera) {
        if(!view->camera.on) view->camera.init();
        double horizontal = -2. * dx, vertical = 2. * dy;
        view->camera.moveRight(horizontal); view->camera.moveUp(vertical);
      }
      else {
        double scale = std::max(CTX::instance()->lc, 1.e-12) * 2.;
        view->t[0] += dx * scale / std::max(view->s[0], 1.e-12);
        view->t[1] -= dy * scale / std::max(view->s[1], 1.e-12);
      }
      lastX = Fl::event_x(); lastY = Fl::event_y();
      drawContext::global()->draw(false); redraw(); return 1;
    }
    if(event == FL_MOUSEWHEEL) {
      double factor = exp(-.1 * Fl::event_dy());
      if(CTX::instance()->camera) {
        if(!view->camera.on) view->camera.init();
        view->camera.zoom(factor);
      }
      else for(double &s : view->s) s = std::max(1.e-6, std::min(1.e6, s * factor));
      drawContext::global()->draw(false); redraw(); return 1;
    }
    if(event == FL_KEYDOWN || event == FL_SHORTCUT) {
      if(Fl::event_key() == FL_Escape) { hide(); return 1; }
      // Leave Gmsh shortcuts (including 0 = reload) and DomeD's configured
      // chords to their normal handlers. Stereo controls live in the real menu.
      return Fl_Gl_Window::handle(event);
    }
    return Fl_Gl_Window::handle(event);
  }
public:
  explicit MeshWindow(openglWindow *original)
    : Fl_Gl_Window(1280, 800, "Gmsh — DomeD XR mesh"), source(new Fl_Widget_Tracker(original))
  {
    syncMode();
    xclass(appId);
    end();
    resizable(this);
    size_range(320, 200);
    callback([](Fl_Widget *w, void *) { static_cast<Fl_Window *>(w)->hide(); });
  }
  void separation(int action) {
    baseline = action == 0 ? 0. : action == 2 ? .06 :
      std::max(0., std::min(.2, baseline + .01 * action));
    redraw();
  }
  void syncMode() {
    const int flags = FL_RGB | FL_DOUBLE | FL_DEPTH |
                      (glShader::wanted() ? FL_OPENGL3 : 0);
    if(mode() != flags) mode(flags);
  }
  ~MeshWindow() { domeDesktop::detach(*this); if(context()) { make_current(); ctx.invalidateBgImageTexture(); } }
};
std::unique_ptr<MeshWindow> window;
}

void toggle()
{
  if(window && window->shown()) { window->hide(); return; }
  try {
    if(capture.empty()) requireSession();
    auto source = FlGui::instance()->getCurrentOpenglWindow();
    if(!source) throw std::runtime_error("Open a Gmsh mesh view first");
    Fl_Group::current(nullptr);
    window.reset(new MeshWindow(source));
    for(auto graph : FlGui::instance()->graph) {
      if(graph->getMenuBar()) {
        domeDesktop::attach(*window, *graph->getMenuBar());
        break;
      }
    }
    window->show();
    window->redraw();
  }
  catch(const std::exception &e) { Msg::Error("DomeD XR: %s", e.what()); }
}
void separation(int action) { if(window) window->separation(action); }
void redraw() {
  if(window && window->shown()) {
    window->syncMode();
    window->redraw();
  }
}
void start() { if(requested || !capture.empty()) toggle(); }
void shutdown() { window.reset(); }
}
