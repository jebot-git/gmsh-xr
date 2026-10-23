// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <functional>
class Fl_Window;
class Fl_Menu_Bar;
namespace domeDesktop {
bool active();
void init();
void shutdown();
void appearance();
Fl_Menu_Bar *createMenuBar(int x, int y, int width, int height);
void menuLayout(Fl_Menu_Bar &, std::function<void(int)>);
void attach(Fl_Window &, Fl_Menu_Bar &);
void detach(Fl_Window &);
int fontSize();
}
