// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
class Fl_Window;
class Fl_Menu_Bar;
namespace domeDesktop {
bool active();
void init();
void shutdown();
void appearance();
void attach(Fl_Window &, Fl_Menu_Bar &);
void detach(Fl_Window &);
int fontSize();
}
