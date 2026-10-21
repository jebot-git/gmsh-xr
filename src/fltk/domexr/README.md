The MIT-licensed appearance.h, desktop-menu.{h,cpp,cmake} and appmenu.xml
are shared de-xr FLTK integration sources copied from qimgvr/fltk in this
workspace (fltk-vr snapshot 0a7e2a1). Keep them aligned with the shared
implementation. domeDesktop.cpp bridges the C++17 appearance helper to
Gmsh's C++14 frontend. Native menus use Gmsh's original Fl_Menu_Item tree
and callbacks, including dynamic recent files and shortcut metadata.

Local appearance extensions style FLTK tree items and text displays, and emit
optional DX_APPEARANCE diagnostics when DE_XR_APPEARANCE_TRACE is set.
