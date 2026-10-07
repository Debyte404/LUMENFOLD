#include <cstdio>
#include <cstdlib>
#include <vector>
#include <algorithm>
// Standalone test: compares our CDT (edt_squared, copied from caustic.cpp)
// against scipy's exact EDT. Run via: tools/edt_debug.py
static void edt_squared(const std::vector<char>& feat, int W, int H, std::vector<float>& out) {
  const float INF = 1e20f;
  std::vector<float> tmp(W * H, INF);
  int M = std::max(W, H);
  std::vector<float> f(M), d(M);
  std::vector<int> v(M);
  std::vector<float> z(M + 1);
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) f[x] = feat[y * W + x] ? 0.0f : INF;
    int k = 0; v[0] = 0; z[0] = -INF; z[1] = INF;
    for (int q = 1; q < W; q++) {
      float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      while (s <= z[k]) { k--; s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]); }
      k++; v[k] = q; z[k] = s; z[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < W; q++) { while (z[k + 1] < q) k++; float dd = float(q - v[k]); d[q] = dd * dd + f[v[k]]; }
    for (int x2 = 0; x2 < W; x2++) tmp[y * W + x2] = d[x2];
  }
  for (int x = 0; x < W; x++) {
    for (int y = 0; y < H; y++) f[y] = tmp[y * W + x];
    int k = 0; v[0] = 0; z[0] = -INF; z[1] = INF;
    for (int q = 1; q < H; q++) {
      float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      while (s <= z[k]) { k--; s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]); }
      k++; v[k] = q; z[k] = s; z[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < H; q++) { while (z[k + 1] < q) k++; float dd = float(q - v[k]); out[q * W + x] = dd * dd + f[v[k]]; }
  }
}
int main(int argc, char** argv) {
  int W = std::atoi(argv[1]), H = std::atoi(argv[2]);
  std::vector<char> feat(W * H);
  FILE* f = std::fopen(argv[3], "rb");
  std::fread(feat.data(), 1, W * H, f);
  std::fclose(f);
  std::vector<float> out(W * H);
  edt_squared(feat, W, H, out);
  f = std::fopen(argv[4], "wb");
  std::fwrite(out.data(), sizeof(float), W * H, f);
  std::fclose(f);
  return 0;
}
