// SPDX-License-Identifier: GPL-2.0-or-later
#include "../domeDesktop.h"
#include "appearance.h"
#include "desktop-menu.h"
#include <FL/Fl_Menu_Bar.H>
#include <map>
namespace domeDesktop {
namespace {
struct Export {
  Fl_Menu_Bar *bar;
  std::unique_ptr<DesktopMenu> menu;
};
std::map<Fl_Window *, Export> exports;
bool initialized = false;
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
  exports.emplace(&window, Export{&bar, std::make_unique<DesktopMenu>(window, bar)});
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
