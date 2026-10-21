// SPDX-License-Identifier: GPL-2.0-or-later
#include "DomeStereo.h"
#include <iostream>
#include <cmath>

double project(const domeStereo::Frustum &f, double x, double z)
{
  return 2. * f.nearPlane * (x - f.eye) / (-z * (f.right - f.left)) -
         (f.right + f.left) / (f.right - f.left);
}
int main()
{
  const auto left = domeStereo::frustum(1.6, .01, 100., 2.5, 1., -.03);
  const auto right = domeStereo::frustum(1.6, .01, 100., 2.5, 1., .03);
  auto disparity = [&](double z) { return project(left, .2, z) - project(right, .2, z); };
  if(std::abs(disparity(-2.5)) > 1.e-12 || disparity(-1.) <= 0 || disparity(-5.) >= 0) return 1;
  if(left.bottom != right.bottom || left.top != right.top || left.eye >= right.eye) return 2;
  for(double aspect : {0.5, 1., 1.6, 3.2}) {
    auto l = domeStereo::frustum(aspect, .01, 100., 2.5, 1., 0.);
    auto r = domeStereo::frustum(aspect, .01, 100., 2.5, 1., 0.);
    if(project(l, .5, -1.) != project(r, .5, -1.)) return 3;
  }
  try { domeStereo::frustum(0., .01, 100., 2.5, 1., .03); return 4; }
  catch(const std::invalid_argument &) {}
  std::cout << "Stereo convergence, disparity sign, parallel vertical frusta and zero baseline passed\n";
}
