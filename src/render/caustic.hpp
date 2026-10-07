// caustic.hpp — analytic pool-caustic field with Airy wave correction.
// v1: CPU texture baker (float field -> RGB). Filament material in materials/.
#pragma once
#include <cstdint>
#include <vector>

namespace caust {

// Parameters of the animated water heightfield (sum of directional waves).
struct WaterParams {
  int n_waves = 4;
  float amp[4] = {0.035f, 0.022f, 0.014f, 0.008f};
  float wavelength[4] = {1.4f, 0.7f, 0.35f, 0.18f};
  float dirx[4] = {1, 0.3f, -0.6f, 0.8f};
  float diry[4] = {0.2f, 1, 0.8f, -0.6f};
  float speed[4] = {0.9f, 1.3f, 1.7f, 2.2f};
};

// Bake a W×H caustic field at time t.
// geometric_only=true -> returns W*H floats (mean=1).
// geometric_only=false -> returns W*H*3 interleaved RGB floats, flux-conserved.
// airy_scale sets the Airy fringe width in metres. Keep it so the band spans at
// least ~3 pixels (>= 0.018 at 1024^2 over a 6 m patch) or the fringe structure
// is unresolvable; and note that colour visibility FALLS as the band widens
// (measured: 10% per-channel spread at 0.02, 0.6% at 0.08). The default used to
// be 1.0, which silently produced both an unresolvable band and monochrome
// caustics - see docs/EVIDENCE.md §1 and tools/dispersion_scale.py.
std::vector<float> bake(int W, int H, float t, const WaterParams& wp, bool geometric_only,
                        float airy_scale = 0.02f);

// Map interleaved RGB float field to 8-bit sRGB.
std::vector<uint8_t> tonemap(const std::vector<float>& field);

}  // namespace caust
