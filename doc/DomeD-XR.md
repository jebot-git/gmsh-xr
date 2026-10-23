# Gmsh in DomeD XR

This checkout merges upstream master `c020e8f438f8a6dfc674f440ded2030f59d8d502`
(2026-10-18, Gmsh 5.0 development) from the
[official repository](https://gitlab.onelab.info/gmsh/gmsh). It uses DomeD's installed
patched FLTK 1.4.5; it does not use a Qt frontend or create a second OpenXR session.

Run `bash scripts/build-domed.sh` to build with `-O3`, native CPU tuning and LTO.
The default toolkit location is `/opt/fltk-vr/toolkit`; set `DOME_FLTK_PREFIX`
to use a different installation of the same patched toolkit. OpenCASCADE
development files enable CAD imports and meshing alongside native `.geo` and
`.msh` support. The Linux XR integration also requires libcurl, Cairo and
nlohmann JSON, GIO, Wayland, X11 and Fontconfig development files, plus
`wayland-scanner`. Set `ENABLE_DOME_XR=OFF` for an ordinary build.

## Use

In a DomeD Wayland session, start XR using DomeD's normal controls. Open a mesh
in Gmsh and choose **Window → DomeD XR Mesh** (`Ctrl+Shift+X`). The same command
closes the view. Alternatively:

```sh
gmsh-dome-xr mesh.msh
# Directly from this checkout:
./build-domed/gmsh mesh.msh -dome-xr
```

The ordinary Gmsh GUI stays on the desktop. Its additional mesh-only window is
visible only in XR; it shares the live model, visibility options and source view
transform. New meshes, model edits, view changes and post-processing updates are
redrawn through Gmsh's normal render notifications. No model export or image
conversion worker is involved. Use Gmsh's ordinary GUI for entity selection,
editing, meshing and option changes.

In the XR view:

- Left-drag rotates the source view; Shift-left-drag or another mouse button pans.
- The wheel zooms. These gestures update the ordinary source view too.
- **Window → XR Eye Separation** adjusts, resets or zeroes separation.
  Gmsh retains its ordinary keyboard shortcuts, including `0` for reload.
- Escape or the window close control closes only the XR view.

The initial total baseline is 6% of the model bounding diagonal. Parallel
off-axis views converge at 2.5 model diagonals in trackball/Euler mode, or at
the existing camera's focal distance in camera mode. The render uses a squeezed
left/right SBS texture with a full-window logical aspect ratio; DomeD expands
each half into the corresponding eye. It is a stereo model-inspection panel,
not a head-tracked or room-scale CAD camera. Head tracking places the panel
through DomeD; it does not change Gmsh's model camera.

## Menus, appearance and keybindings

Both the desktop GUI and XR mesh surface export the same live native menu tree
to DomeD's universal menu over DBusMenu and the Wayland appmenu protocol. Recent
files, enabled states, accelerators and callbacks come from Gmsh's own menu.
DomeD supplies its standard missing categories and window actions. The in-window
bar collapses and its space is reclaimed while DomeD's universal-menu host and
window association are available. Native shortcuts stay active. The bar returns
if the host disappears, and remains available on other desktops. Desktop and XR
surfaces share this state, so closing the XR view cannot restore a duplicate bar.

Inside DomeD, the UI follows live light/dark, accent and bitmap font/strike
settings from `dome/appearance.json`, including dialogs, text and model-tree
widgets. Mesh background, scientific colors and explicit plot fonts remain model
settings. No Gmsh preferences are rewritten. Outside DomeD the normal Gmsh UI
settings apply.

DomeD handles its user-configured session shortcuts before client delivery.
Gmsh's native shortcuts remain active in the XR view; separation controls do not
claim bare `0`, `+` or `-`. Escape closes only the XR view.

## DomeD integration

The companion changes in `../DomeD` recognize `org.gmsh.Sbs`, mark the view XR-only
when that identity first appears, and expose `GET /api/integrations/gmsh` with
the existing version-1 stereo integration contract. Later user presentation
changes are retained. Both Gmsh windows use the caller's existing native Wayland
connection. Session discovery checks the socket owner's UID/PID, the private
per-socket session record and the integration response, and accepts a still-running
compositor whose executable was replaced during an update.

An inactive XR session, a different compositor or an older DomeD without the
integration reports an error and leaves the desktop GUI running. After updating
DomeD, start a new DomeD session; installations do not restart an active desktop.

## Validation

```sh
ctest --test-dir build-domed -R '^dome-stereo$' --output-on-failure
uv run --with pillow --with python-xlib --with dbus-next python scripts/test-domed-xr.py
uv run --with pillow --with python-xlib --with dbus-next python scripts/test-domed-menu.py
```

The integration test uses private Xvfb/D-Bus/DomeD instances and a simulated XR
heartbeat. It generates a real tetrahedral mesh, checks rendered eye disparity
in both shader and legacy OpenGL pipelines, including camera mode, and checks
native Wayland routing, GPU DMA-BUF export, mouse rotation, universal menu
callbacks, live appearance, native shortcuts, remapped session shortcuts and view
lifetime.
It does not exercise physical-headset output or claim a real OpenXR lifecycle.
Logs, JSON results and captures are written to `artifacts/domexr/`.

For a standalone render capture without an XR session:

```sh
./build-domed/gmsh mesh.msh -dome-xr-capture stereo.ppm
```

CPU readback is used only for explicit QA captures; normal presentation renders
the live geometry directly with OpenGL and uses DomeD's native surface transport.
