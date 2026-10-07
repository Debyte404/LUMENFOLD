# Caustics — wave-corrected caustics over a two-medium MuJoCo scene, rendered in Filament
Status: early scaffold (2026-10-04). Decisions locked: upstream Filament 1a, Airy caustics 3a,
MuJoCo role = issue #3452 (two-medium air/water physics).

## What this is
A real-time demo + reusable modules:
1. `src/physics/two_medium` — air/water interface with REAL buoyancy (submerged-volume
   force applied at the center of buoyancy, so the restoring moment exists).
   This fills the gap filed as google-deepmind/mujoco#3452, which was closed
   unmerged: MuJoCo 3.14.0 (checked: no `nlayer`/`mj_envLayer` in headers) still
   has one global density, no free surface, no Archimedes force, and a `gravcomp`
   proxy whose torque cancels identically (hull can never self-right).
2. `src/render/caustic` — analytic caustic texture with wave-corrected Airy
   fringe profile (finite focus, no blown-out infinity), consumed by a custom
   Filament material. Per prior viability study (Sebastian-Engine
   docs/WAVE_VIABILITY.md): no shipping renderer does Airy/Pearcey-regularized
   caustics — that is the novelty.
3. `src/app` — Filament viewer stepping the MuJoCo scene (pool + floating bodies).

## Layout
- `third_party/` — prebuilt drops (fetch via `tools/fetch_third_party.sh`):
  mujoco-3.14.0-windows, filament-v1.77.2-windows. NOT committed (see .gitignore).
- `models/` — MJCF scenes (`pool.xml`, bodies).
- `tools/` — Python proofs: `repro_3452.py`, `two_medium_demo.py`, `airy_caustic.py`.
- `src/physics`, `src/render`, `src/app` — C++ (MSVC 14.41, CMake 4.4).
- `docs/` — DESIGN.md (architecture), WAVE_VIABILITY.md (prior study, copied).

## Build (once third_party is in place)
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
./build/src/app/Release/caustics_demo.exe

## Physics scope (honest)
Static flat free surface at z=0, hydrostatics only: no waves/currents/sloshing
(same out-of-scope list as #3452's Limits). Sphere + box + capsule analytic
clipping (exact); concave meshes fall back to convex-hull approx, documented.
MuJoCo's own drag (fluidshape) stays on; we add ONLY the missing Archimedes
term + its moment, as external `xfrc_applied`.
