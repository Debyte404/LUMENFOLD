// two_medium.hpp — air/water interface forces (fills mujoco#3452 gap).
// MuJoCo 3.14.0 has NO free surface / Archimedes term; we add it as external
// forces (d->xfrc_applied). Scope: static flat surface z=0, hydrostatics only.
#pragma once
#include <array>

namespace twomed {

// Environment: air above z=0, water below. SI units.
struct Env {
  double surface_z = 0.0;     // free surface height (static, flat)
  double rho_air = 1.225;     // kg/m^3
  double rho_water = 1000.0;  // kg/m^3
  double g = 9.81;            // m/s^2
};

// Supported analytic shapes for exact submerged-volume clipping.
enum class Shape { Sphere, Box, Capsule };

// Rigid body description (pose + shape + mass distribution).
struct Body {
  Shape shape;
  // Sphere: p[0]=radius. Box: p=half extents (x,y,z). Capsule: p[0]=radius, p[1]=half length (cylinder part).
  std::array<double, 3> p{};
  double mass = 1.0;
  // Pose: position of COM, rotation matrix (row-major 3x3).
  std::array<double, 3> x{0, 0, 0};
  std::array<double, 9> R{1, 0, 0, 0, 1, 0, 0, 0, 1};
  // Center of buoyancy is COMPUTED (not at COM) -> restoring moment exists.
};

// Result: force (world frame, Newtons) + torque about COM (N m).
struct Wrench {
  std::array<double, 3> F{0, 0, 0};
  std::array<double, 3> T{0, 0, 0};
  double submerged_volume = 0.0;  // m^3
  std::array<double, 3> cob{0, 0, 0};  // center of buoyancy, world frame
};

// Exact (sphere/box/capsule) submerged volume + centroid below surface_z.
Wrench archimedes(const Body& b, const Env& e);

// Convenience: neutral-buoyancy mass for a fully submerged shape of volume V.
inline double neutral_mass(double volume, const Env& e) { return e.rho_water * volume; }

}  // namespace twomed
