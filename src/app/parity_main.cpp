// parity_main.cpp — C++/Python parity harness (not shipped).
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include "caustic.hpp"
int main(int argc, char** argv) {
  int N = argc > 1 ? std::atoi(argv[1]) : 128;
  float t = argc > 2 ? float(std::atof(argv[2])) : 1.7f;
  float as = argc > 3 ? float(std::atof(argv[3])) : 0.02f;
  caust::WaterParams wp;
  auto g = caust::bake(N, N, t, wp, true, as);
  auto w = caust::bake(N, N, t, wp, false, as);
  double gmax = 0, gsum = 0;
  for (float v : g) {
    gmax = v > gmax ? v : gmax;
    gsum += v;
  }
  double wsum[3] = {0, 0, 0};
  double wmax[3] = {0, 0, 0};
  for (int i = 0; i < N * N; i++)
    for (int c = 0; c < 3; c++) {
      double v = w[(i * 3) + c];
      wsum[c] += v;
      if (v > wmax[c]) wmax[c] = v;
    }
  std::FILE* f = std::fopen(argv[4], "wb");
  std::fwrite(w.data(), sizeof(float), w.size(), f);
  std::fclose(f);
  std::printf("geom_peak=%.2f geom_mean=%.4f\n", gmax, gsum / (N * N));
  std::printf("wave_peak=%.2f,%.2f,%.2f flux=%.4f,%.4f,%.4f\n", wmax[0], wmax[1], wmax[2],
              wsum[0] / gsum, wsum[1] / gsum, wsum[2] / gsum);
  return 0;
}
