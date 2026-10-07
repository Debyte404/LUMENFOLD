// bench_main.cpp — real timing for the caustic baker.
// Separates the geometric quadrature (one deterministic pass) from the wave
// (Airy) correction, so the demo HUD and the paper can quote a cost split
// rather than a single opaque number.
//
//   bench [iterations]
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "caustic.hpp"

int main(int argc, char** argv) {
  int iters = argc > 1 ? std::atoi(argv[1]) : 5;
  if (iters < 1) iters = 1;
  caust::WaterParams wp;
  const int sizes[] = {256, 512, 1024, 2048};
  const float t = 1.7f;
  std::printf("caustic bake timing (best of %d, t=%.1f, airy_scale=1.0)\n", iters, t);
  std::printf("%6s %10s %10s %10s %12s\n", "grid", "geom_ms", "wave_ms", "total_ms", "Msplats/s");
  for (int s : sizes) {
    double bg = 1e18, bw = 1e18;
    for (int i = 0; i < iters; i++) {
      auto t0 = std::chrono::steady_clock::now();
      auto g = caust::bake(s, s, t, wp, true, 1.0f);
      auto t1 = std::chrono::steady_clock::now();
      auto w = caust::bake(s, s, t, wp, false, 1.0f);
      auto t2 = std::chrono::steady_clock::now();
      bg = std::min(bg, std::chrono::duration<double, std::milli>(t1 - t0).count());
      bw = std::min(bw, std::chrono::duration<double, std::milli>(t2 - t1).count());
      volatile float sink = g[0] + w[0];
      (void)sink;
    }
    double cells = double(s) * double(s);
    std::printf("%6d %10.2f %10.2f %10.2f %12.1f\n", s, bg, bw, bg + bw,
                cells / ((bg + bw) / 1000.0) / 1e6);
  }
  return 0;
}
