// caustic.cpp — analytic pool-caustic field with Airy wave correction.
// Mirrors tools/airy_caustic.py (kept in sync; see tools/parity_cpp.py).
// CPU-only, no renderer dependency.
//
// Two measured improvements over the first implementation (see docs/EVIDENCE.md):
//  1. Fold locus = |det J| of the surface->floor ray map, not an intensity
//     percentile. A percentile always flags the same 2% of pixels regardless of
//     how much of the image is actually inside the fold band, so it is
//     resolution-dependent: RMSE against a 2048^2 truth stalls at 0.08534 while
//     the analytic locus converges (0.20188 -> 0.13738 -> 0.10455 -> 0.03914;
//     see EVIDENCE section 1).
//  2. Band-local flux conservation. Rescaling the whole channel AFTER the
//     intensity clamp pushes the peak back above its own ceiling (11.58x vs a
//     ceiling of 8.10x at 256^2); preserving the band's own energy holds the
//     ceiling (7.55x) with equal-or-better RMSE.
//
// All heavy stages are parallel over rows/columns. Thread count is
// std::thread::hardware_concurrency() unless CAUSTIC_THREADS is set, which also
// makes thread-scaling measurements reproducible.
#include "caustic.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <numeric>
#include <thread>
#include <utility>
#include <vector>

#include "airy_lut.hpp"

namespace caust {
namespace {

constexpr float kPi = 3.14159265358979323846f;
constexpr float kSize = 6.0f;
constexpr float kDepth = 1.0f;
// Achromatic backbone: the pool scene refracts all channels through one eta
// (measured water at 550 nm is 1.33468; 1.333 is 0.0017 low -- geometrically
// negligible). Its per-channel spread comes ONLY from the lambda^(2/3) Airy
// width, not from a per-channel ray map: pool dispersion is a width effect,
// unvalidated against any reference. See EVIDENCE section 8.
constexpr float kEta = 1.0f / 1.333f;
constexpr float kLamp[3] = {650e-9f, 550e-9f, 450e-9f};

int n_threads() {
  static const int n = [] {
    if (const char* e = std::getenv("CAUSTIC_THREADS")) {
      int v = std::atoi(e);
      if (v > 0) return v;
    }
    unsigned hw = std::thread::hardware_concurrency();
    return int(hw ? hw : 4u);
  }();
  return n;
}

// Run fn(y0, y1, tid) over row blocks in parallel.
template <typename F>
void parallel_blocks(int total, int nt, F&& fn) {
  if (nt <= 1 || total <= 1) {
    fn(0, total, 0);
    return;
  }
  int chunk = (total + nt - 1) / nt;
  if (chunk < 1) chunk = 1;
  std::vector<std::thread> th;
  th.reserve(size_t(nt));
  int tid = 0;
  for (int a = 0; a < total; a += chunk) {
    int b = std::min(total, a + chunk);
    th.emplace_back([&fn, a, b, tid] { fn(a, b, tid); });
    tid++;
  }
  for (auto& t : th) t.join();
}

template <typename F>
void parallel_rows(int H, F&& fn) {
  parallel_blocks(H, n_threads(), std::forward<F>(fn));
}

// Linear-interp Airy profile lookup.
float airy_prof(float u) {
  float x = std::clamp(u / kAiryUmax, 0.0f, 1.0f) * float(kAiryN - 1);
  std::size_t i = std::min<std::size_t>(std::size_t(x), kAiryN - 2);
  return kAiryLUT[i] + (kAiryLUT[i + 1] - kAiryLUT[i]) * (x - float(i));
}

// Two-pass Euclidean distance transform (Felzenszwalb-Huttenlocher), squared
// distances. mask==true means "feature" (fold ridge here).
// Pass 1 is independent per row, pass 2 independent per column -> both parallel.
void edt_squared(const std::vector<char>& feat, int W, int H, std::vector<float>& out) {
  const float INF = 1e20f;
  std::vector<float> tmp(W * H, INF);
  parallel_rows(H, [&](int y0, int y1, int) {
    const size_t mx = size_t(std::max(W, H));
    std::vector<float> f(mx, 0.0f), d(mx, 0.0f);
    std::vector<int> v(mx, 0);
    std::vector<float> z(mx + 1, 0.0f);
    for (int y = y0; y < y1; y++) {
      for (int x = 0; x < W; x++) f[x] = feat[y * W + x] ? 0.0f : INF;
      int k = 0;
      v[0] = 0;
      z[0] = -INF;
      z[1] = INF;
      for (int q = 1; q < W; q++) {
        float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) /
                  float(2 * q - 2 * v[k]);
        while (s <= z[k]) {
          k--;
          s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) /
              float(2 * q - 2 * v[k]);
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
  });
  // pass 2: along columns (parallel over columns)
  parallel_rows(W, [&](int x0, int x1, int) {
    const size_t mx = size_t(std::max(W, H));
    std::vector<float> f(mx, 0.0f), d(mx, 0.0f);
    std::vector<int> v(mx, 0);
    std::vector<float> z(mx + 1, 0.0f);
    for (int x = x0; x < x1; x++) {
      for (int y = 0; y < H; y++) f[y] = tmp[y * W + x];
      int k = 0;
      v[0] = 0;
      z[0] = -INF;
      z[1] = INF;
      for (int q = 1; q < H; q++) {
        float s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) /
                  float(2 * q - 2 * v[k]);
        while (s <= z[k]) {
          k--;
          s = ((f[q] + float(q * q)) - (f[v[k]] + float(v[k] * v[k]))) /
              float(2 * q - 2 * v[k]);
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
  });
}

void gaussian_blur(const std::vector<float>& in, int W, int H, float sigma,
                   std::vector<float>& out) {
  int R = std::max(1, int(std::ceil(3 * sigma)));
  std::vector<float> k(2 * R + 1);
  float s = 0;
  for (int i = -R; i <= R; i++) {
    k[i + R] = std::exp(-float(i * i) / (2 * sigma * sigma));
    s += k[i + R];
  }
  for (auto& v : k) v /= s;
  std::vector<float> tmp(W * H);
  parallel_rows(H, [&](int y0, int y1, int) {
    for (int y = y0; y < y1; y++)
      for (int x = 0; x < W; x++) {
        float a = 0;
        for (int i = -R; i <= R; i++) a += k[i + R] * in[y * W + std::clamp(x + i, 0, W - 1)];
        tmp[y * W + x] = a;
      }
  });
  out.assign(W * H, 0);
  parallel_rows(H, [&](int y0, int y1, int) {
    for (int y = y0; y < y1; y++)
      for (int x = 0; x < W; x++) {
        float a = 0;
        for (int i = -R; i <= R; i++) a += k[i + R] * tmp[std::clamp(y + i, 0, H - 1) * W + x];
        out[y * W + x] = a;
      }
  });
}

}  // namespace

std::vector<float> bake(int W, int H, float t, const WaterParams& wp, bool geometric_only,
                        float airy_scale) {
  const int nt = n_threads();
  std::vector<float> h(W * H, 0), gx(W * H, 0), gy(W * H, 0);
  const float kNaN = std::numeric_limits<float>::quiet_NaN();
  std::vector<float> Hxa(W * H, kNaN), Hya(W * H, kNaN);
  std::vector<float> flux(W * H, 0);

  float sun[3] = {-0.35f, -0.25f, -1.0f};
  float sn = std::sqrt(sun[0] * sun[0] + sun[1] * sun[1] + sun[2] * sun[2]);
  sun[0] /= sn;
  sun[1] /= sn;
  sun[2] /= sn;

  // 1+2. surface, gradient, refract, splat.  The splat scatters into
  // neighbouring cells, so each block accumulates into its own buffer.
  const double bytes_per_buf = double(W) * double(H) * sizeof(float);
  const double kBudget = 2.0e8;  // <= ~200 MB of scratch across all threads
  int nt_splat = std::max(1, std::min(nt, int(kBudget / std::max(bytes_per_buf, 1.0))));
  std::vector<std::vector<float>> local;
  local.resize(static_cast<size_t>(nt_splat));
  for (auto& v : local) v.assign(size_t(W) * size_t(H), 0.0f);
  parallel_blocks(H, nt_splat, [&](int y0, int y1, int tid) {
    std::vector<float>& fl = local[size_t(tid)];
    for (int y = y0; y < y1; y++)
      for (int x = 0; x < W; x++) {
        int i = y * W + x;
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
        h[i] = hh;
        gx[i] = dx;
        gy[i] = dy;

        float inv = 1 / std::sqrt(1 + gx[i] * gx[i] + gy[i] * gy[i]);
        float nx = -gx[i] * inv, ny = -gy[i] * inv, nz = inv;
        float cosi = -(sun[0] * nx + sun[1] * ny + sun[2] * nz);
        cosi = std::clamp(cosi, -1.0f, 1.0f);
        float sin2t = kEta * kEta * (1 - cosi * cosi);
        if (sin2t > 1 || cosi <= 0) continue;  // TIR or backface
        float cost = std::sqrt(1 - sin2t);
        float rx = kEta * sun[0] + (kEta * cosi - cost) * nx;
        float ry = kEta * sun[1] + (kEta * cosi - cost) * ny;
        float rz = kEta * sun[2] + (kEta * cosi - cost) * nz;
        float rn = std::sqrt(rx * rx + ry * ry + rz * rz);
        rx /= rn;
        ry /= rn;
        rz /= rn;
        if (rz >= -1e-6f) continue;
        float ss = (-kDepth - h[i]) / rz;
        float Hx = px + rx * ss, Hy = py + ry * ss;
        Hxa[i] = Hx;
        Hya[i] = Hy;
        float fx = (Hx + kSize / 2) / kSize * W - 0.5f;
        float fy = (Hy + kSize / 2) / kSize * H - 0.5f;
        int x0 = int(std::floor(fx)), y0i = int(std::floor(fy));
        float ax = fx - x0, ay = fy - y0i;
        // Discard taps that land outside the receiver. Clamping them onto the
        // border piles all escaping energy into a false bright rim: measured
        // geometric peak 350.8x vs 9.3x for the same field when discarded.
        for (int oy = 0; oy <= 1; oy++)
          for (int ox = 0; ox <= 1; ox++) {
            int xx = x0 + ox, yy = y0i + oy;
            if (xx < 0 || xx >= W || yy < 0 || yy >= H) continue;
            fl[yy * W + xx] += (ox ? ax : 1 - ax) * (oy ? ay : 1 - ay);
          }
      }
  });
  if (nt_splat == 1) {
    flux.swap(local[0]);
  } else {
    flux.assign(size_t(W) * size_t(H), 0.0f);
    for (const auto& v : local)
      for (size_t i = 0; i < flux.size(); i++) flux[i] += v[i];
  }

  float mean = std::accumulate(flux.begin(), flux.end(), 0.0f) / (W * H) + 1e-12f;
  std::vector<float> geom(W * H);
  for (int i = 0; i < W * H; i++) geom[i] = flux[i] / mean;
  if (geometric_only) return geom;

  // 3. wave correction: fold band -> Airy profile, per channel.
  // Fold locus = |det J| -> 0 of the surface->floor ray map.
  const float dX = kSize / float(W - 1), dY = kSize / float(H - 1);
  std::vector<float> adet(W * H, 0.0f);
  parallel_rows(H, [&](int y0, int y1, int) {
    for (int y = y0; y < y1; y++)
      for (int x = 0; x < W; x++) {
        int i = y * W + x;
        int xm = std::max(x - 1, 0), xp = std::min(x + 1, W - 1);
        int ym = std::max(y - 1, 0), yp = std::min(y + 1, H - 1);
        float hx_dx = (Hxa[y * W + xp] - Hxa[y * W + xm]) / (float(xp - xm) * dX);
        float hx_dy = (Hxa[yp * W + x] - Hxa[ym * W + x]) / (float(yp - ym) * dY);
        float hy_dx = (Hya[y * W + xp] - Hya[y * W + xm]) / (float(xp - xm) * dX);
        float hy_dy = (Hya[yp * W + x] - Hya[ym * W + x]) / (float(yp - ym) * dY);
        float dj = hx_dx * hy_dy - hx_dy * hy_dx;
        adet[i] = std::isfinite(dj) ? std::fabs(dj) : 0.0f;
      }
  });
  std::vector<float> sorted = adet;
  std::nth_element(sorted.begin(), sorted.begin() + sorted.size() * 2 / 100, sorted.end());
  float thr = sorted[sorted.size() * 2 / 100];
  std::vector<char> feat(W * H);
  for (int i = 0; i < W * H; i++) feat[i] = adet[i] < thr;

  std::vector<float> d2(W * H);
  edt_squared(feat, W, H, d2);
  float dxm = kSize / W;
  std::vector<float> smooth(W * H);
  gaussian_blur(geom, W, H, 3.0f, smooth);

  constexpr float kCap = 6.0f;
  std::vector<float> out(W * H * 3);
  for (int c = 0; c < 3; c++) {
    float w = airy_scale * std::pow(kLamp[c] / 550e-9f, 2.0f / 3.0f);
    // Band-local flux conservation: the Airy profile redistributes the band's
    // OWN energy, so no global rescale (which would break the ceiling) is used.
    std::vector<double> pw(size_t(nt), 0.0), pg(size_t(nt), 0.0);
    parallel_blocks(H, nt, [&](int y0, int y1, int tid) {
      double want = 0, got = 0;
      for (int y = y0; y < y1; y++)
        for (int x = 0; x < W; x++) {
          int i = y * W + x;
          float s = std::sqrt(d2[i]) * dxm;
          if (s < 5 * w) {
            want += geom[i];
            got += double(std::min(smooth[i], kCap)) * (0.15f + 0.85f * airy_prof(s / w));
          }
        }
      pw[size_t(tid)] = want;
      pg[size_t(tid)] = got;
    });
    double want = 0, got = 0;
    for (int i = 0; i < nt; i++) {
      want += pw[size_t(i)];
      got += pg[size_t(i)];
    }
    float k = got > 0 ? float(want / got) : 0.0f;
    parallel_rows(H, [&](int y0, int y1, int) {
      for (int y = y0; y < y1; y++)
        for (int x = 0; x < W; x++) {
          int i = y * W + x;
          float s = std::sqrt(d2[i]) * dxm;
          float v = geom[i];
          if (s < 5 * w) {
            float strength = std::min(smooth[i], kCap);
            v = std::min(strength * (0.15f + 0.85f * airy_prof(s / w)) * k, kCap * 1.35f);
          }
          out[(i * 3) + c] = v;
        }
    });
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
