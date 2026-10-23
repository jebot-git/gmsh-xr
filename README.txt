This is Gmsh, an automatic three-dimensional finite element mesh generator with
built-in pre- and post-processing facilities.

Gmsh is copyright (C) 1997-2026 C. Geuzaine and J.-F. Remacle, and is
distributed under the terms of the GNU General Public License, Version 2 or
later, with an exception to allow for easier linking with external
libraries. See LICENSE.txt and CREDITS.txt for more information.

See the doc/ and tutorials/ directories for documentation and tutorials. The
reference manual is located in doc/texinfo/. See the examples/ directory and the
web site https://gmsh.info for additional examples.

Building Gmsh from source code requires a C++ compiler and CMake
(http://cmake.org). Building the graphical user interface requires FLTK 1.3.3 or
higher on Windows and Linux, and FLTK 1.4.0 or higher on macOS
(http://fltk.org), configured with OpenGL support. Support for boolean
operations, constructive solid geometry features and STEP file import requires
OpenCASCADE 6.9 or higher (version 7.2 or higher is highly recommended;
http://www.opencascade.com). Step-by-step compilation instructions are available
on the Gmsh wiki: https://gitlab.onelab.info/gmsh/gmsh/-/wikis/Gmsh-compilation.


Build Gmsh from the command line
--------------------------------

* Create a build directory, for example as a subdirectory of Gmsh's source
  directory:

    mkdir build

* To build the monolithic Gmsh app with the default build options, run cmake
  from within the build directory, pointing to Gmsh's source directory, then run
  "make"

    cd build
    cmake ..
    make

  Optionally running

    make install

  will install the Gmsh app in the standard system location (controlled by
  CMAKE_INSTALL_PREFIX - see below).

* To build the Gmsh app dynamically linked to the shared Gmsh library, which can
  then also be used by external codes through the C++, C, Python, Julia and
  Fortran Gmsh API, run

    cd build
    cmake -DENABLE_BUILD_DYNAMIC=1 ..
    make
    make install

  This will install the Gmsh app and the shared Gmsh library, as well as the C++
  and C include files, and the Python, Julia and Fortran modules.

* The JavaScript Gmsh API needs Gmsh compiled to WebAssembly with Emscripten:
  see utils/wasm/README.txt.

* To change build options you can use "ccmake" instead of "cmake", e.g.:

    ccmake ..

  or you can specify options directly on the command line. For example, you can
  use

    cmake -DCMAKE_PREFIX_PATH=/opt/local ..

  to specify the location of external packages installed in non-standard
  directories. You can use

    cmake -DCMAKE_INSTALL_PREFIX=/opt

  to change the installation directory. Or you could use

    cmake -DENABLE_FLTK=0 ..

  to build a version of Gmsh without the FLTK graphical interface. The list of
  all available configuration options is given in the reference manual.

* To see a detailed compilation log use

    make VERBOSE=1


Build Gmsh using CMake's graphical user interface
-------------------------------------------------

* Launch CMake and fill-in the two top input fields (telling where the Gmsh
  source directory is located and where you want the Gmsh binary to be created).

* Click on "Add entry" and define the variable CMAKE_PREFIX_PATH, of type
  "PATH", pointing to the location(s) of any external package(s) (FLTK,
  BLAS/LAPACK, etc.) installed in non-standard directories.

* Click on "Configure" and choose your compiler.

* Optionally change some configuration options (re-run "Configure" every time
  you change some options).

* Once you are happy with all the configuration options, click on "Generate".

* Go to the build directory and build Gmsh using your chosen compiler.


DomeD / de-xr FLTK fork
-----------------------

The preceding text is the upstream Gmsh README. This fork adds a Linux FLTK
stereo mesh view and native DomeD desktop integration; Gmsh's geometry, meshing,
post-processing, file formats and APIs remain those described above.

The maintained fork build is FLTK-based. scripts/build-domed.sh selects the
patched toolkit at /opt/fltk-vr/toolkit by default (override DOME_FLTK_PREFIX).
It configures an optimized CMake Release build with interprocedural optimization
and local CPU tuning, builds build-domed/gmsh, then runs the dome-stereo test.
Its -march=native artifacts target the build machine's CPU. Build as a regular
user. Additional Dome integration dependencies include libcurl, Cairo,
Fontconfig, nlohmann-json and the GIO/Wayland native-menu build dependencies.
The upstream optional geometry/solver dependencies still apply.

    ./scripts/build-domed.sh
    ./build-domed/gmsh -help
    ./build-domed/gmsh tutorials/t1.geo -dome-xr

ENABLE_DOME_XR defaults to ON, but the integration is compiled only with FLTK
on Linux. For a conventional build without it, configure -DENABLE_DOME_XR=OFF.
Use the patched FLTK for the Dome fork rather than relying on an arbitrary
system FLTK found first by CMake.

In a native Wayland Gmsh window inside an already active DomeD XR session,
Window -> DomeD XR Mesh (Ctrl+Shift+X), or -dome-xr on the command line, opens
the current model's stereo view. DomeD must provide its matching Gmsh integration
endpoint and session record. Gmsh does not start a compositor or separate XR
runtime. The universal menu exports the existing FLTK commands; the desktop
bridge follows DomeD's live appearance settings, including bitmap fonts.

In the stereo window, left-drag rotates; Shift+left-drag or another drag pans;
the mouse wheel zooms. Escape closes this view. Window -> XR Eye Separation
provides Increase, Decrease, Zero Separation and Default Separation. Existing
Gmsh shortcuts are left to their normal handlers.

The QA-only -dome-xr-capture FILE.ppm writes a stereo framebuffer and exits.
It bypasses the active-session check, so no headset is needed, but still requires
a working graphical/OpenGL environment. It is not a headless rendering option.

    ./build-domed/gmsh tutorials/t1.geo -dome-xr-capture /tmp/gmsh-stereo.ppm
    man -l doc/gmsh.1

For staging only, after a successful build:

    DESTDIR="$PWD/stage" cmake --install build-domed --strip

Inspect the staged files before any system installation. scripts/stage-domed.py
is a broader integration staging tool: it requires the existing
/opt/fltk-vr/install-manifest.json and sibling DomeD release artifacts. It is
not a standalone Gmsh installer. None of these commands requires restarting
an active desktop or display manager.

See src/fltk/domexr/README.md for the shared appearance/menu bridge and
scripts/test-domed-xr.py for the isolated compositor/rendering test harness.
The installed gmsh(1) page is sourced from doc/gmsh.1 and now includes these
fork-specific display options. Upstream Texinfo documentation remains intact.
