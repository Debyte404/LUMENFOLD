// caustic.cpp — analytic pool-caustic field with Airy wave correction.
// Mirrors tools/airy_caustic.py. CPU-only, no renderer dependency.
#include "caustic.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

#include "airy_lut.hpp"

namespace caust {
namespace {

constexpr float kPi = 3.14159265358979323846f;
constexpr float kSize = 6.0f;
constexpr float kDepth = 1.0f;
constexpr float kEta = 1.0f / 1.333f;
constexpr float kLamp[3] = {650e-9f, 550e-9f, 450e-9f};

// Linear-interp Airy profile lookup.
float airy_prof(float u) {
  float x = std::clamp(u / kAiryUmax, 0.0f, 1.0f) * float(kAiryN - 1);
  std::size_t i = std::min<std::size_t>(std::size_t(x), kAiryN - 2);
  return kAiryLUT[i] + (kAiryLUT[i + 1] - kAiryLUT[i]) * (x - float(i));
}

// Two-pass Euclidean distance transform (Felzenszwalb-Huttenlocher), squared
// distances. mask==true means "feature" (fold ridge here).
void edt_squared(const std::vector<char>& feat, int W, int H, std::vector<float>& out) {
  const float INF = 1e20f;
  std::vector<float> tmp(W * H, INF);
  std::vector<float> f(std::max(W, H)), d(std::max(W, H));
  std::vector<int> v(std::max(W, H));
  std::vector<float> z(std::max(W, H) + 1);
  // pass 1: along rows
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) f[x] = feat[y * W + x] ? 0.0f : INF;
    int k = 0;
    v[0] = 0;
    z[0] = -INF;
    z[1] = INF;
    for (int q = 1; q < W; q++) {
      float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      while (s <= z[k]) {
        k--;
        s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      }
      k++;
      v[k] = q;
      z[k] = s;
      z[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < W; q++) {
      while (z[k + 1] < q) k++;
      float dd = float(q - v[k]);
      d[q] = dd * dd + f[v[k]];
    }
    for (int x = 0; x < W; x++) tmp[y * W + x] = d[x];
  }
  // pass 2: along cols
  for (int x = 0; x < W; x++) {
    for (int y = 0; y < H; y++) f[y] = tmp[y * W + x];
    int k = 0;
    v[0] = 0;
    z[0] = -INF;
    z[1] = INF;
    for (int q = 1; q < H; q++) {
      float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      while (s <= z[k]) {
        k--;
        s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) / float(2 * q - 2 * v[k]);
      }
      k++;
      v[k] = q;
      z[k] = s;
      z[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < H; q++) {
      while (z[k + 1] < q) k++;
      float dd = float(q - v[k]);
      out[q * W + x] = dd * dd + f[v[k]];
    }
  }
}

void gaussian_blur(const std::vector<float>& in, int W, int H, float sigma, std::vector<float>& out) {
  int R = std::max(1, int(std::ceil(3 * sigma)));
  std::vector<float> k(2 * R + 1);
  float s = 0;
  for (int i = -R; i <= R; i++) {
    k[i + R] = std::exp(-float(i * i) / (2 * sigma * sigma));
    s += k[i + R];
  }
  for (auto& v : k) v /= s;
  std::vector<float> tmp(W * H);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      float a = 0;
      for (int i = -R; i <= R; i++) a += k[i + R] * in[y * W + std::clamp(x + i, 0, W - 1)];
      tmp[y * W + x] = a;
    }
  out.assign(W * H, 0);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      float a = 0;
      for (int i = -R; i <= R; i++) a += k[i + R] * tmp[std::clamp(y + i, 0, H - 1) * W + x];
      out[y * W + x] = a;
    }
}

}  // namespace

std::vector<float> bake(int W, int H, float t, const WaterParams& wp, bool geometric_only,
                        float airy_scale) {
  // 1. surface + gradients
  std::vector<float> h(W * H, 0), gx(W * H, 0), gy(W * H, 0);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      float px = (float(x) / (W - 1) - 0.5f) * kSize;
      float py = (float(y) / (H - 1) - 0.5f) * kSize;
      float hh = 0, dx = 0, dy = 0;
      for (int w = 0; w < wp.n_waves; w++) {
        float vx = wp.dirx[w], vy = wp.diry[w];
        float n = std::sqrt(vx * vx + vy * vy);
        vx /= n;
        vy /= n;
        float k = 2 * kPi / wp.wavelength[w];
        float ph = k * (vx * px + vy * py) - wp.speed[w] * k * t;
        hh += wp.amp[w] * std::sin(ph);
        float c = wp.amp[w] * k * std::cos(ph);
        dx += c * vx;
        dy += c * vy;
      }
      h[y * W + x] = hh;
      gx[y * W + x] = dx;
      gy[y * W + x] = dy;
    }
  // 2. refract + splat (bilinear)
  float sun[3] = {-0.35f, -0.25f, -1.0f};
  float sn = std::sqrt(sun[0] * sun[0] + sun[1] * sun[1] + sun[2] * sun[2]);
  sun[0] /= sn;
  sun[1] /= sn;
  sun[2] /= sn;
  std::vector<float> flux(W * H, 0);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      int i = y * W + x;
      float inv = 1 / std::sqrt(1 + gx[i] * gx[i] + gy[i] * gy[i]);
      float nx = -gx[i] * inv, ny = -gy[i] * inv, nz = inv;
      float cosi = -(sun[0] * nx + sun[1] * ny + sun[2] * nz);
      cosi = std::clamp(cosi, -1.0f, 1.0f);
      float sin2t = kEta * kEta * (1 - cosi * cosi);
      if (sin2t > 1 || cosi <= 0) continue;  // TIR or backface (shouldn't happen here)
      float cost = std::sqrt(1 - sin2t);
      float rx = kEta * sun[0] + (kEta * cosi - cost) * nx;
      float ry = kEta * sun[1] + (kEta * cosi - cost) * ny;
      float rz = kEta * sun[2] + (kEta * cosi - cost) * nz;
      float rn = std::sqrt(rx * rx + ry * ry + rz * rz);
      rx /= rn;
      ry /= rn;
      rz /= rn;
      if (rz >= -1e-6f) continue;
      float px = (float(x) / (W - 1) - 0.5f) * kSize;
      float py = (float(y) / (H - 1) - 0.5f) * kSize;
      float s = (-kDepth - h[i]) / rz;
      float Hx = px + rx * s, Hy = py + ry * s;
      float fx = (Hx + kSize / 2) / kSize * W - 0.5f;
      float fy = (Hy + kSize / 2) / kSize * H - 0.5f;
      int x0 = int(std::floor(fx)), y0 = int(std::floor(fy));
      float ax = fx - x0, ay = fy - y0;
      for (int oy = 0; oy <= 1; oy++)
        for (int ox = 0; ox <= 1; ox++) {
          int xx = std::clamp(x0 + ox, 0, W - 1), yy = std::clamp(y0 + oy, 0, H - 1);
          flux[yy * W + xx] += (ox ? ax : 1 - ax) * (oy ? ay : 1 - ay);
        }
    }
  float mean = std::accumulate(flux.begin(), flux.end(), 0.0f) / (W * H) + 1e-12f;
  std::vector<float> geom(W * H);
  for (int i = 0; i < W * H; i++) geom[i] = flux[i] / mean;
  if (geometric_only) return geom;

  // 3. wave correction: fold band -> Airy profile, per channel, flux-conserved
  std::vector<float> sorted = geom;
  std::nth_element(sorted.begin(), sorted.begin() + sorted.size() * 98 / 100, sorted.end());
  float thr = sorted[sorted.size() * 98 / 100];
  std::vector<char> feat(W * H);
  for (int i = 0; i < W * H; i++) feat[i] = geom[i] > thr;
  std::vector<float> d2(W * H);
  edt_squared(feat, W, H, d2);
  float dxm = kSize / W;
  std::vector<float> smooth(W * H);
  gaussian_blur(geom, W, H, 3.0f, smooth);
  constexpr float kCap = 6.0f;
  std::vector<float> out(W * H * 3);
  for (int c = 0; c < 3; c++) {
    float w = airy_scale * std::pow(kLamp[c] / 550e-9f, 2.0f / 3.0f);
    double sum = 0;
    for (int i = 0; i < W * H; i++) {
      float s = std::sqrt(d2[i]) * dxm;
      float v;
      if (s < 5 * w) {
        float strength = std::min(smooth[i], kCap);
        v = strength * (0.15f + 0.85f * airy_prof(s / w));
        v = std::min(v, kCap * 1.35f);
      } else {
        v = geom[i];
      }
      out[(i * 3) + c] = v;
      sum += v;
    }
    double target = std::accumulate(geom.begin(), geom.end(), 0.0);
    float k = float(target / (sum + 1e-12));
    for (int i = 0; i < W * H; i++) out[(i * 3) + c] *= k;
  }
  return out;  // interleaved RGB when !geometric_only
}

std::vector<uint8_t> tonemap(const std::vector<float>& field) {
  std::size_t n = field.size() / 3;
  std::vector<uint8_t> rgb(n * 3);
  for (std::size_t i = 0; i < n; i++)
    for (int c = 0; c < 3; c++) {
      float v = std::clamp(field[i * 3 + c] / 8.0f, 0.0f, 1.0f);
      v = std::pow(v, 1.0f / 2.2f);  // gamma
      rgb[i * 3 + c] = std::uint8_t(std::clamp(v, 0.0f, 1.0f) * 255.0f);
    }
  return rgb;
}

}  // namespace caust
