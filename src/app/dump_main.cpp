// dump_main.cpp — parity bisect harness: dumps geometric + wave fields to .bin
#include <cstdio>
#include <cstdlib>
#include "caustic.hpp"
int main(int argc, char** argv) {
  int N = std::atoi(argv[1]);
  float t = float(std::atof(argv[2]));
  float as = float(std::atof(argv[3]));
  caust::WaterParams wp;
  auto g = caust::bake(N, N, t, wp, true, as);
  auto w = caust::bake(N, N, t, wp, false, as);
  std::FILE* f = std::fopen(argv[4], "wb");
  std::fwrite(g.data(), sizeof(float), g.size(), f);
  std::fclose(f);
  f = std::fopen(argv[5], "wb");
  std::fwrite(w.data(), sizeof(float), w.size(), f);
  std::fclose(f);
  return 0;
}
