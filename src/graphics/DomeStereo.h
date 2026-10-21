// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef GMSH_DOME_STEREO_H
#define GMSH_DOME_STEREO_H
#include <cmath>
#include <stdexcept>

namespace domeStereo {
struct Frustum {
  double left, right, bottom, top, nearPlane, farPlane, eye;
};
// Parallel cameras with asymmetric frusta: the convergence plane has zero
// disparity. No toe-in, vertical disparity, or quad-buffer GL is required.
inline Frustum frustum(double aspect, double nearPlane, double farPlane,
                       double convergence, double halfHeight, double eye)
{
  if(!std::isfinite(aspect) || !std::isfinite(eye) ||
     !std::isfinite(nearPlane) || !std::isfinite(farPlane) ||
     !std::isfinite(convergence) || !std::isfinite(halfHeight) ||
     aspect <= 0 || nearPlane <= 0 || farPlane <= nearPlane ||
     convergence <= nearPlane || halfHeight <= 0)
    throw std::invalid_argument("Invalid DomeD stereo frustum");
  const double top = halfHeight * nearPlane / convergence;
  const double shift = -eye * nearPlane / convergence;
  return {-top * aspect + shift, top * aspect + shift, -top, top,
          nearPlane, farPlane, eye};
}
}
#endif
