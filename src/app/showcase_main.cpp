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
  double k = 0.72 + 0.38 * grain - 0.10 * fibre;
  r = 0.60 * k;
  g = 0.48 * k;
  b = 0.36 * k;
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

}  // namespace

int main(int argc, char** argv) {
  int W = 1600, R = 1024, ssaa = 2;
  double airy = 0.006;
  std::string out = "out/showcase.png";
  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    if (a == "--n" && i + 1 < argc) W = std::atoi(argv[++i]);
    else if (a == "--res" && i + 1 < argc) R = std::atoi(argv[++i]);
    else if (a == "--airy" && i + 1 < argc) airy = std::atof(argv[++i]);
    else if (a == "--ssaa" && i + 1 < argc) ssaa = std::atoi(argv[++i]);
    else if (a == "--out" && i + 1 < argc) out = argv[++i];
  }
  const int H = int(W * 0.625);

  std::printf("[showcase] %dx%d, caustic grid %d^2, airy_scale %.4f, %dx SSAA\n", W, H, R, airy,
              ssaa);
  double t0 = 0;
  (void)t0;

  Field f = build_caustic(R, airy);

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
  const V3 sunD = normalize(kSun);
  int shadow_px = 0, glass_px = 0, caustic_px = 0;

  for (int py = 0; py < H; py++) {
    for (int px = 0; px < W; px++) {
      double acc[3] = {0, 0, 0};
      for (int sy = 0; sy < ssaa; sy++)
        for (int sx = 0; sx < ssaa; sx++) {
          double u = (2.0 * (px + (sx + 0.5) / ssaa) / W - 1.0) * tanf * (double(W) / H);
          double v = (1.0 - 2.0 * (py + (sy + 0.5) / ssaa) / H) * tanf;
          V3 dir = normalize(fwd + rgt * u + up * v);

          // --- glass body -------------------------------------------------
          // intersect with the finite cylinder (radius kGlassR, z in [0,H])
          double ox = eye.x, oy = eye.y;
          double a = dir.x * dir.x + dir.y * dir.y;
          double b2 = 2.0 * (ox * dir.x + oy * dir.y);
          double cc = ox * ox + oy * oy - kGlassR * kGlassR;
          double disc = b2 * b2 - 4 * a * cc;
          bool drew_glass = false;
          if (disc > 0 && a > 1e-12) {
            double sq = std::sqrt(disc);
            for (int sgn = 0; sgn < 2; sgn++) {
              double t = (sgn ? (-b2 + sq) : (-b2 - sq)) / (2 * a);
              if (t < 1e-4) continue;
              V3 p = eye + dir * t;
              if (p.z < 0 || p.z > kGlassH) continue;
              // shade: dark body + vertical streaks + rim + water line
              double az = std::atan2(p.y, p.x);
              double streak = 0;
              for (int k = 0; k < 3; k++)
                streak = std::max(streak, std::pow(std::max(0.0, std::cos(az * 1.0 +
                                    k * 2.1 - 0.6)), 24.0));
              double fres = 0.04 + 0.96 * std::pow(1.0 - std::fabs(dot(normalize(dir),
                                       normalize(V3{p.x, p.y, 0}))), 5.0);
              double body = 0.05 + 0.30 * fres + 0.55 * streak;
              bool water = (p.z < kGlassH * kFill);
              if (water) body *= 0.85;
              // rim: near the top edge, and the meniscus line
              double rim = (p.z > kGlassH - 0.002) ? 0.45 : 0.0;
              double men = (std::fabs(p.z - kGlassH * kFill) < 0.0015) ? -0.10 : 0.0;
              double g = std::clamp(body + rim + men, 0.0, 1.0);
              V3 nd = normalize(V3{p.x, p.y, 0});
              double lit = std::max(0.0, -dot(sunD, nd));
              acc[0] += g * (0.75 + 0.55 * lit);
              acc[1] += g * (0.80 + 0.55 * lit);
              acc[2] += g * (0.92 + 0.55 * lit);
              drew_glass = true;
              break;
            }
          }
          if (drew_glass) {
            glass_px++;
            continue;
          }

          // --- table plane z = 0 -----------------------------------------
          if (dir.z >= -1e-9) {
            acc[0] += 0.02; acc[1] += 0.02; acc[2] += 0.03;  // background
            continue;
          }
          double tt = -eye.z / dir.z;
          if (tt <= 0) {
            acc[0] += 0.02; acc[1] += 0.02; acc[2] += 0.03;
            continue;
          }
          V3 P = eye + dir * tt;
          double wr, wg, wb;
          wood(P.x, P.y, wr, wg, wb);

          // caustic + direct light, with the glass shadow
          double caus[3] = {0, 0, 0};
          if (std::fabs(P.x) < kExt && std::fabs(P.y) < kExt) {
            for (int c = 0; c < 3; c++) caus[c] = sample_field(f, P.x, P.y, c);
          }
          // soft shadow: sample the light as a small disk by nudging the point
          double cover = 0;
          const int SK = 5;
          for (int k = 0; k < SK; k++) {
            double a2 = 2.0 * kPi * k / SK;
            double rx = P.x + 0.004 * std::cos(a2), ry = P.y + 0.004 * std::sin(a2);
            cover += in_shadow(rx, ry) ? 1.0 : 0.0;
          }
          cover /= SK;
          if (cover > 0.5) shadow_px++;
          double direct = 1.0 - cover;
          double amb = 0.10;  // bounce light under the table shadow
          double caus_vis = (1.0 - 0.55 * cover);
          if (caus[1] > 1.5) caustic_px++;
          // distance falloff from the glass: without it the parallel-light table
          // is uniformly lit and the frame reads flat
          double rr = std::hypot(P.x, P.y);
          double fall = 1.0 / (1.0 + std::pow(rr / 0.26, 2.0));
          double gainT = (amb + 0.95 * direct) * (0.35 + 1.05 * fall);
          const double alb[3] = {wr, wg, wb};
          // The caustic is composited as an ADDITIVE light with a soft per-channel
          // knee (1 - exp(-k*I)) instead of being added linearly and then
          // tonemapped. Linear-add + Reinhard blew every channel of the fan to
          // white, which is why the dispersion measured 6.65% in the field and
          // 0.02% in the image: the colour was in the clipping, not the physics.
          for (int c = 0; c < 3; c++) {
            double t = alb[c] * gainT;
            double td = std::pow(t / (1.0 + t), 1.0 / 2.2);
            double cd = 1.0 - std::exp(-caus[c] * 0.45 * caus_vis);
            acc[c] += std::min(td + cd, 1.0);
          }
        }
      double inv = 1.0 / (ssaa * ssaa);
      for (int c = 0; c < 3; c++) {
        // shading already returns display-space values, so only average + quantise
        double m = std::clamp(acc[c] * inv, 0.0, 1.0);
        img[((size_t)py * W + px) * 3 + c] = uint8_t(m * 255.0);
      }
    }
  }
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
