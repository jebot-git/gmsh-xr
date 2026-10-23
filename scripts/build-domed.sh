#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
prefix="${DOME_FLTK_PREFIX:-/opt/fltk-vr/toolkit}"
cmake -S "$root" -B "$root/build-domed" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -march=native' \
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -march=native' \
  -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
  -DCMAKE_BUILD_RPATH="$prefix/lib" \
  -DCMAKE_INSTALL_RPATH="$prefix/lib" \
  -DCMAKE_PREFIX_PATH="$prefix" \
  -DFLTK_CONFIG_SCRIPT="$prefix/bin/fltk-config" \
  -DENABLE_DOME_XR=ON -DENABLE_TESTS=ON -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build "$root/build-domed" --parallel "${BUILD_JOBS:-8}"
ctest --test-dir "$root/build-domed" -R '^dome-stereo$' --output-on-failure
