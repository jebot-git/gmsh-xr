// SPDX-License-Identifier: GPL-2.0-or-later
#include "../domeDesktop.h"
#include "appearance.h"
#include "desktop-menu.h"
#include <FL/Fl_Menu_Bar.H>
#include <map>
namespace domeDesktop {
namespace {
class DomeMenuBar : public Fl_Menu_Bar {
  bool external = false;
  int localHeight;
  void draw() override { if(!external) Fl_Menu_Bar::draw(); }
public:
  std::function<void(int)> layoutChanged;
  DomeMenuBar(int x, int y, int w, int h)
    : Fl_Menu_Bar(x, y, w, h), localHeight(h) {}
  int reclaimedHeight() const { return localHeight - h(); }
  void universal(bool value) {
    if(value == external) return;
    const int previousHeight = h();
    external = value;
    resize(x(), y(), w(), value ? 0 : localHeight);
    if(layoutChanged) layoutChanged(previousHeight - h());
    if(window()) window()->redraw();
    if(getenv("DE_XR_APPEARANCE_TRACE"))
      fprintf(stderr, "DX_UNIVERSAL_MENU external=%d height=%d\n", external, h());
  }
  int handle(int event) override {
    if(external) return event == FL_SHORTCUT ? test_shortcut() != nullptr : 0;
    return Fl_Menu_Bar::handle(event);
  }
};
struct Export {
  Fl_Menu_Bar *bar;
  std::unique_ptr<DesktopMenu> menu;
};
std::map<Fl_Window *, Export> exports;
bool initialized = false;
void updateMenu(Fl_Menu_Bar &bar) {
  if(auto local = dynamic_cast<DomeMenuBar *>(&bar)) {
    bool available = false;
    // The desktop and XR surfaces export the same command tree. Closing or
    // hiding either one must not undo the other's working menu association.
    for(auto &entry : exports)
      if(entry.second.bar == &bar && entry.second.menu->universalAvailable())
        available = true;
    local->universal(available);
  }
}
}
Fl_Menu_Bar *createMenuBar(int x, int y, int width, int height) {
  return new DomeMenuBar(x, y, width, height);
}
void menuLayout(Fl_Menu_Bar &bar, std::function<void(int)> changed) {
  if(auto local = dynamic_cast<DomeMenuBar *>(&bar)) {
    local->layoutChanged = std::move(changed);
    if(local->reclaimedHeight() && local->layoutChanged)
      local->layoutChanged(local->reclaimedHeight());
  }
}
bool active() { return dx::dome(); }
void init() {
  if(initialized || !active()) return;
  initialized = true;
  dx::init();
}
void appearance() {
  if(!active()) return;
  // Gmsh reapplies its own palette after opening the display and in Options.
  // Session appearance wins without changing any saved Gmsh preferences.
  dx::last.clear();
  dx::appearance();
}
int fontSize() { return active() ? dx::size : 0; }
void attach(Fl_Window &window, Fl_Menu_Bar &bar) {
  // Export outside Dome as well, for other desktops supporting DBusMenu.
  exports.erase(&window);
  exports.emplace(&window, Export{&bar, std::make_unique<DesktopMenu>(window, bar, [&bar] { updateMenu(bar); })});
  if(getenv("DE_XR_APPEARANCE_TRACE")) {
    auto &menu = exports.at(&window).menu;
    fprintf(stderr, "DX_MENU %s %s\n", menu->serviceName().c_str(), menu->objectPath().c_str());
  }
}
void detach(Fl_Window &window) {
  auto current = exports.find(&window);
  auto bar = current == exports.end() ? nullptr : current->second.bar;
  // The main window owns the shared menu used by its XR surface.
  for(auto i = exports.begin(); i != exports.end();) {
    if(i->first == &window || (bar && bar->window() == &window && i->second.bar == bar))
      i = exports.erase(i);
    else ++i;
  }
  if(bar) updateMenu(*bar);
}
void shutdown() {
  exports.clear();
  if(!initialized) return;
  Fl::remove_timeout(dx::poll);
  Fl::remove_check(dx::style_new_windows);
  if(Fl::event_dispatch() == dx::dispatch) Fl::event_dispatch(dx::previous_dispatch);
  dx::styled_windows.clear();
  initialized = false;
}
}
