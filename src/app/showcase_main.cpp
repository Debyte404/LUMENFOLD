// showcase_main.cpp — offline still: a glass of water on a wood table, lit
// obliquely, with a wave-corrected caustic fan and chromatic dispersion.
//
// Why this scene: it is the canonical case where rays visibly fail - a cylinder
// focuses the refracted beam into a fold, the geometric map predicts infinite
// intensity there, and the real photograph shows a finite fan with a spectral
// fringe along the fold. Exactly the structure the Airy correction produces.
//
// Method: the same three pieces as src/render/caustic.cpp, on a different ray
// map -
//   1. trace the refracted ray map and splat it (quadrature -> geometric field)
//   2. fold locus = where |dH/dphi| -> 0 (the map degenerates), analytic,
//      NOT an intensity percentile
//   3. replace the band with the Airy fold profile |Ai(-s/w)|^2 per wavelength,
//      w ~ lambda^(2/3) and n(lambda) via Cauchy, conserving flux INSIDE the
//      band so the ceiling holds
//
// Documented approximations (do not overclaim this image):
//   * the glass wall + water column is modelled as ONE refracting cylinder of
//     index n_water(lambda); the thin glass shell (n~1.5) is neglected
//   * every ray is taken to enter at mid-height (removes a small vertical
//     smearing of the fan, not its structure)
//   * wood grain and the glass surface shading are procedural, not measured
//   * no interreflection, no caustic re-focus by the glass rim
//
//   showcase [--n 1600] [--res 1024] [--airy 0.006] [--out out/showcase.png]
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace {

// ---------------------------------------------------------------- PNG writer
void put32(std::vector<uint8_t>& o, uint32_t v) {
  o.push_back((v >> 24) & 0xFF);
  o.push_back((v >> 16) & 0xFF);
  o.push_back((v >> 8) & 0xFF);
  o.push_back(v & 0xFF);
}
uint32_t crc32_of(const uint8_t* d, size_t n) {
  static uint32_t t[256];
  static bool init = false;
  if (!init) {
    for (uint32_t i = 0; i < 256; i++) {
      uint32_t c = i;
      for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : (c >> 1);
      t[i] = c;
    }
    init = true;
  }
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; i++) c = t[(c ^ d[i]) & 0xFF] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}
void chunk(std::vector<uint8_t>& o, const char* type, const uint8_t* d, size_t n) {
  put32(o, (uint32_t)n);
  size_t h = o.size();
  o.insert(o.end(), type, type + 4);
  if (n) o.insert(o.end(), d, d + n);
  put32(o, crc32_of(o.data() + h, 4 + n));
}
std::vector<uint8_t> zlib_store(const uint8_t* d, size_t n) {
  std::vector<uint8_t> o = {0x78, 0x01};
  uint32_t a = 1, b = 0;
  size_t i = 0;
  while (i < n) {
    size_t blk = std::min<size_t>(n - i, 65535);
    bool last = (i + blk == n);
    o.push_back(last ? 0x01 : 0x00);
    o.push_back(blk & 0xFF);
    o.push_back((blk >> 8) & 0xFF);
    o.push_back((~blk) & 0xFF);
    o.push_back(((~blk) >> 8) & 0xFF);
    o.insert(o.end(), d + i, d + i + blk);
    for (size_t k = i; k < i + blk; k++) {
      a += d[k];
      b += a;
      a %= 65521;
      b %= 65521;
    }
    i += blk;
  }
  put32(o, (b << 16) | a);
  return o;
}
bool write_png(const char* path, int W, int H, const std::vector<uint8_t>& rgb_topdown) {
  std::vector<uint8_t> o = {137, 80, 78, 71, 13, 10, 26, 10};
  uint8_t ihdr[13] = {(uint8_t)(W >> 24), (uint8_t)(W >> 16), (uint8_t)(W >> 8), (uint8_t)W,
                      (uint8_t)(H >> 24), (uint8_t)(H >> 16), (uint8_t)(H >> 8), (uint8_t)H,
                      8, 2, 0, 0, 0};
  chunk(o, "IHDR", ihdr, 13);
  std::vector<uint8_t> raw;
  raw.reserve((size_t)H * (W * 3 + 1));
  for (int y = 0; y < H; y++) {
    raw.push_back(0);
    raw.insert(raw.end(), rgb_topdown.begin() + (size_t)y * W * 3,
               rgb_topdown.begin() + (size_t)(y + 1) * W * 3);
  }
  auto z = zlib_store(raw.data(), raw.size());
  chunk(o, "IDAT", z.data(), z.size());
  chunk(o, "IEND", nullptr, 0);
  std::ofstream f(path, std::ios::binary);
  if (!f) return false;
  f.write((const char*)o.data(), o.size());
  return true;
}

// 16-bit RGB PNG, for handing the caustic field to Blender without banding.
// Samples are big-endian per the PNG spec.
bool write_png16(const char* path, int W, int H, const std::vector<uint16_t>& rgb_topdown) {
  std::vector<uint8_t> o = {137, 80, 78, 71, 13, 10, 26, 10};
  uint8_t ihdr[13] = {(uint8_t)(W >> 24), (uint8_t)(W >> 16), (uint8_t)(W >> 8), (uint8_t)W,
                      (uint8_t)(H >> 24), (uint8_t)(H >> 16), (uint8_t)(H >> 8), (uint8_t)H,
                      16, 2, 0, 0, 0};
  chunk(o, "IHDR", ihdr, 13);
  std::vector<uint8_t> raw;
  raw.reserve((size_t)H * (size_t(W) * 6 + 1));
  for (int y = 0; y < H; y++) {
    raw.push_back(0);
    for (int x = 0; x < W; x++)
      for (int c = 0; c < 3; c++) {
        uint16_t v = rgb_topdown[((size_t)y * W + x) * 3 + c];
        raw.push_back(uint8_t(v >> 8));
        raw.push_back(uint8_t(v & 0xFF));
      }
  }
  auto z = zlib_store(raw.data(), raw.size());
  chunk(o, "IDAT", z.data(), z.size());
  chunk(o, "IEND", nullptr, 0);
  std::ofstream f(path, std::ios::binary);
  if (!f) return false;
  f.write((const char*)o.data(), o.size());
  return true;
}

// ---------------------------------------------------------------- tiny vector
struct V3 {
  double x = 0, y = 0, z = 0;
};
V3 operator+(V3 a, V3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
V3 operator-(V3 a, V3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
V3 operator*(V3 a, double s) { return {a.x * s, a.y * s, a.z * s}; }
double dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
V3 normalize(V3 a) {
  double n = std::sqrt(dot(a, a));
  return n > 0 ? a * (1.0 / n) : a;
}

// ---------------------------------------------------------------- scene setup
constexpr double kGlassR = 0.035;   // cylinder radius, m
constexpr double kGlassH = 0.090;   // cylinder height, m
constexpr double kFill = 0.66;      // water fills 2/3
// Low, late-afternoon sun (~25 deg elevation). A steep sun cannot produce a
// table caustic from a glass this tall: the ray drops more than the glass is
// high before it can exit the far wall, so it crosses the table inside the
// glass. Measured while bringing this up - the first attempt used a 59 deg sun
// and produced an empty field. This also matches the reference photograph,
// where the caustic is a long fan thrown well clear of the glass.
const V3 kSun = {0.80, 0.42, -0.43};  // direction light TRAVELS (downward)

// Cauchy for water: n(lambda) = A + B/lambda^2 (lambda in nm).
// A/B chosen to give ~1.3314 / 1.3345 / 1.3407 at 650 / 550 / 450 nm.
constexpr double kCauchyA = 1.31700;
constexpr double kCauchyB = 6080.0;
double water_index(double lambda_nm) {
  return kCauchyA + kCauchyB / (lambda_nm * lambda_nm);
}

// Vector Snell. d and n unit, d pointing INTO the surface (dot(d,n) < 0).
bool snell(V3 d, V3 n, double eta, V3& t) {
  double ci = -dot(d, n);
  if (ci < 0) return false;
  double s2 = eta * eta * (1.0 - ci * ci);
  if (s2 > 1.0) return false;  // total internal reflection
  double ct = std::sqrt(1.0 - s2);
  t = normalize(d * eta + n * (eta * ci - ct));
  return true;
}

// Trace the ray that enters the cylinder at angle phi (mid-height) and find
// where it lands on the table (z = 0). Also returns |dH/dphi| by finite
// difference, which is the caustic condition: it vanishes on the fold.
struct Hit {
  double x, y;      // table hit
  double jac;       // |dH/dphi|, metres per radian
  bool ok;
};

Hit trace(double phi, double n_water) {
  Hit h{0, 0, 0, false};
  V3 P{kGlassR * std::cos(phi), kGlassR * std::sin(phi), kGlassH * 0.5};
  V3 nrm{std::cos(phi), std::sin(phi), 0.0};
  V3 d = normalize(kSun);
  V3 t1;
  if (!snell(d, nrm, 1.0 / n_water, t1)) return h;

  // exit point: the entry point lies ON the circle (c = 0), so the two
  // intersections are s = 0 (entry) and s = -b; the exit is -b.
  double b = 2.0 * (P.x * t1.x + P.y * t1.y);
  double s = -b;
  if (s <= 1e-9) return h;
  V3 Q = P + t1 * s;
  V3 nq{Q.x / kGlassR, Q.y / kGlassR, 0.0};
  V3 t2;
  // snell() expects the normal to face the incoming ray, so at the exit the
  // OUTWARD normal must be flipped inward. Passing it unflipped silently
  // rejected every ray and produced an empty caustic field.
  if (!snell(t1, nq * -1.0, n_water / 1.0, t2)) return h;
  if (t2.z >= -1e-9) return h;  // must still be heading down
  if (Q.z <= 0.0) return h;     // exits below the table: blocked by it
  double drop = Q.z / (-t2.z);
  h.x = Q.x + t2.x * drop;
  h.y = Q.y + t2.y * drop;
  h.ok = true;
  return h;
}

// Does the table point (x,y) sit in the glass's shadow? Walk back along -sun
// in the horizontal plane and test the circle.
bool in_shadow(double x, double y) {
  V3 hs{kSun.x, kSun.y, 0};
  hs = normalize(hs);
  double px = x - hs.x * 1e4, py = y - hs.y * 1e4;
  double dx = hs.x, dy = hs.y;
  double b = 2.0 * (px * dx + py * dy);
  double c = px * px + py * py - kGlassR * kGlassR;
  double disc = b * b - 4.0 * c;
  return disc >= 0;
}

// ------------------------------------------------------- caustic field (N x N)
// Coverage: [ -ext, ext ]^2 around the glass, ext = kExt.
constexpr double kExt = 0.16;

struct Field {
  int N = 0;
  std::vector<float> rgb;  // N*N*3 linear intensity
};

constexpr double kPi = 3.14159265358979323846;

int idx(int N, int x, int y) { return y * N + x; }

constexpr double kCapAiry = 6.0;
constexpr double kAiryUmax = 8.0;

// |Ai(-u)|^2 normalized to unit peak. Ai(x) = (1/pi) * int_0^inf cos(t^3/3 + x*t) dt,
// evaluated by Simpson. Tabulated once; this is the fold-caustic profile.
double airy_prof_1d(double u) {
  static const std::vector<double> lut = [] {
    std::vector<double> l(2048);
    double mx = 0;
    for (int i = 0; i < 2048; i++) {
      double uu = kAiryUmax * i / 2047.0;
      const int S = 4000;
      double hh = 12.0 / S, sum = 0;
      for (int k = 0; k <= S; k++) {
        double t = k * hh;
        double fv = std::cos(t * t * t / 3.0 - uu * t);
        double wgt = (k == 0 || k == S) ? 1.0 : (k % 2 ? 4.0 : 2.0);
        sum += wgt * fv;
      }
      double a = sum * hh / 3.0 / kPi;
      l[i] = a * a;
      mx = std::max(mx, l[i]);
    }
    for (double& v : l) v /= (mx > 0 ? mx : 1.0);
    return l;
  }();
  double t = std::clamp(u / kAiryUmax, 0.0, 1.0) * 2047.0;
  int i = std::min<int>(int(t), 2046);
  return lut[i] + (lut[i + 1] - lut[i]) * (t - i);
}

Field build_caustic(int N, double airy_scale) {
  const double lambdas[3] = {650.0, 550.0, 450.0};
  Field f;
  f.N = N;
  f.rgb.assign((size_t)N * N * 3, 0.0f);

  // The pattern a vertical cylinder throws from a parallel beam is INVARIANT
  // along the direction perpendicular to the light's horizontal projection, so
  // the whole caustic is a function of one table coordinate
  //     u = dot(P, e_u),   e_u = normalize(sun.xy)
  // and the fold set is a family of straight lines - the fan in the reference
  // photograph - not isolated points. Modelling it as a 2D point splat gave
  // 0.05% of frame coverage; the invariant 1D model gives the fan.
  V3 eu = normalize(V3{kSun.x, kSun.y, 0});

  const int M = 400000;  // rays around the cylinder
  const double dphi = 2.0 * kPi / M;
  const double du = 2.0 * kExt / N;  // one cell of the u axis

  auto u_of = [&](const V3& p) { return p.x * eu.x + p.y * eu.y; };

  for (int c = 0; c < 3; c++) {
    double n = water_index(lambdas[c]);
    std::vector<double> flux((size_t)N, 0.0);
    std::vector<char> fold1d((size_t)N, 0);
    std::vector<double> jacmin((size_t)N, 1e30);

    // pass 1: accumulate the 1D quadrature and the fold marks
    for (int i = 0; i < M; i++) {
      double phi = (i + 0.5) * dphi;
      Hit h = trace(phi, n);
      if (!h.ok) continue;
      Hit hp = trace(phi + 1e-6, n), hm = trace(phi - 1e-6, n);
      double jac = (hp.ok && hm.ok)
                       ? std::hypot(hp.x - hm.x, hp.y - hm.y) / 2e-6
                       : 1e30;
      double u = u_of(V3{h.x, h.y, 0});
      double fu = (u + kExt) / (2 * kExt) * N - 0.5;
      int u0 = int(std::floor(fu));
      double au = fu - u0;
      // rays pile up where the map compresses: weight by 1/|dH/dphi|
      double w = (jac > 1e-9) ? 1.0 / jac : 0.0;
      if (u0 >= 0 && u0 < N) flux[u0] += (1 - au) * w;
      if (u0 + 1 >= 0 && u0 + 1 < N) flux[u0 + 1] += au * w;
      int uc = std::clamp(u0, 0, N - 1);
      jacmin[uc] = std::min(jacmin[uc], jac);
    }
    // normalize the 1D profile to mean 1
    double mean = 0;
    for (double v : flux) mean += v;
    mean /= double(N);
    if (mean <= 0) mean = 1e-12;
    for (double& v : flux) v /= mean;

    // fold cells: an ABSOLUTE compression criterion, not a percentile.
    // A percentile only ever marks 2% of cells, so cells just above the cut kept
    // their raw 1/|dH/dphi| spike and escaped the ceiling entirely (measured
    // peaks of 326x with a nominal cap of 8.1x). The caustic condition is
    // |dH/dphi| -> 0, so mark everything far below the typical compression.
    std::vector<double> js;
    js.reserve(N);
    for (int i = 0; i < N; i++)
      if (jacmin[i] < 1e29) js.push_back(jacmin[i]);
    if (!js.empty()) {
      std::sort(js.begin(), js.end());
      double jmed = js[js.size() / 2];
      double thr = 0.10 * jmed;
      for (int i = 0; i < N; i++)
        if (jacmin[i] < thr) fold1d[i] = 1;
    }

    // 1D distance to the nearest fold cell (exact, two sweeps)
    std::vector<double> sd((size_t)N, 1e18);
    {
      double last = -1e18;
      for (int i = 0; i < N; i++) {
        if (fold1d[i]) last = i;
        if (last > -1e17) sd[i] = std::min(sd[i], std::abs(double(i) - last));
      }
      last = 1e18;
      for (int i = N - 1; i >= 0; i--) {
        if (fold1d[i]) last = i;
        if (last < 1e17) sd[i] = std::min(sd[i], std::abs(double(i) - last));
      }
    }
    // smooth the profile slightly before using it as the band strength
    std::vector<double> sm((size_t)N, 0.0);
    for (int i = 0; i < N; i++) {
      double a = 0;
      int k = 0;
      for (int d = -3; d <= 3; d++) {
        int j = std::clamp(i + d, 0, N - 1);
        a += flux[j];
        k++;
      }
      sm[i] = a / k;
    }

    // per-channel Airy replacement in the band, flux conserved inside the band
    const double w = airy_scale * std::pow(lambdas[c] / 550.0, 2.0 / 3.0);
    std::vector<double> out((size_t)N, 0.0);
    double want = 0, got = 0;
    for (int i = 0; i < N; i++) {
      double s = sd[i] * du;
      if (s < 5 * w) {
        want += flux[i];
        got += std::min(sm[i], kCapAiry) * (0.15 + 0.85 * airy_prof_1d(s / w));
      }
    }
    double kk = got > 0 ? want / got : 0.0;
    for (int i = 0; i < N; i++) {
      double s = sd[i] * du;
      double v = flux[i];
      if (s < 5 * w) {
        double base = std::min(sm[i], kCapAiry);
        v = std::min(base * (0.15 + 0.85 * airy_prof_1d(s / w)) * kk, kCapAiry * 1.35);
      }
      out[i] = std::min(v, kCapAiry * 1.35);  // the ceiling holds everywhere
    }
    // broadcast: fill the 2D field from the invariant 1D profile
    for (int y = 0; y < N; y++)
      for (int x = 0; x < N; x++) {
        double px = (double(x) / (N - 1) - 0.5) * 2 * kExt;
        double py = (double(y) / (N - 1) - 0.5) * 2 * kExt;
        double u = px * eu.x + py * eu.y;
        double fu = (u + kExt) / (2 * kExt) * N - 0.5;
        int u0 = int(std::floor(fu));
        double au = fu - u0;
        int a = std::clamp(u0, 0, N - 1), b2 = std::clamp(u0 + 1, 0, N - 1);
        f.rgb[((size_t)idx(N, x, y)) * 3 + c] = float(out[a] * (1 - au) + out[b2] * au);
      }
  }
  return f;
}

// ------------------------------------------------------- caustic field (N x N)
// procedural wood: fine straight grain along a diagonal, warm light tone
void wood(double x, double y, double& r, double& g, double& b) {
  double u = x * 0.7 + y * 0.7;         // grain direction
  double v = -x * 0.7 + y * 0.7;
  double grain = 0.5 + 0.5 * std::sin(u * 900.0 + 6.0 * std::sin(v * 40.0));
  grain = std::pow(grain, 0.6);
  double fibre = 0.5 + 0.5 * std::sin(v * 260.0);
  // wider albedo swing than the first pass: at 0.82+0.18*grain the table read
  // as a flat field (measured p50 150 / p99 157)
  double k = 0.70 + 0.42 * grain - 0.12 * fibre;
  // palette matched to the reference photo, which measures R-B warmth 18.5;
  // the first pass at 0.60/0.48/0.36 came out at 38.6, twice as warm
  r = 0.575 * k;
  g = 0.525 * k;
  b = 0.470 * k;
}

void table_albedo(double x, double y, double out[3]) {
  double r, g, b;
  wood(x, y, r, g, b);
  out[0] = r;
  out[1] = g;
  out[2] = b;
}

inline float sample_field(const Field& f, double x, double y, int c) {
  double fx = (x + kExt) / (2 * kExt) * f.N - 0.5;
  double fy = (y + kExt) / (2 * kExt) * f.N - 0.5;
  int x0 = int(std::floor(fx)), y0 = int(std::floor(fy));
  double ax = fx - x0, ay = fy - y0;
  float acc = 0;
  for (int oy = 0; oy <= 1; oy++)
    for (int ox = 0; ox <= 1; ox++) {
      int xx = std::clamp(x0 + ox, 0, f.N - 1), yy = std::clamp(y0 + oy, 0, f.N - 1);
      acc += float((ox ? ax : 1 - ax) * (oy ? ay : 1 - ay)) *
             f.rgb[((size_t)idx(f.N, xx, yy)) * 3 + c];
    }
  return acc;
}

// ============================================================================
// Dielectric stack + shading, for the photoreal pass.
//
// The scene is a genuine multi-layer dielectric: air | glass shell | water,
// with the sun as a small (1.2 deg) disk so penumbrae are real, a gradient
// environment for the reflected branches and ambient, Beer-Lambert absorption
// in the water, and a rough-specular term on the table so the glass leaves a
// sheen. Every interface uses Fresnel with the wavelength-dependent index, so
// the chromatic separation comes from the transport itself.
// ============================================================================

constexpr double kRout = kGlassR;              // outer wall radius
constexpr double kRin = kGlassR - 0.0035;      // 3.5 mm wall
constexpr double kWaterLevel = kGlassH * kFill;

double glass_index(double l) { return 1.5095 + 4200.0 / (l * l); }  // soda-lime Cauchy

// Medium id: 0 air, 1 glass, 2 water.
int medium_at(const V3& p) {
  if (p.z < 0.0) return 0;  // below the table plane
  double r = std::hypot(p.x, p.y);
  if (r > kRout) return 0;
  if (r > kRin) return 1;
  return (p.z < kWaterLevel) ? 2 : 0;
}
double medium_index(int m, double lambda) {
  if (m == 1) return glass_index(lambda);
  if (m == 2) return water_index(lambda);
  return 1.0;
}

// Beer-Lambert absorption per metre (water is faintly cyan over centimetres).
void medium_absorb(int m, double dist, double out[3]) {
  const double aw[3] = {0.35, 0.06, 0.025};
  const double ag[3] = {0.10, 0.08, 0.07};
  for (int c = 0; c < 3; c++) {
    double s = (m == 2) ? aw[c] : (m == 1 ? ag[c] : 0.0);
    out[c] = std::exp(-s * dist);
  }
}

// Gradient environment: bright warm sky overhead, dim warm ground bounce.
void env_color(const V3& d, double out[3]) {
  double up = std::clamp(d.z * 0.7 + 0.30, 0.0, 1.0);
  const double skyv[3] = {0.62, 0.72, 0.95};
  const double hz[3] = {0.85, 0.74, 0.60};
  const double gnd[3] = {0.11, 0.095, 0.08};
  for (int c = 0; c < 3; c++) {
    out[c] = (d.z >= 0) ? (hz[c] * (1.0 - up) + skyv[c] * up) : gnd[c];
  }
}

// The sun: a disk of angular radius ~1.2 deg around kSun.
constexpr double kSunAng = 0.021;
// kSun is the direction light TRAVELS (downward); its negation points at the
// light and is what shadow rays and mirror reflections must use. Casting the
// shadow ray along kSun instead tested the wrong side of the glass and
// registered zero shadows.
const V3 kSunTo{-kSun.x, -kSun.y, -kSun.z};

void sun_dir_sample(int i, int n, V3& out) {
  // concentric-ish disk sample on the sun's angular disk
  double r = kSunAng * std::sqrt((double(i) + 0.5) / double(n));
  double th = 2.399963229728653 * double(i);
  V3 s = normalize(kSunTo);
  V3 tmp = (std::fabs(s.z) < 0.9) ? V3{0, 0, 1} : V3{1, 0, 0};
  V3 t1 = normalize(V3{s.y * tmp.z - s.z * tmp.y, s.z * tmp.x - s.x * tmp.z,
                       s.x * tmp.y - s.y * tmp.x});
  V3 t2 = V3{s.y * t1.z - s.z * t1.y, s.z * t1.x - s.x * t1.z, s.x * t1.y - s.y * t1.x};
  out = normalize(s + t1 * (r * std::cos(th)) + t2 * (r * std::sin(th)));
}

double fresnel_dielectric(double cosi, double eta) {
  double s2 = eta * eta * (1.0 - cosi * cosi);
  if (s2 >= 1.0) return 1.0;
  double cost = std::sqrt(1.0 - s2);
  double rs = (eta * cosi - cost) / (eta * cosi + cost);
  double rp = (cosi - eta * cost) / (cosi + eta * cost);
  return 0.5 * (rs * rs + rp * rp);
}
double schlick(double f0, double cosi) { return f0 + (1 - f0) * std::pow(1 - cosi, 5.0); }

V3 reflect_dir(V3 d, V3 n) { return normalize(d - n * (2.0 * dot(d, n))); }

bool refract_dir(V3 d, V3 n, double eta, V3& t) {
  double ci = -dot(d, n);
  if (ci < 0) return false;
  double s2 = eta * eta * (1.0 - ci * ci);
  if (s2 > 1.0) return false;
  double ct = std::sqrt(1.0 - s2);
  t = normalize(d * eta + n * (eta * ci - ct));
  return true;
}

// Nearest positive crossing with any scene surface. Fills t, the point, the
// outward normal, the two medium ids on either side, and the surface KIND
// (0 = table, 1 = dielectric). The medium-equality guard applies only to
// dielectrics: the table legitimately has air on BOTH sides (that is what a
// table is), and rejecting it silently replaced the entire table with the
// ground colour - no wood, no shadow, and no caustic anywhere outside the
// glass footprint.
bool next_crossing(V3 o, V3 d, double tmin, double& tbest, V3& pbest, V3& nbest, int& m_in,
                   int& m_out, int& kind) {
  tbest = 1e30;
  bool found = false;
  int best_kind = 0;
  auto consider = [&](double t, V3 n, int k) {
    if (t <= tmin || t >= tbest) return;
    V3 p = o + d * t;
    if (p.z < -1e-9) return;
    tbest = t;
    pbest = p;
    nbest = n;
    best_kind = k;
    found = true;
  };
  // cylinders
  for (double R : {kRout, kRin}) {
    double a = d.x * d.x + d.y * d.y;
    if (a < 1e-12) continue;
    double b = 2.0 * (o.x * d.x + o.y * d.y);
    double cc = o.x * o.x + o.y * o.y - R * R;
    double disc = b * b - 4 * a * cc;
    if (disc < 0) continue;
    double sq = std::sqrt(disc);
    for (int s = 0; s < 2; s++) {
      double t = (s ? (-b + sq) : (-b - sq)) / (2 * a);
      V3 p = o + d * t;
      if (p.z < 0.0 || p.z > kGlassH) continue;
      consider(t, normalize(V3{p.x / R, p.y / R, 0}), 1);
    }
  }
  // water surface inside the glass
  if (std::fabs(d.z) > 1e-12) {
    double t = (kWaterLevel - o.z) / d.z;
    V3 p = o + d * t;
    if (std::hypot(p.x, p.y) < kRin) consider(t, V3{0, 0, 1}, 1);
  }
  // glass top rim
  if (std::fabs(d.z) > 1e-12) {
    double t = (kGlassH - o.z) / d.z;
    V3 p = o + d * t;
    double r = std::hypot(p.x, p.y);
    if (r >= kRin && r <= kRout) consider(t, V3{0, 0, 1}, 1);
  }
  // table plane
  if (std::fabs(d.z) > 1e-12) {
    double t = (0.0 - o.z) / d.z;
    consider(t, V3{0, 0, 1}, 0);
  }
  if (found) {
    kind = best_kind;
    // orient the normal against the travelling ray and label the media
    if (dot(d, nbest) > 0) nbest = nbest * -1.0;
    V3 ahead = o + d * (tbest + 1e-5);
    m_out = medium_at(ahead);
    V3 behind = o + d * (tbest - 1e-5);
    m_in = medium_at(behind);
    if (best_kind == 1 && m_out == m_in) return false;  // grazing dielectric
  }
  return found;
}

bool in_glass_solid(V3 p) {
  double r = std::hypot(p.x, p.y);
  return r <= kRout && p.z >= 0.0 && p.z <= kGlassH;
}

V3 cross3(V3 a, V3 b) {
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}

// deterministic per-sample hash (no RNG state shared across threads)
inline uint32_t hash_u32(uint32_t x) {
  x ^= x >> 16;
  x *= 0x7feb352dU;
  x ^= x >> 15;
  x *= 0x846ca68bU;
  x ^= x >> 16;
  return x;
}
inline double rnd01(uint32_t& s) {
  s = hash_u32(s * 1664525u + 1013904223u);
  return double(s >> 8) * (1.0 / 16777216.0);
}

// Sun irradiance on a surface facing it, and its solid angle.
const double kCosSun = 0.4296;  // cosine of the sun's elevation
// Tuned against the reference photograph's measured statistics, not by eye:
// it measures mean 108 with p25 79 / p75 129 (a wide mid-tone spread) and R-B
// warmth 18.5, so the exposure came down and the palette was neutralised (the
// first pass measured mean 140 and warmth 38.6).
const double kSunE[3] = {19.0, 17.6, 15.8};
const double kSunOmega = kPi * kSunAng * kSunAng;
constexpr double kCausGain = 1.7;
constexpr double kExposure = 0.125;  // scene -> film

// Table surface response: base colour, used by the direct term and the sheen.
void table_albedo(double x, double y, double out[3]);

// ============================================================================
// Wavy water surface inside the glass.
//
// The 1-D invariant model (below, now superseded) assumed a smooth cylinder,
// which yields a smooth straight fan. A real glass of water has a rippling
// surface, and those ripples are what make the caustic turbulent like the
// reference photograph. With waves the pattern is no longer invariant along any
// axis, so the ray map becomes genuinely 2-D: parameters (phi, z0) -> table
// point, and folds are where its Jacobian determinant vanishes.
// ============================================================================
struct WaveParams {
  int n = 4;
  double amp[4] = {0.00065, 0.00040, 0.00025, 0.00015};   // metres
  double lam[4] = {0.042, 0.027, 0.017, 0.011};           // metres
  double dx[4] = {1.0, 0.35, -0.75, 0.6};
  double dy[4] = {0.25, 1.0, 0.55, -0.9};
  double t = 0.0;
};

double water_h(double x, double y, const WaveParams& w) {
  double h = 0;
  for (int i = 0; i < w.n; i++) {
    double nn = std::hypot(w.dx[i], w.dy[i]);
    double ux = w.dx[i] / nn, uy = w.dy[i] / nn;
    double k = 2.0 * kPi / w.lam[i];
    h += w.amp[i] * std::sin(k * (ux * x + uy * y) + w.t * (1.0 + i));
  }
  return h;
}

void water_normal(double x, double y, const WaveParams& w, double eps, V3& out) {
  double hx = (water_h(x + eps, y, w) - water_h(x - eps, y, w)) / (2 * eps);
  double hy = (water_h(x, y + eps, w) - water_h(x, y - eps, w)) / (2 * eps);
  double inv = 1.0 / std::sqrt(1 + hx * hx + hy * hy);
  out = normalize(V3{-hx * inv, -hy * inv, inv});
}

// Extend the 2-D grid with a closest-feature Euclidean distance transform
// (Felzenszwalb-Huttenlocher), same routine as the pool baker.
void edt2d(const std::vector<char>& feat, int N, std::vector<double>& d2out) {
  const double INF = 1e18;
  std::vector<double> tmp((size_t)N * N, INF);
  std::vector<double> fv(N), dv(N), zv(N + 1);
  std::vector<int> vv(N);
  for (int y = 0; y < N; y++) {
    for (int x = 0; x < N; x++) fv[x] = feat[(size_t)y * N + x] ? 0.0 : INF;
    int k = 0;
    vv[0] = 0;
    zv[0] = -INF;
    zv[1] = INF;
    for (int q = 1; q < N; q++) {
      double s = ((fv[q] + double(q * q)) - (fv[vv[k]] + double(vv[k] * vv[k]))) /
                 double(2 * q - 2 * vv[k]);
      while (s <= zv[k] && k > 0) {
        k--;
        s = ((fv[q] + double(q * q)) - (fv[vv[k]] + double(vv[k] * vv[k]))) /
            double(2 * q - 2 * vv[k]);
      }
      k++;
      vv[k] = q;
      zv[k] = s;
      zv[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < N; q++) {
      while (zv[k + 1] < q) k++;
      double dd = double(q - vv[k]);
      dv[q] = dd * dd + fv[vv[k]];
    }
    for (int x = 0; x < N; x++) tmp[(size_t)y * N + x] = dv[x];
  }
  d2out.assign((size_t)N * N, INF);
  for (int x = 0; x < N; x++) {
    for (int y = 0; y < N; y++) fv[y] = tmp[(size_t)y * N + x];
    int k = 0;
    vv[0] = 0;
    zv[0] = -INF;
    zv[1] = INF;
    for (int q = 1; q < N; q++) {
      double s = ((fv[q] + double(q * q)) - (fv[vv[k]] + double(vv[k] * vv[k]))) /
                 double(2 * q - 2 * vv[k]);
      while (s <= zv[k] && k > 0) {
        k--;
        s = ((fv[q] + double(q * q)) - (fv[vv[k]] + double(vv[k] * vv[k]))) /
            double(2 * q - 2 * vv[k]);
      }
      k++;
      vv[k] = q;
      zv[k] = s;
      zv[k + 1] = INF;
    }
    k = 0;
    for (int q = 0; q < N; q++) {
      while (zv[k + 1] < q) k++;
      double dd = double(q - vv[k]);
      d2out[(size_t)q * N + x] = dd * dd + fv[vv[k]];
    }
  }
}

// One ray through the glass of water. Two regimes, both physical:
//
//   z0 below the water line  : wall (air->glass), inner wall (glass->water),
//                              straight through the water to the table. This is
//                              the smooth cylindrical-lens fan.
//   z0 above the water line  : wall (air->glass), inner wall (glass->air), then
//                              the ray falls onto the WAVY water surface
//                              (air->water) and refracts again. This is the
//                              turbulent structure - the part the reference
//                              photograph is full of, and the reason the ray
//                              map has to be 2-D.
//
// (the 3.5 mm glass shell is traversed properly here; only its dispersion is
// folded into the water index)
Hit trace_wavy(double phi, double z0, double n_water, double n_glass, const WaveParams& wp) {
  Hit h{0, 0, 0, false};
  V3 P{kRout * std::cos(phi), kRout * std::sin(phi), z0};
  V3 nw{std::cos(phi), std::sin(phi), 0.0};
  V3 d = normalize(kSun);
  V3 t1;
  if (!snell(d, nw, 1.0 / n_glass, t1)) return h;      // air -> glass
  // to the inner wall
  double a = t1.x * t1.x + t1.y * t1.y;
  if (a < 1e-14) return h;
  double b = 2.0 * (P.x * t1.x + P.y * t1.y);
  double cc = P.x * P.x + P.y * P.y - kRin * kRin;
  double disc = b * b - 4 * a * cc;
  if (disc < 0) return h;
  double sq = std::sqrt(disc);
  double sIn = (-b - sq) / (2 * a);
  if (sIn <= 1e-9) sIn = (-b + sq) / (2 * a);
  if (sIn <= 1e-9) return h;
  V3 W = P + t1 * sIn;
  V3 nIn{W.x / kRin, W.y / kRin, 0.0};                 // outward at the inner wall
  V3 t2;

  if (W.z < kWaterLevel) {
    // glass -> water, then straight to the table.
    // The ray is still travelling INWARD here, so the normal facing it is the
    // OUTWARD one (+nIn). Using the inward normal made snell() reject every ray
    // and the whole field came out empty.
    if (!snell(t1, nIn, n_glass / n_water, t2)) return h;
    if (t2.z >= -1e-9) return h;
    double drop = -W.z / t2.z;
    h.x = W.x + t2.x * drop;
    h.y = W.y + t2.y * drop;
    h.ok = true;
    return h;
  }
  // glass -> air, then fall onto the rippling surface
  if (!snell(t1, nIn, n_glass / 1.0, t2)) return h;
  if (t2.z >= -1e-9) return h;
  double s = (kWaterLevel - W.z) / t2.z;
  if (s <= 0) return h;
  V3 S = W + t2 * s;
  for (int it = 0; it < 2; it++) {                     // fixed point on the surface height
    double zw = kWaterLevel + water_h(S.x, S.y, wp);
    s = (zw - W.z) / t2.z;
    if (s <= 0) return h;
    S = W + t2 * s;
  }
  if (std::hypot(S.x, S.y) > kRin) return h;           // leaves through the wall
  V3 n2;
  water_normal(S.x, S.y, wp, 2e-5, n2);
  V3 t3;
  if (!snell(t2, n2, 1.0 / n_water, t3)) return h;     // air -> water
  if (t3.z >= -1e-9) return h;
  double drop = -S.z / t3.z;
  h.x = S.x + t3.x * drop;
  h.y = S.y + t3.y * drop;
  h.ok = true;
  return h;
}

Field build_caustic_wavy(int N, double airy_scale, const WaveParams& wp) {
  const double lambdas[3] = {650.0, 550.0, 450.0};
  Field f;
  f.N = N;
  f.rgb.assign((size_t)N * N * 3, 0.0f);

  const int NP = 420;   // samples around the wall
  const int NZ = 260;   // samples up the wall
  const double dz0 = kGlassH / NZ;
  const double dphi = 2.0 * kPi / NP;
  const double dxg = 2.0 * kExt / N;

  for (int c = 0; c < 3; c++) {
    double nw = water_index(lambdas[c]);
    double ng = glass_index(lambdas[c]);
    std::vector<double> flux((size_t)N * N, 0.0);
    std::vector<char> fold((size_t)N * N, 0);
    // pass 1: ray map, Jacobian, splat
    std::vector<double> jac((size_t)N * N, 1e30);
    for (int i = 0; i < NP; i++) {
      double phi = (i + 0.5) * dphi;
      for (int j = 0; j < NZ; j++) {
        double z0 = (j + 0.5) * dz0;
        Hit h0 = trace_wavy(phi, z0, nw, ng, wp);
        if (!h0.ok) continue;
        Hit hp = trace_wavy(phi + 1e-5, z0, nw, ng, wp);
        Hit hm = trace_wavy(phi - 1e-5, z0, nw, ng, wp);
        Hit hu = trace_wavy(phi, z0 + 1e-5, nw, ng, wp);
        Hit hd = trace_wavy(phi, z0 - 1e-5, nw, ng, wp);
        double jdet = 1e30;
        if (hp.ok && hm.ok && hu.ok && hd.ok) {
          double dxdphi = (hp.x - hm.x) / 2e-5, dydphi = (hp.y - hm.y) / 2e-5;
          double dxdz = (hu.x - hd.x) / 2e-5, dydz = (hu.y - hd.y) / 2e-5;
          jdet = std::fabs(dxdphi * dydz - dxdz * dydphi);
        }
        double wgt = (jdet > 1e-12) ? 1.0 / jdet : 0.0;
        double fx = (h0.x + kExt) / (2 * kExt) * N - 0.5;
        double fy = (h0.y + kExt) / (2 * kExt) * N - 0.5;
        int x0 = int(std::floor(fx)), y0 = int(std::floor(fy));
        double ax = fx - x0, ay = fy - y0;
        for (int oy = 0; oy <= 1; oy++)
          for (int ox = 0; ox <= 1; ox++) {
            int xx = x0 + ox, yy = y0 + oy;
            if (xx < 0 || xx >= N || yy < 0 || yy >= N) continue;
            flux[(size_t)yy * N + xx] += (ox ? ax : 1 - ax) * (oy ? ay : 1 - ay) * wgt;
          }
        int cx = std::clamp(x0, 0, N - 1), cy = std::clamp(y0, 0, N - 1);
        jac[(size_t)cy * N + cx] = std::min(jac[(size_t)cy * N + cx], jdet);
      }
    }
    double mean = 0;
    for (double v : flux) mean += v;
    mean /= double(N) * double(N);
    if (mean <= 0) mean = 1e-12;
    for (double& v : flux) v /= mean;

    // pass 2: fold locus = |det J| far below the typical compression
    std::vector<double> js;
    js.reserve((size_t)N * N);
    for (double v : jac)
      if (v < 1e29) js.push_back(v);
    if (!js.empty()) {
      std::sort(js.begin(), js.end());
      double thr = 0.10 * js[js.size() / 2];
      for (int i = 0; i < N * N; i++) fold[i] = jac[i] < thr;
    }
    // pass 3: distance to the fold, then the Airy replacement (band-local flux)
    std::vector<double> d2;
    edt2d(fold, N, d2);
    const double cap = kCapAiry;
    const double w = airy_scale * std::pow(lambdas[c] / 550.0, 2.0 / 3.0);
    std::vector<double> sm((size_t)N * N, 0.0);
    for (int y = 0; y < N; y++)
      for (int x = 0; x < N; x++) {
        double a = 0;
        int k = 0;
        for (int dy = -2; dy <= 2; dy++)
          for (int dx = -2; dx <= 2; dx++) {
            int xx = std::clamp(x + dx, 0, N - 1), yy = std::clamp(y + dy, 0, N - 1);
            a += flux[(size_t)yy * N + xx];
            k++;
          }
        sm[(size_t)y * N + x] = a / k;
      }
    double want = 0, got = 0;
    for (int i = 0; i < N * N; i++) {
      double s = std::sqrt(d2[i]) * dxg;
      if (s < 5 * w) {
        want += flux[i];
        got += std::min(sm[i], cap) * (0.15 + 0.85 * airy_prof_1d(s / w));
      }
    }
    double kk = got > 0 ? want / got : 0.0;
    for (int i = 0; i < N * N; i++) {
      double s = std::sqrt(d2[i]) * dxg;
      double v = flux[i];
      if (s < 5 * w) {
        double base = std::min(sm[i], cap);
        v = std::min(base * (0.15 + 0.85 * airy_prof_1d(s / w)) * kk, cap * 1.35);
      }
      f.rgb[(size_t)i * 3 + c] = float(std::min(v, cap * 1.35));
    }
  }
  return f;
}

// ============================================================================
}  // namespace

int main(int argc, char** argv) {
  int W = 1600, R = 1024, ssaa = 2;
  // 0.0015 m: chosen by measurement, not taste. tools/airy_scale_sweep.py
  // scores candidate scales against a Cycles render of the same scene; at
  // 0.006 the caustic centroid sat 10.0 mm from the path-traced one, at
  // 0.0015 only 5.1 mm. 0.0006 is no better and breaks the >= 3 px per
  // fringe rule at the 1024^2 bake (0.6 mm ~ 2 px).
  double airy = 0.0015;
  std::string out = "out/showcase.png";
  std::string dump_caustic;
  bool flat = false;
  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    if (a == "--n" && i + 1 < argc) W = std::atoi(argv[++i]);
    else if (a == "--res" && i + 1 < argc) R = std::atoi(argv[++i]);
    else if (a == "--airy" && i + 1 < argc) airy = std::atof(argv[++i]);
    else if (a == "--ssaa" && i + 1 < argc) ssaa = std::atoi(argv[++i]);
    else if (a == "--out" && i + 1 < argc) out = argv[++i];
    else if (a == "--dump-caustic" && i + 1 < argc) dump_caustic = argv[++i];
    else if (a == "--flat") flat = true;
  }
  const int H = int(W * 0.625);

  std::printf("[showcase] %dx%d, caustic grid %d^2, airy_scale %.4f, %dx SSAA\n", W, H, R, airy,
              ssaa);
  double t0 = 0;
  (void)t0;

  Field f = flat ? build_caustic(R, airy) : build_caustic_wavy(R, airy, WaveParams{});

  // report the caustic + dispersion metrics so the image is checked, not assumed
  double peak[3] = {0, 0, 0};
  double sum[3] = {0, 0, 0};
  for (int i = 0; i < R * R; i++)
    for (int c = 0; c < 3; c++) {
      double v = f.rgb[(size_t)i * 3 + c];
      peak[c] = std::max(peak[c], v);
      sum[c] += v;
    }
  double rb_spread = 0, mean_all = 0;
  for (int i = 0; i < R * R; i++) {
    double r = f.rgb[(size_t)i * 3 + 0], b = f.rgb[(size_t)i * 3 + 2];
    rb_spread += std::fabs(r - b);
    mean_all += 0.5 * (r + b);
  }
  rb_spread /= double(R) * R;
  mean_all /= double(R) * R;
  std::printf("[caustic] peaks R/G/B = %.3f / %.3f / %.3f   means = %.3f / %.3f / %.3f\n",
              peak[0], peak[1], peak[2], sum[0] / (R * R), sum[1] / (R * R), sum[2] / (R * R));
  std::printf("[caustic] mean |R-B| = %.4f  (%.2f%% of field mean %.3f)  "
              "-> dispersion %s\n",
              rb_spread, 100.0 * rb_spread / std::max(mean_all, 1e-9), mean_all,
              (rb_spread > 0.05 * mean_all) ? "VISIBLE" : "too weak");

  if (!dump_caustic.empty()) {
    // Hand the field to Blender: 16-bit, linear, scaled by 1/16 (the display cap
    // is 8.1), row 0 = +Y so it lines up with a plane whose UV v=1 edge is +Y.
    // Load it as Non-Color and multiply by 16 in the shader.
    std::vector<uint16_t> img16((size_t)R * R * 3);
    for (int y = 0; y < R; y++)
      for (int x = 0; x < R; x++) {
        int sy = R - 1 - y;
        for (int c = 0; c < 3; c++) {
          double v = double(f.rgb[((size_t)idx(R, x, sy)) * 3 + c]) / 16.0;
          img16[((size_t)y * R + x) * 3 + c] =
              uint16_t(std::clamp(v * 65535.0, 0.0, 65535.0));
        }
      }
    if (write_png16(dump_caustic.c_str(), R, R, img16))
      std::printf("[caustic] wrote %s (%dx%d, 16-bit linear/16, row 0 = +Y)\n",
                  dump_caustic.c_str(), R, R);
    else
      std::printf("[caustic] FAILED to write %s\n", dump_caustic.c_str());
  }

  // ---- camera: auto-framed on the caustic so the fan always fits ----
  double cx = 0, cy = 0, wsum = 0, maxr = 0;
  for (int i = 0; i < R * R; i++) {
    double v = f.rgb[(size_t)i * 3 + 1];
    if (v <= 1.2) continue;
    int x = i % R, y = i / R;
    double px = (double(x) / (R - 1) - 0.5) * 2 * kExt;
    double py = (double(y) / (R - 1) - 0.5) * 2 * kExt;
    cx += px * v;
    cy += py * v;
    wsum += v;
  }
  if (wsum > 0) {
    cx /= wsum;
    cy /= wsum;
  }
  for (int i = 0; i < R * R; i++) {
    double v = f.rgb[(size_t)i * 3 + 1];
    if (v <= 1.2) continue;
    int x = i % R, y = i / R;
    double px = (double(x) / (R - 1) - 0.5) * 2 * kExt;
    double py = (double(y) / (R - 1) - 0.5) * 2 * kExt;
    maxr = std::max(maxr, std::hypot(px - cx, py - cy));
  }
  std::printf("[frame] caustic centroid (%.4f, %.4f), extent %.4f m\n", cx, cy, maxr);

  const V3 eyeDir = normalize(V3{-0.45, -0.78, 0.44});   // above, looking down-table
  // Frame the glass AND the fan together (the reference photograph shows both):
  // aim between them and pull back far enough for the glass to read as a glass
  // rather than filling the frame. At dist = extent*2.6 the glass covered 61%
  // of the image; this puts it near 15%.
  const V3 target{cx * 0.55, cy * 0.55, kGlassH * 0.45};
  double dist = std::clamp(maxr * 2.4, 0.20, 0.32);
  const V3 eye = target + eyeDir * dist;
  const V3 fwd = normalize(target - eye);
  const V3 rgt = normalize(V3{fwd.y, -fwd.x, 0});
  const V3 up = V3{rgt.y * fwd.z - rgt.z * fwd.y, rgt.z * fwd.x - rgt.x * fwd.z,
                   rgt.x * fwd.y - rgt.y * fwd.x};
  const double fov = 38.0 * kPi / 180.0;
  const double tanf = std::tan(fov * 0.5);

  std::vector<uint8_t> img((size_t)W * H * 3);
  const double kLambdas[3] = {650.0, 550.0, 450.0};
  const double focus_d = std::max(1e-3, dot(target - eye, fwd));
  constexpr double kAperture = 0.0009;  // subtle background falloff, glass stays sharp

  auto cylinder_blocked = [](V3 o, V3 d) {
    double a = d.x * d.x + d.y * d.y;
    if (a < 1e-12) return false;
    double b = 2.0 * (o.x * d.x + o.y * d.y);
    double cc = o.x * o.x + o.y * o.y - kRout * kRout;
    double disc = b * b - 4 * a * cc;
    if (disc < 0) return false;
    double sq = std::sqrt(disc);
    for (int s = 0; s < 2; s++) {
      double t = (s ? (-b + sq) : (-b - sq)) / (2 * a);
      if (t <= 1e-6) continue;
      V3 q = o + d * t;
      if (q.z >= 0.0 && q.z <= kGlassH) return true;
    }
    return false;
  };

  // Full transport for one sample. The air | glass | water stack is walked with
  // Fresnel at every crossing, so the background is genuinely refracted and the
  // rim highlights and chromatic separation come out of the transport rather
  // than being painted on. One walk per channel, since n depends on lambda.
  auto shade = [&](V3 ro, V3 rd, uint32_t seed, double rad[3], int* cnt) {
    for (int c = 0; c < 3; c++) {
      double tp = 1.0;
      V3 o = ro, d = rd;
      double sum = 0.0;
      for (int step = 0; step < 10; step++) {
        double t;
        V3 p, n;
        int mi, mo, kind = -1;
        if (!next_crossing(o, d, 1e-5, t, p, n, mi, mo, kind)) {
          double e[3];
          env_color(d, e);
          sum += tp * e[c];
          break;
        }
        if (step == 0 && kind == 1 && cnt) cnt[0]++;  // camera ray entered a dielectric
        if (kind == 0) {
          // ------------------------------ table ------------------------------
          double alb[3];
          table_albedo(p.x, p.y, alb);
          double cosT = std::clamp(-d.z, 0.0, 1.0);
          const int NS = 6;
          double vis = 0;
          for (int s = 0; s < NS; s++) {
            V3 sd;
            sun_dir_sample(s, NS, sd);
            if (!cylinder_blocked(p, sd)) vis += 1.0;
          }
          vis /= NS;
          if (vis < 0.5 && cnt) cnt[1]++;
          double caus = (std::fabs(p.x) < kExt && std::fabs(p.y) < kExt)
                            ? double(sample_field(f, p.x, p.y, c))
                            : 0.0;
          if (caus > 1.5 && cnt) cnt[2]++;
          if (cnt) {
            cnt[3]++;  // table samples
            if (caus > cnt[4] * 1.0) cnt[4] = int(caus * 1000.0);  // max caus x1000
          }
          // rough-specular sheen: jitter the reflection, pick up sky or glass
          V3 rf = reflect_dir(d, V3{0, 0, 1});
          double ja = 2.0 * kPi * rnd01(seed);
          double jr = 0.30 * std::sqrt(rnd01(seed));
          V3 t1 = normalize(cross3(rf, V3{0, 0, 1}));
          V3 t2 = cross3(rf, t1);
          V3 rj = normalize(rf + t1 * (jr * std::cos(ja)) + t2 * (jr * std::sin(ja)));
          double fv = schlick(0.035, cosT);
          double e2[3];
          env_color(rj, e2);
          double sheen = fv * e2[c];
          if (cylinder_blocked(p, rj)) sheen += fv * 9.0;  // glint off the glass
          double amb[3];
          env_color(V3{0, 0, 1}, amb);
          sum += tp * (alb[c] / kPi * kSunE[c] * kCosSun * vis + alb[c] * amb[c] * 0.12 +
                       caus * kCausGain * (0.35 + 0.85 * vis) + sheen * (0.5 + 0.7 * vis));
          break;
        }
        // ------------------------ dielectric interface ------------------------
        double n1 = medium_index(mi, kLambdas[c]);
        double n2 = medium_index(mo, kLambdas[c]);
        double eta = n1 / n2;
        double cosi = std::clamp(-dot(d, n), 0.0, 1.0);
        double F = fresnel_dielectric(cosi, eta);
        V3 rr = reflect_dir(d, n);
        double e[3];
        env_color(rr, e);
        sum += tp * F * e[c];
        // mirror-smooth glass shows the sun disk itself: the blown glint
        if (dot(rr, normalize(kSunTo)) > std::cos(kSunAng))
          sum += tp * F * kSunE[c] / kSunOmega;
        V3 rt;
        if (!refract_dir(d, n, eta, rt)) {  // total internal reflection
          o = p + rr * 1e-6;
          d = rr;
          continue;
        }
        double ab[3];
        medium_absorb(mi, t, ab);
        tp *= (1.0 - F) * ab[c];
        o = p + rt * 1e-6;
        d = rt;
      }
      rad[c] = sum;
    }
  };

  int nt = 8;
  if (const char* env = std::getenv("CAUSTIC_THREADS")) {
    int v = std::atoi(env);
    if (v > 0) nt = v;
  }
  nt = std::clamp(nt, 1, 32);
  std::vector<int> counters(size_t(nt) * 5, 0);  // glass, shadow, caustic, table, max caus

  auto render_rows = [&](int tid, int y0, int y1) {
    int* cnt = &counters[size_t(tid) * 5];
    for (int py = y0; py < y1; py++)
      for (int px = 0; px < W; px++) {
        double acc[3] = {0, 0, 0};
        for (int sy = 0; sy < ssaa; sy++)
          for (int sx = 0; sx < ssaa; sx++) {
            double u = (2.0 * (px + (sx + 0.5) / ssaa) / W - 1.0) * tanf * (double(W) / H);
            double v = (1.0 - 2.0 * (py + (sy + 0.5) / ssaa) / H) * tanf;
            V3 dir = normalize(fwd + rgt * u + up * v);
            uint32_t seed = uint32_t(px * 1973 + py * 9277 + sx * 2663 + sy * 1013 + 1);
            // thin-lens depth of field
            double lr = kAperture * std::sqrt(rnd01(seed));
            double la = 2.0 * kPi * rnd01(seed);
            V3 o = eye + rgt * (lr * std::cos(la)) + up * (lr * std::sin(la));
            V3 focal = eye + dir * focus_d;
            V3 d2 = normalize(focal - o);
            double rad[3];
            shade(o, d2, seed, rad, cnt);
            for (int c = 0; c < 3; c++) acc[c] += rad[c];
          }
        double inv = 1.0 / (ssaa * ssaa);
        double vx = double(px) / W - 0.5, vy = double(py) / H - 0.5;
        // stronger falloff: the reference spreads p25 79 -> p75 129 across the
        // frame (a lit table falling into shadow), our first pass only spanned
        // 134 -> 155
        double vig = 1.0 - 0.46 * std::pow(std::clamp(std::hypot(vx, vy) * 1.42, 0.0, 1.0), 2.0);
        for (int c = 0; c < 3; c++) {
          double x = std::max(0.0, acc[c] * inv) * vig * kExposure;
          // ACES-style filmic curve: the per-channel shoulder rolls highlights off
          // instead of clipping them, which is what keeps the fan's colour.
          const double a = 2.51, b = 0.03, cc2 = 2.43, dd = 0.59, ee = 0.14;
          double m = (x * (a * x + b)) / (x * (cc2 * x + dd) + ee);
          m = std::pow(std::clamp(m, 0.0, 1.0), 1.0 / 2.2);
          img[((size_t)py * W + px) * 3 + c] = uint8_t(std::clamp(m, 0.0, 1.0) * 255.0);
        }
      }
  };

  {
    std::vector<std::thread> pool;
    int chunk = (H + nt - 1) / nt;
    int tid = 0;
    for (int y0 = 0; y0 < H; y0 += chunk) {
      int y1 = std::min(H, y0 + chunk);
      pool.emplace_back([&, tid, y0, y1] { render_rows(tid, y0, y1); });
      tid++;
    }
    for (auto& th : pool) th.join();
  }
  int shadow_px = 0, glass_px = 0, caustic_px = 0, table_px = 0, max_caus = 0;
  for (int i = 0; i < nt; i++) {
    glass_px += counters[size_t(i) * 5 + 0];
    shadow_px += counters[size_t(i) * 5 + 1];
    caustic_px += counters[size_t(i) * 5 + 2];
    table_px += counters[size_t(i) * 5 + 3];
    max_caus = std::max(max_caus, counters[size_t(i) * 5 + 4]);
  }
  std::printf("[diag] samples: glass %d, table %d, shadow %d, caustic %d, max caus %.3f\n",
              glass_px, table_px, shadow_px, caustic_px, max_caus / 1000.0);
  if (write_png(out.c_str(), W, H, img)) {
    std::printf("[ok] wrote %s (%dx%d)\n", out.c_str(), W, H);
  } else {
    std::printf("[fail] could not write %s\n", out.c_str());
    return 1;
  }
  const double inv_samples = 1.0 / (double(ssaa) * ssaa);
  std::printf("[stats] glass pixels %.2f%%, shadow pixels %.2f%%, caustic pixels %.2f%%\n",
              100.0 * glass_px * inv_samples / (double(W) * H),
              100.0 * shadow_px * inv_samples / (double(W) * H),
              100.0 * caustic_px * inv_samples / (double(W) * H));
  return 0;
}
