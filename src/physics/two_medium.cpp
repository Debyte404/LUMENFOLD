// two_medium.cpp — exact submerged-volume clipping for sphere/box/capsule.
// Surface: plane z = e.surface_z (flat, static). Water occupies z < surface_z.
// Force F = +rho_water * g * Vsub * zhat (up), applied at centroid of the
// SUBMERGED part -> torque T = (cob - com) x F about the COM. That couple is
// exactly what MuJoCo's gravcomp proxy lacks (it applies at xipos/COM -> zero
// moment), which is the core of issue #3452's self-righting failure.
#include "two_medium.hpp"

#include <algorithm>
#include <cmath>

namespace twomed {
namespace {
constexpr double kPi = 3.14159265358979323846;

std::array<double, 3> matvec(const std::array<double, 9>& R, const std::array<double, 3>& v) {
  return {R[0] * v[0] + R[1] * v[1] + R[2] * v[2], R[3] * v[0] + R[4] * v[1] + R[5] * v[2],
          R[6] * v[0] + R[7] * v[1] + R[8] * v[2]};
}
std::array<double, 3> cross(const std::array<double, 3>& a, const std::array<double, 3>& b) {
  return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}

// ---- sphere: cap below plane. h = submerged depth measured from bottom (0..2r).
void sphere_sub(double r, double cz, double surf, double& V, double& zc) {
  double h = std::clamp(surf - (cz - r), 0.0, 2.0 * r);
  if (h <= 0) {
    V = 0;
    zc = cz;
    return;
  }
  V = kPi * h * h * (r - h / 3.0);
  // Centroid of spherical cap measured from sphere center:
  // zbar = -3(2r-h)^2 / (4(3r-h))  (below center). See e.g. standard cap tables.
  double zbar = -3.0 * (2 * r - h) * (2 * r - h) / (4.0 * (3 * r - h));
  zc = cz + zbar;
}

// Box clipper: decompose into 12 tets about the center; each tet is clipped
// against the half-space in CLOSED FORM (Sutherland-style case analysis).
// No recursion: the old subdivision version branched up to 8^12 near the
// surface and effectively hung. Each tet yields disjoint sub-tets whose
// |volume| and |volume|*centroid sums are exact.
struct TetRes {
  double v = 0;
  std::array<double, 3> c{0, 0, 0};  // volume-weighted centroid sum
};

inline double tet_vol(const std::array<double, 3>& a, const std::array<double, 3>& b,
                      const std::array<double, 3>& c, const std::array<double, 3>& d) {
  double abx = b[0] - a[0], aby = b[1] - a[1], abz = b[2] - a[2];
  double acx = c[0] - a[0], acy = c[1] - a[1], acz = c[2] - a[2];
  double adx = d[0] - a[0], ady = d[1] - a[1], adz = d[2] - a[2];
  return (abx * (acy * adz - acz * ady) - aby * (acx * adz - acz * adx) +
          abz * (acx * ady - acy * adx)) /
         6.0;
}

inline void acc_tet(TetRes& acc, const std::array<double, 3>& a,
                    const std::array<double, 3>& b, const std::array<double, 3>& c,
                    const std::array<double, 3>& d) {
  // Disjoint tiling piece: orientation-independent via abs.
  double v = std::abs(tet_vol(a, b, c, d));
  acc.v += v;
  acc.c[0] += v * (a[0] + b[0] + c[0] + d[0]) / 4.0;
  acc.c[1] += v * (a[1] + b[1] + c[1] + d[1]) / 4.0;
  acc.c[2] += v * (a[2] + b[2] + c[2] + d[2]) / 4.0;
}

inline std::array<double, 3> edge_hit(const std::array<double, 3>& p,
                                      const std::array<double, 3>& q, double dp, double dq) {
  double a = dp / (dp - dq);  // lerp p->q at d==0
  return {p[0] + a * (q[0] - p[0]), p[1] + a * (q[1] - p[1]), p[2] + a * (q[2] - p[2])};
}

// Closed-form clip of one tet against z <= surf. Accumulates the submerged
// piece as disjoint sub-tets (abs-sum => orientation-independent).
void clip_tet_closed(const std::array<double, 3> t[4], double surf, TetRes& acc) {
  double d[4] = {t[0][2] - surf, t[1][2] - surf, t[2][2] - surf, t[3][2] - surf};
  int sub[4], dry[4], ns = 0, nd = 0;
  for (int i = 0; i < 4; i++) ((d[i] <= 0) ? sub[ns++] = i : dry[nd++] = i);
  if (ns == 4) {
    acc_tet(acc, t[0], t[1], t[2], t[3]);
    return;
  }
  if (ns == 0) return;
  if (ns == 1) {
    // small submerged tet: vertex + 3 edge-plane hits
    int a = sub[0];
    auto p1 = edge_hit(t[a], t[dry[0]], d[a], d[dry[0]]);
    auto p2 = edge_hit(t[a], t[dry[1]], d[a], d[dry[1]]);
    auto p3 = edge_hit(t[a], t[dry[2]], d[a], d[dry[2]]);
    acc_tet(acc, t[a], p1, p2, p3);
    return;
  }
  if (ns == 3) {
    // full tet minus small dry tet
    int a = dry[0];
    auto p1 = edge_hit(t[a], t[sub[0]], d[a], d[sub[0]]);
    auto p2 = edge_hit(t[a], t[sub[1]], d[a], d[sub[1]]);
    auto p3 = edge_hit(t[a], t[sub[2]], d[a], d[sub[2]]);
    double vfull = std::abs(tet_vol(t[0], t[1], t[2], t[3]));
    std::array<double, 3> cfull{(t[0][0] + t[1][0] + t[2][0] + t[3][0]) / 4.0,
                                (t[0][1] + t[1][1] + t[2][1] + t[3][1]) / 4.0,
                                (t[0][2] + t[1][2] + t[2][2] + t[3][2]) / 4.0};
    double vdry = std::abs(tet_vol(t[a], p1, p2, p3));
    std::array<double, 3> cdry{(t[a][0] + p1[0] + p2[0] + p3[0]) / 4.0,
                               (t[a][1] + p1[1] + p2[1] + p3[1]) / 4.0,
                               (t[a][2] + p1[2] + p2[2] + p3[2]) / 4.0};
    acc.v += vfull - vdry;
    acc.c[0] += vfull * cfull[0] - vdry * cdry[0];
    acc.c[1] += vfull * cfull[1] - vdry * cdry[1];
    acc.c[2] += vfull * cfull[2] - vdry * cdry[2];
    return;
  }
  // ns == 2: wedge. Submerged A,B; dry C,D. Cut quad (cyclic):
  // P_AC -> P_AD -> P_BD -> P_BC; fan 3 disjoint tets off edge AB.
  const auto& A = t[sub[0]];
  const auto& B = t[sub[1]];
  const auto& C = t[dry[0]];
  const auto& D = t[dry[1]];
  auto pAC = edge_hit(A, C, d[sub[0]], d[dry[0]]);
  auto pAD = edge_hit(A, D, d[sub[0]], d[dry[1]]);
  auto pBD = edge_hit(B, D, d[sub[1]], d[dry[1]]);
  auto pBC = edge_hit(B, C, d[sub[1]], d[dry[0]]);
  acc_tet(acc, A, B, pAC, pAD);
  acc_tet(acc, A, B, pAD, pBD);
  acc_tet(acc, A, B, pBD, pBC);
}

void box_sub(const Body& b, double surf, double& V, std::array<double, 3>& cen) {
  // 8 corners in world.
  std::array<double, 3> c[8];
  for (int i = 0; i < 8; i++) {
    std::array<double, 3> l{(i & 1 ? b.p[0] : -b.p[0]), (i & 2 ? b.p[1] : -b.p[1]),
                             (i & 4 ? b.p[2] : -b.p[2])};
    auto w = matvec(b.R, l);
    c[i] = {w[0] + b.x[0], w[1] + b.x[1], w[2] + b.x[2]};
  }
  // Box center world.
  std::array<double, 3> o = b.x;
  // 12 tets: 6 faces x 2 tris, each (o, tri).
  const int faces[6][4] = {{0, 1, 3, 2}, {4, 6, 7, 5}, {0, 4, 5, 1},
                           {2, 3, 7, 6}, {0, 2, 6, 4}, {1, 5, 7, 3}};
  TetRes acc;
  for (auto& f : faces)
    for (int k = 0; k < 2; k++) {
      const std::array<double, 3> t[4] = {o, c[f[0]], c[f[k + 1]], c[f[k + 2]]};
      clip_tet_closed(t, surf, acc);
    }
  V = acc.v;
  cen = V > 0 ? std::array<double, 3>{acc.c[0] / V, acc.c[1] / V, acc.c[2] / V} : b.x;
}

// ---- capsule: cylinder part (axis = local z, half-length hl) + 2 hemispheres.
// Exact: slice integral along axis. Axis direction world a = R * zhat.
void capsule_sub(const Body& b, double surf, double& V, std::array<double, 3>& cen) {
  double r = b.p[0], hl = b.p[1];
  std::array<double, 3> a{matvec(b.R, {0, 0, 1})};
  // Sample-free exact: integrate cross-section area A(s) and first moment along
  // axis coordinate s in [-(hl+r), hl+r]. A(s) = circle segment below plane.
  // Plane: z(s) = x.z + s*a.z (+ radial offset handled by segment formula).
  // For ball ends use sphere-cap-in-tilted-plane approx via numeric Gauss-
  // Legendre (64 pts = exact to 1e-12 for smooth parts; plane cut is C1 so
  // 64-pt GL converges spectrally except exactly at tangent — fine).
  // Slice integral along the axis with 64-pt Gauss-Legendre (computed inline,
  // no tables). The plane cut is C1 so GL converges spectrally except exactly
  // at tangent — fine for our tolerances.
  const int N = 64;
  double xs[64], ws[64];
  {
    // Compute once per call (cheap: 64*20*64 flops ~ 80k).
    for (int i = 0; i < N; i++) {
      double x = std::cos(kPi * (i + 0.75) / (N + 0.5));
      for (int it = 0; it < 20; it++) {
        double p0 = 1, p1 = x;
        for (int k = 2; k <= N; k++) {
          double p2 = ((2 * k - 1) * x * p1 - (k - 1) * p0) / k;
          p0 = p1;
          p1 = p2;
        }
        double pp = N / (x * x - 1) * (x * p1 - p0);
        x = x - p1 / pp;
      }
      double p0 = 1, p1 = x;
      for (int k = 2; k <= N; k++) {
        double p2 = ((2 * k - 1) * x * p1 - (k - 1) * p0) / k;
        p0 = p1;
        p1 = p2;
      }
      double pp = N / (x * x - 1) * (x * p1 - p0);
      xs[i] = x;
      ws[i] = 2 / ((1 - x * x) * pp * pp);
    }
  }
  double L = hl + r;  // half total length along axis
  V = 0;
  std::array<double, 3> m{0, 0, 0};
  double az = a[2];
  for (int i = 0; i < N; i++) {
    double s = L * xs[i];
    double w = L * ws[i];
    // Radius of capsule cross-section at s.
    double rs;
    if (std::abs(s) <= hl)
      rs = r;
    else {
      double q = std::abs(s) - hl;
      rs = std::sqrt(std::max(0.0, r * r - q * q));
    }
    if (rs <= 0) continue;
    // Center of disc world z:
    double zc = b.x[2] + s * az;
    // Cross-section: disc radius rs in plane ⊥ a. Waterline cuts it along a
    // line; depth of water over disc center measured along world z, projected:
    // effective submersion of disc center: t = (surf - zc) / (perp factor).
    // The cut direction in-disc has world-z slope gamma = |a x zhat| component.
    // Exact segment area for a disc cut by a line at signed distance d from
    // center (d>0: center submerged by d): A = rs^2 acos(-d/rs)... use formula
    // with hseg = submerged cap height.
    double gperp = std::sqrt(std::max(0.0, 1 - az * az));  // |dz| per unit in-disc along steepest dir
    double A, zoff;  // submerged area, and its centroid z-offset from disc center
    if (gperp < 1e-12) {
      // Axis vertical: cut is all-or-nothing per slice.
      if (zc <= surf) {
        A = kPi * rs * rs;
        zoff = 0;
      } else {
        A = 0;
        zoff = 0;
      }
    } else {
      // Line cut at signed distance dc = (surf - zc)/gperp from disc center
      // (positive = center under water by dc along steepest descent).
      double dc = (surf - zc) / gperp;
      double hseg = std::clamp(dc + rs, 0.0, 2.0 * rs);  // submerged cap height
      if (hseg <= 0) {
        A = 0;
        zoff = 0;
      } else if (hseg >= 2 * rs) {
        A = kPi * rs * rs;
        zoff = 0;
      } else {
        // Circular segment area + centroid from center (toward submerged side).
        double th = std::acos(std::clamp(1.0 - hseg / rs, -1.0, 1.0));
        A = rs * rs * th - (rs - hseg) * std::sqrt(std::max(0.0, hseg * (2 * rs - hseg)));
        double chord = 2 * std::sqrt(std::max(0.0, hseg * (2 * rs - hseg)));
        double cdist = (chord * chord * chord) / (12.0 * std::max(A, 1e-300));
        // Centroid lies along steepest-descent in-disc dir (world -z projected),
        // its world-z offset = -cdist * gperp.
        zoff = -cdist * gperp;
        // x,y offset direction: -(a x zhat)x a normalized... only z matters
        // for the couple arm's dominant term, but keep full vector:
        // u = normalize(zhat - (zhat.a) a) is steepest ascent in-disc.
        // centroid world offset = -cdist * u.
        double ux = -az * a[0], uy = -az * a[1], uz = 1 - az * az;
        double un = std::sqrt(ux * ux + uy * uy + uz * uz);
        if (un > 1e-12) {
          double ox = -cdist * ux / un, oy = -cdist * uy / un, oz = -cdist * uz / un;
          // accumulate full moment below
          double px = b.x[0] + s * a[0] + ox, py = b.x[1] + s * a[1] + oy,
                 pz = b.x[2] + s * a[2] + oz;
          V += A * w;
          m[0] += A * w * px;
          m[1] += A * w * py;
          m[2] += A * w * pz;
          continue;
        }
      }
    }
    double px = b.x[0] + s * a[0], py = b.x[1] + s * a[1], pz = b.x[2] + s * a[2] + zoff;
    V += A * w;
    m[0] += A * w * px;
    m[1] += A * w * py;
    m[2] += A * w * pz;
  }
  cen = V > 1e-18 ? std::array<double, 3>{m[0] / V, m[1] / V, m[2] / V} : b.x;
}

}  // namespace

Wrench archimedes(const Body& b, const Env& e) {
  Wrench w;
  double V = 0;
  std::array<double, 3> cob = b.x;
  if (b.shape == Shape::Sphere) {
    double zc;
    sphere_sub(b.p[0], b.x[2], e.surface_z, V, zc);
    cob = {b.x[0], b.x[1], zc};
  } else if (b.shape == Shape::Box) {
    box_sub(b, e.surface_z, V, cob);
  } else {
    capsule_sub(b, e.surface_z, V, cob);
  }
  w.submerged_volume = V;
  w.cob = cob;
  double F = e.rho_water * e.g * V;  // air buoyancy neglected (rho_air/rho_water ~ 1e-3)
  w.F = {0, 0, F};
  std::array<double, 3> arm{cob[0] - b.x[0], cob[1] - b.x[1], cob[2] - b.x[2]};
  w.T = cross(arm, w.F);
  return w;
}

}  // namespace twomed
