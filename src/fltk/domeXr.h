// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef GMSH_DOME_XR_H
#define GMSH_DOME_XR_H
#include <string>
namespace domeXr {
extern bool requested;
extern std::string capture;
void toggle();
void separation(int action);
void redraw();
void start();
void shutdown();
}
#endif
