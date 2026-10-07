// main.cpp — headless stepping: MuJoCo scene + two_medium forces (stage 1).
// Filament viewer lands in stage 2; this binary proves the physics first.
#include <cstdio>
#ifdef HAVE_MUJOCO
#include <mujoco/mujoco.h>
#endif
#include "two_medium.hpp"

int main() {
  twomed::Env env;
  twomed::Body sphere{twomed::Shape::Sphere, {0.15, 0, 0}, 14.137167, {0, 0, -0.4}};
  auto w = twomed::archimedes(sphere, env);
  std::printf("sphere Vsub=%.7f m^3 F=%.3f N (expect ~138.7)\n", w.submerged_volume, w.F[2]);
#ifdef HAVE_MUJOCO
  std::printf("mujoco headers linked.\n");
#else
  std::printf("built without mujoco headers (physics lib only).\n");
#endif
  return 0;
}
