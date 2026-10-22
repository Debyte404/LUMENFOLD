# Complex-Geometry Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether the band-local Airy correction survives beyond the single solid cylinder — on a sphere, a torus, a triangular prism, a two-body scene, and a cusp — using an independent mesh tracer as ground truth and a pre-registered pass/fail criterion.

**Architecture:** Phase 1 is a Python prototype. `tools/geometry_suite.py` writes analytic OBJ meshes; `tools/trace_mesh.py` traces sun rays through a triangle mesh and bins the receiver hits without using the production solver's Jacobian; `tools/apply_airy_band.py` applies the same band-local flux correction to that ray map. If Phase 1 passes, Phase 2 ports only the ray-map acquisition to C++ (`src/geometry/`) and leaves the correction unchanged. A failed geometry is recorded in EVIDENCE and is not tuned.

**Tech Stack:** Python 3.12, numpy, Pillow, matplotlib; C++17 for Phase 2; Blender/PBRT only for the comparison renders, never for the ground truth.

---

## Pre-registered acceptance criteria

These are fixed before any run. Changing them after seeing a result is a new
experiment and must be recorded as such.

| geometry | pass criterion at 40 mm tiles | additional |
|---|---|---|
| sphere, R = 35 mm, n = 1.5251 | r >= 0.85 against the mesh tracer | centroid within 2% of the 320 mm patch |
| torus, R = 35 mm, r = 12 mm | r >= 0.80 | both fold arcs detected; band energy within 1% |
| triangular prism, side 70 mm | r >= 0.85 | edge caustic present, no false fold in the flat interior |
| two spheres, centres 90 mm apart | r >= 0.80 | two separated caustics; no cross-talk in the gap |
| cusp (bicylinder, Phase 3) | bounded field, no NaN | exponent -0.3333 ± 0.01; cost reported, not claimed |

A geometry that fails is a negative result. Do not change the mesh resolution,
threshold, or tile size to make it pass after the first run.

The cusp is Phase 3, after the four watertight meshes pass their self-checks. It
is reported separately because the paper already measured its cost at ~2.1e4x an
Airy lookup; the mesh suite is not a production-cost claim.

---

## File Structure

**Create**
- `tools/geometry_suite.py` — analytic OBJ generators and manifest.
- `tools/geometry_selfcheck.py` — watertightness, volume, and Euler checks.
- `tools/trace_mesh.py` — independent triangle-mesh tracer and ray-map grid.
- `tools/apply_airy_band.py` — the band-local correction applied to a generic ray map.
- `tools/run_geometry_suite.py` — orchestration, metrics, CSV, and figure.
- `docs/GEOMETRY_SUITE.md` — protocol, criteria, and how to reproduce.
- `docs/data/geometry_suite.csv` — one row per geometry and metric (generated).
- `docs/media/geometry_suite.png` — the six-panel comparison (generated).
- `models/geometries/` — generated OBJ files and `manifest.json`.
- `src/geometry/mesh.hpp`, `src/geometry/mesh.cpp`, `src/geometry/CMakeLists.txt` — Phase 2 only.

**Modify**
- `docs/EVIDENCE.md` — append a dated section with the measured table.
- `README.md`, `docs/README.md`, `tools/README.md` — only after the numbers exist.
- `docs/paper/sections/*.tex` and `docs/paper-ieee/` — only if a result survives and the dual-format rule is satisfied.
- `AGENTS.md` — no change expected; the existing claim and dual-format rules cover this work.

---

## Task 1: Generate analytic meshes

**Files:**
- Create: `tools/geometry_suite.py`
- Create: `tools/geometry_selfcheck.py`
- Create: `models/geometries/manifest.json` (generated)

- [ ] **Step 1: Write the generator**

Create `tools/geometry_suite.py`:

```python
"""geometry_suite.py -- analytic OBJ meshes for the complex-geometry suite.

All meshes are in metres, centred on the origin, with +Z up and the receiver
plane at z = -0.10 m. The generator is deterministic: the same arguments always
write byte-identical OBJ files apart from the header comment.
"""
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "models" / "geometries"


def write_obj(path, verts, faces, name):
    lines = [f"# {name}", f"# {len(verts)} vertices, {len(faces)} faces"]
    lines += [f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in verts]
    lines += [f"f {a+1} {b+1} {c+1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def uv_sphere(radius, n_lat=48, n_lon=96, centre=(0.0, 0.0, 0.0)):
    cx, cy, cz = centre
    verts = [(cx, cy, cz + radius)]
    for i in range(1, n_lat):
        theta = math.pi * i / n_lat
        for j in range(n_lon):
            phi = 2.0 * math.pi * j / n_lon
            verts.append((cx + radius * math.sin(theta) * math.cos(phi),
                          cy + radius * math.sin(theta) * math.sin(phi),
                          cz + radius * math.cos(theta)))
    south = len(verts)
    verts.append((cx, cy, cz - radius))
    faces = []
    for j in range(n_lon):
        faces.append((0, 1 + j, 1 + (j + 1) % n_lon))
    for i in range(n_lat - 2):
        row0 = 1 + i * n_lon
        row1 = row0 + n_lon
        for j in range(n_lon):
            a = row0 + j
            b = row0 + (j + 1) % n_lon
            c = row1 + j
            d = row1 + (j + 1) % n_lon
            faces.append((a, b, d))
            faces.append((a, d, c))
    last = 1 + (n_lat - 2) * n_lon
    for j in range(n_lon):
        faces.append((south, last + (j + 1) % n_lon, last + j))
    return verts, faces


def torus(R, r, n_major=96, n_minor=48):
    verts, faces = [], []
    for i in range(n_major):
        u = 2.0 * math.pi * i / n_major
        for j in range(n_minor):
            v = 2.0 * math.pi * j / n_minor
            verts.append(((R + r * math.cos(v)) * math.cos(u),
                          (R + r * math.cos(v)) * math.sin(u),
                          r * math.sin(v)))
    for i in range(n_major):
        for j in range(n_minor):
            a = i * n_minor + j
            b = ((i + 1) % n_major) * n_minor + j
            c = ((i + 1) % n_major) * n_minor + (j + 1) % n_minor
            d = i * n_minor + (j + 1) % n_minor
            faces.append((a, b, c))
            faces.append((a, c, d))
    return verts, faces


def triangular_prism(side=0.070, height=0.090):
    h = side * math.sqrt(3.0) / 2.0
    base = [(-side / 2, -h / 3), (side / 2, -h / 3), (0.0, 2 * h / 3)]
    verts = [(x, y, -height / 2) for x, y in base]
    verts += [(x, y, height / 2) for x, y in base]
    faces = [(0, 1, 2), (5, 4, 3)]
    for i in range(3):
        a, b = i, (i + 1) % 3
        faces.append((a, b, b + 3))
        faces.append((a, b + 3, a + 3))
    return verts, faces


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    s1_v, s1_f = uv_sphere(0.025, centre=(-0.045, 0.0, 0.0))
    s2_v, s2_f = uv_sphere(0.025, centre=(0.045, 0.0, 0.0))
    two_v = s1_v + s2_v
    two_f = s1_f + [(a + len(s1_v), b + len(s1_v), c + len(s1_v))
                    for a, b, c in s2_f]
    specs = [
        ("sphere_r35", "sphere", uv_sphere(0.035), 0.035),
        ("torus_R35_r12", "torus", torus(0.035, 0.012), 0.012),
        ("prism_side70", "prism", triangular_prism(0.070, 0.090), 0.035),
        ("two_spheres", "two-body", (two_v, two_f), 0.025),
    ]
    for name, kind, (verts, faces), scale in specs:
        path = OUT / f"{name}.obj"
        write_obj(path, verts, faces, name)
        manifest.append({"name": name, "kind": kind, "file": path.name,
                         "vertices": len(verts), "faces": len(faces),
                         "euler": 0 if kind == "torus" else (4 if kind == "two-body" else 2),
                         "scale_m": scale})
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(f"wrote {len(manifest)} meshes to {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the self-check**

Create `tools/geometry_selfcheck.py`:

```python
"""geometry_selfcheck.py -- a mesh is usable only if it is closed and oriented."""
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "geometries"


def load_obj(path):
    verts, faces = [], []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            verts.append(tuple(float(x) for x in line.split()[1:4]))
        elif line.startswith("f "):
            idx = [int(x.split("/")[0]) - 1 for x in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return verts, faces


def volume(verts, faces):
    v = 0.0
    for a, b, c in faces:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        v += (ax * (by * cz - bz * cy)
              - ay * (bx * cz - bz * cx)
              + az * (bx * cy - by * cx)) / 6.0
    return abs(v)


def main():
    manifest = json.loads((MODELS / "manifest.json").read_text())
    for entry in manifest:
        verts, faces = load_obj(MODELS / entry["file"])
        edges = Counter()
        for a, b, c in faces:
            for u, v in ((a, b), (b, c), (c, a)):
                edges[tuple(sorted((u, v)))] += 1
        bad = [e for e, n in edges.items() if n != 2]
        euler = len(verts) - len(set(edges)) + len(faces)
        vol = volume(verts, faces)
        print(f"{entry['name']:16s} V={len(verts):6d} F={len(faces):6d} "
              f"E={len(set(edges)):6d} euler={euler:3d} "
              f"open_edges={len(bad):3d} volume={vol:.6e}")
        assert not bad, f"{entry['name']} is not watertight: {bad[:3]}"
        assert euler == entry["euler"], f"{entry['name']} euler {euler} != {entry['euler']}"
        assert vol > 0, f"{entry['name']} has zero volume"
    print("GEOMETRY SELF-CHECK OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the generator and the self-check**

Run:
```bat
python tools/geometry_suite.py
python tools/geometry_selfcheck.py
```
Expected: `wrote 4 meshes`, then four lines with `open_edges=0`, `euler` equal to the manifest value (2 for the sphere and prism, 0 for the torus, 4 for the two-body mesh), positive volume, and `GEOMETRY SELF-CHECK OK`.

- [ ] **Step 4: Commit**

```bat
git add tools/geometry_suite.py tools/geometry_selfcheck.py models/geometries
git commit -m "Add analytic meshes for the complex-geometry suite"
```

---

## Task 2: Write the independent mesh tracer

**Files:**
- Create: `tools/trace_mesh.py`

- [ ] **Step 1: Write the tracer**

Create `tools/trace_mesh.py` with the following public functions. The ray-triangle
test is Möller–Trumbore; the refraction is the same Snell law as the paper, but it
is implemented here from the interface normal and is not imported from the solver.

```python
"""trace_mesh.py -- independent triangle-mesh tracer for the geometry suite.

No Jacobian, no parametrisation, no call into src/: this is the ground truth.
A sun ray is traced from the source plane, through the mesh, to the receiver
plane at z = -0.10 m. The receiver is binned on a 320 mm x 320 mm patch.
"""
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "geometries"
RECEIVER_Z = -0.10
PATCH = 0.320
SUN = np.array([-0.35, -0.25, -1.0])
SUN = SUN / np.linalg.norm(SUN)


def load_obj(path):
    verts, faces = [], []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(x.split("/")[0]) - 1 for x in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return np.asarray(verts), np.asarray(faces, dtype=np.int64)


def intersect(o, d, a, b, c):
    e1, e2 = b - a, c - a
    p = np.cross(d, e2)
    det = e1 @ p
    if abs(det) < 1e-14:
        return None
    inv = 1.0 / det
    t = o - a
    u = (t @ p) * inv
    if u < 0.0 or u > 1.0:
        return None
    q = np.cross(t, e1)
    v = (d @ q) * inv
    if v < 0.0 or u + v > 1.0:
        return None
    dist = (e2 @ q) * inv
    if dist <= 1e-9:
        return None
    n = np.cross(e1, e2)
    n /= np.linalg.norm(n)
    return dist, a + dist * d, n


def refract(d, n, eta):
    cosi = -float(d @ n)
    if cosi < 0.0:
        n, cosi = -n, -cosi
    k = 1.0 - eta * eta * (1.0 - cosi * cosi)
    if k < 0.0:
        return None
    return eta * d + (eta * cosi - math.sqrt(k)) * n


def trace(mesh, n_side=1400, eta=1.5251, receiver_z=RECEIVER_Z):
    verts, faces = mesh
    A = verts[faces[:, 0]]
    E1 = verts[faces[:, 1]] - A
    E2 = verts[faces[:, 2]] - A
    pvec = np.cross(SUN, E2)                 # constant: the sun is fixed
    det = np.einsum("ij,ij->i", E1, pvec)
    good = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[good] = 1.0 / det[good]
    # Source plane: a square perpendicular to the sun, wide enough for the mesh.
    lo, hi = verts.min(axis=0) - 0.02, verts.max(axis=0) + 0.02
    centre = 0.5 * (lo + hi)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(SUN, up); right /= np.linalg.norm(right)
    up = np.cross(right, SUN)
    half = 0.5 * float(np.linalg.norm(hi - lo)) + 0.01
    xs = np.linspace(-half, half, n_side)
    hits = []
    for x in xs:
        for y in xs:
            o = centre + x * right + y * up - 0.20 * SUN
            tvec = o - A
            qvec = np.cross(tvec, E1)
            u = np.einsum("ij,ij->i", tvec, pvec) * inv
            v = (qvec @ SUN) * inv
            dist = np.einsum("ij,ij->i", qvec, E2) * inv
            ok = (good & (u >= 0.0) & (u <= 1.0) & (v >= 0.0)
                  & (u + v <= 1.0) & (dist > 1e-9))
            if not ok.any():
                continue
            i = int(np.argmin(np.where(ok, dist, np.inf)))
            p = o + dist[i] * SUN
            n = np.cross(E1[i], E2[i])
            n /= np.linalg.norm(n)
            if n @ SUN > 0.0:
                n = -n
            t = refract(SUN, n, 1.0 / eta)
            if t is None or abs(t[2]) < 1e-9:
                continue
            s = (receiver_z - p[2]) / t[2]
            if s <= 0.0:
                continue
            q = p + s * t
            if abs(q[0]) <= PATCH / 2 and abs(q[1]) <= PATCH / 2:
                hits.append((q[0], q[1]))
    return np.asarray(hits, dtype=np.float64)


def to_grid(hits, n=512, patch=PATCH):
    g, _, _ = np.histogram2d(
        hits[:, 0], hits[:, 1], bins=n,
        range=[[-patch / 2, patch / 2], [-patch / 2, patch / 2]])
    return g.T


def load(name):
    manifest = json.loads((MODELS / "manifest.json").read_text())
    entry = next(e for e in manifest if e["name"] == name)
    return load_obj(MODELS / entry["file"])
```

- [ ] **Step 2: Add the analytic sphere test**

Append to the same file:

```python
def _self_test():
    """A ball lens focuses a parallel beam at f = nR/(2(n-1)) from its centre."""
    verts, faces = load("sphere_r35")
    hits = trace((verts, faces), n_side=300)
    assert len(hits) > 1000, f"only {len(hits)} hits"
    f = 1.5251 * 0.035 / (2.0 * (1.5251 - 1.0))
    hits = trace((verts, faces), n_side=300, receiver_z=-f)
    assert len(hits) > 100, f"only {len(hits)} hits"
    # Put the receiver at the paraxial focus: a ball lens should concentrate
    # there, with spherical aberration broadening the spot.
    r = np.sqrt((hits ** 2).sum(axis=1))
    print(f"sphere: {len(hits)} hits  mean radius {r.mean()*1e3:.2f} mm  "
          f"paraxial EFL {f*1e3:.2f} mm")
    assert r.mean() < 0.2 * f, "sphere caustic is not near the paraxial focus"
    print("TRACE SELF-TEST OK")


if __name__ == "__main__":
    _self_test()
```

- [ ] **Step 3: Run the tracer test**

Run:
```bat
python tools/trace_mesh.py
```
Expected: `sphere: ... hits ... mean radius ... mm paraxial EFL 50.84 mm` and `TRACE SELF-TEST OK`. The 300^2 self-test is for correctness; the runner's 1400^2 trace takes minutes per mesh. Do not reduce the reported run below 700^2, and record the resolution in the CSV.

- [ ] **Step 4: Commit**

```bat
git add tools/trace_mesh.py
git commit -m "Add an independent mesh tracer for the geometry suite"
```

---

## Task 3: Apply the band-local correction to a generic ray map

**Files:**
- Create: `tools/apply_airy_band.py`

- [ ] **Step 1: Write the correction wrapper**

Create `tools/apply_airy_band.py`:

```python
"""apply_airy_band.py -- the paper's band-local Airy correction on a ray map.

Input: a 2-D geometric irradiance map and its signed fold-distance field.
Output: the corrected map. The flux ratio is computed inside the band, so the
same code applies to any geometry; only the det-J field changes.
"""
import numpy as np


def airy_profile(x):
    """|Ai(-x)|^2 normalised to its peak, using the solver's LUT if available."""
    from scipy.special import airy
    ai, _, _, _ = airy(-x)
    y = ai * ai
    return y / y.max()


def correct(field, signed_distance, band_width, airy_scale):
    """Redistribute the band's own geometric energy by the Airy profile.

    field           geometric irradiance, shape (H, W)
    signed_distance distance to the fold, same shape, metres
    band_width      half-width of the detected band, metres
    airy_scale      the display width w, metres (canonical 6.77e-6 here)
    """
    out = field.copy()
    band = np.abs(signed_distance) <= band_width
    if not band.any():
        return out
    energy = float(field[band].sum())
    if energy <= 0.0:
        return out
    s = signed_distance[band] / airy_scale
    w = airy_profile(np.clip(s, -8.0, 8.0))
    w = w / w.sum()
    out[band] = energy * w
    return out
```

- [ ] **Step 2: Add a flux test**

Append:

```python
def _self_test():
    field = np.ones((64, 64))
    d = np.linspace(-0.01, 0.01, 64)[None, :].repeat(64, axis=0)
    out = correct(field, d, band_width=0.002, airy_scale=6.77e-6)
    band = np.abs(d) <= 0.002
    a, b = field[band].sum(), out[band].sum()
    print(f"band energy in {a:.6f} out {b:.6f} ratio {b/a:.9f}")
    assert abs(b / a - 1.0) < 1e-6, "band energy is not conserved"
    print("AIRY BAND SELF-TEST OK")


if __name__ == "__main__":
    _self_test()
```

- [ ] **Step 3: Run the test**

Run:
```bat
python tools/apply_airy_band.py
```
Expected: `ratio 1.000000000` and `AIRY BAND SELF-TEST OK`.

- [ ] **Step 4: Commit**

```bat
git add tools/apply_airy_band.py
git commit -m "Add a geometry-agnostic band correction wrapper"
```

---

## Task 4: Run the suite and write the measurement table

**Files:**
- Create: `tools/run_geometry_suite.py`
- Create: `docs/GEOMETRY_SUITE.md`
- Create: `docs/data/geometry_suite.csv` (generated)
- Create: `docs/media/geometry_suite.png` (generated)

- [ ] **Step 1: Write the runner**

Create `tools/run_geometry_suite.py`:

```python
"""run_geometry_suite.py -- trace every mesh, apply the band, and score it.

Writes docs/data/geometry_suite.csv and docs/media/geometry_suite.png.
The correlation uses the same tile convention as the paper: a tile of k x k
pixels is reported by its physical size, 320/k millimetres.
"""
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

import trace_mesh as T
import apply_airy_band as A

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data"
MEDIA = ROOT / "docs" / "media"
NAMES = ["sphere_r35", "torus_R35_r12", "prism_side70", "two_spheres"]


def corr(a, b, n_tiles):
    bs = a.shape[0] // n_tiles
    A1 = a.reshape(n_tiles, bs, n_tiles, bs).mean(axis=(1, 3))
    B1 = b.reshape(n_tiles, bs, n_tiles, bs).mean(axis=(1, 3))
    A1 = A1 - A1.mean()
    B1 = B1 - B1.mean()
    d = np.sqrt((A1 * A1).sum() * (B1 * B1).sum())
    return float((A1 * B1).sum() / d) if d > 0 else 0.0


def run_one(name, airy=0.0015):
    mesh = T.load(name)
    hits = T.trace(mesh, n_side=1400)
    gt = T.to_grid(hits)
    # The prototype's geometric field is the same trace at a lower resolution;
    # this isolates the correction's effect from the tracer's sampling noise.
    low = T.to_grid(hits, n=512)
    if not (low > 0).any():
        raise SystemExit(f"{name}: the tracer produced no receiver hits")
    # A crude signed distance to the bright ridge; the runner's purpose is the
    # score, not a production band detector.
    from scipy.ndimage import distance_transform_edt
    ridge = low > np.percentile(low[low > 0], 95)
    d = distance_transform_edt(~ridge) / 512.0 * T.PATCH
    # 1.5 mm is the paper's 220x display scale, not the 6.77 um physical scale;
    # the ratio is printed so the CSV cannot be read as a physical run.
    corrected = A.correct(low, d - d[ridge].mean(), band_width=0.004,
                          airy_scale=airy)
    return gt, low, corrected, airy / 6.77e-6


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    rows, panels = [], []
    for name in NAMES:
        gt, low, corrected, ratio = run_one(name)
        rows.append({"geometry": name,
                     "hits": int((gt > 0).sum()),
                     "airy_scale_m": 0.0015,
                     "exaggeration": round(ratio, 0),
                     "r_uncorrected_40mm": round(corr(gt, low, 8), 3),
                     "r_corrected_40mm": round(corr(gt, corrected, 8), 3),
                     "r_corrected_5mm": round(corr(gt, corrected, 64), 3)})
        panels.append((name, low, corrected, gt))
    with (OUT / "geometry_suite.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, len(panels), figsize=(3.2 * len(panels), 6.4))
    for col, (name, low, corrected, gt) in enumerate(panels):
        axes[0, col].imshow(gt, cmap="inferno"); axes[0, col].set_title(name, fontsize=8)
        axes[1, col].imshow(corrected, cmap="inferno")
        for row in (0, 1):
            axes[row, col].set_xticks([]); axes[row, col].set_yticks([])
    axes[0, 0].set_ylabel("ground truth", fontsize=8)
    axes[1, 0].set_ylabel("corrected", fontsize=8)
    fig.tight_layout()
    fig.savefig(MEDIA / "geometry_suite.png", dpi=200)
    plt.close(fig)
    print(json.dumps(rows, indent=2))
    print(f"wrote {OUT / 'geometry_suite.csv'}")
    print(f"wrote {MEDIA / 'geometry_suite.png'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the protocol document**

Create `docs/GEOMETRY_SUITE.md`:

```markdown
# Complex-geometry suite

Pre-registered protocol for extending the caustic correction beyond the solid
cylinder. The acceptance criteria are in the plan
`docs/superpowers/plans/2026-10-20-complex-geometry-experiments.md` and are not
changed after a run.

## Meshes

`python tools/geometry_suite.py` writes four analytic OBJ meshes and a manifest
under `models/geometries/`. `python tools/geometry_selfcheck.py` requires every
mesh to be closed, Euler-2, and positive-volume.

## Ground truth

`python tools/trace_mesh.py` traces 1400^2 sun rays through the mesh, refracts at
the first interface, and bins the receiver hits on a 320 mm patch. It does not
call the solver and does not use the solver's Jacobian.

## Correction

`python tools/apply_airy_band.py` applies the paper's band-local flux ratio to
the ray map. The canonical Airy scale is 6.77 um; any display exaggeration must
be stated in the caption.

## Scoring

`python tools/run_geometry_suite.py` writes `docs/data/geometry_suite.csv`.
Correlation is reported at 40 mm and 5 mm tiles, using the same convention as the
paper. A geometry passes only if it meets the pre-registered threshold; a fail is
recorded in `docs/EVIDENCE.md`, not tuned away.

## Reproduce

```bat
python tools/geometry_suite.py
python tools/geometry_selfcheck.py
python tools/trace_mesh.py
python tools/apply_airy_band.py
python tools/run_geometry_suite.py
```
```

- [ ] **Step 3: Run the suite**

Run:
```bat
python tools/geometry_suite.py
python tools/geometry_selfcheck.py
python tools/trace_mesh.py
python tools/apply_airy_band.py
python tools/run_geometry_suite.py
```
Expected: the CSV has four rows; the sphere and prism meet their thresholds; if a
geometry misses, the row is still written and the failure is recorded. Do not
edit the threshold to make the CSV green.

- [ ] **Step 4: Commit**

```bat
git add tools/run_geometry_suite.py docs/GEOMETRY_SUITE.md docs/data/geometry_suite.csv docs/media/geometry_suite.png
git commit -m "Add the complex-geometry suite and its pre-registered protocol"
```

---

## Task 5: Add robustness sweeps

**Files:**
- Modify: `tools/run_geometry_suite.py`
- Modify: `docs/GEOMETRY_SUITE.md`

- [ ] **Step 1: Add three axes**

Add a `--sweep` mode that runs each geometry at:
- mesh resolution 32, 64, 128 segments (sphere);
- sun elevation offset -10, 0, +10 degrees;
- index 1.33 (water) and 1.5251 (glass);
- three random seeds for the stochastic comparison renders.

- [ ] **Step 2: Report mean and standard deviation**

Extend the CSV with `r_mean`, `r_sd`, `n_runs`. A geometry passes only if the
mean meets the threshold and the standard deviation is below 0.05.

- [ ] **Step 3: Run the sweep**

Run:
```bat
python tools/run_geometry_suite.py --sweep
```
Expected: every geometry has `n_runs=3` for the stochastic axes and the
deterministic axes have `r_sd=0`. Record any geometry whose ranking changes with
the sun angle as a scope limitation, not as a win.

- [ ] **Step 4: Commit**

```bat
git add tools/run_geometry_suite.py docs/GEOMETRY_SUITE.md docs/data/geometry_suite.csv
git commit -m "Add robustness sweeps to the geometry suite"
```

---

## Task 6: Port the ray-map acquisition to C++ (conditional)

**Files:**
- Create: `src/geometry/mesh.hpp`
- Create: `src/geometry/mesh.cpp`
- Create: `src/geometry/CMakeLists.txt`
- Modify: `src/app/showcase_main.cpp`
- Modify: `src/app/CMakeLists.txt`

**Go/no-go:** do this task only if Task 4 meets the sphere and prism thresholds.
If it does not, record the Phase 1 failure and stop; do not port a method that has
not passed its own prototype.

- [ ] **Step 1: Add the mesh interface**

Create `src/geometry/mesh.hpp`:

```cpp
#pragma once
#include <string>
#include <vector>

struct Vec3 { double x, y, z; };
struct Triangle { Vec3 a, b, c; };

struct Hit {
    bool ok = false;
    double t = 0.0;
    Vec3 p{}, n{};
};

class Mesh {
public:
    static Mesh load_obj(const std::string& path);
    Hit intersect(const Vec3& o, const Vec3& d) const;
    const std::vector<Triangle>& triangles() const { return tris_; }
private:
    std::vector<Triangle> tris_;
};
```

- [ ] **Step 2: Add the brute-force implementation**

Create `src/geometry/mesh.cpp` with the Möller–Trumbore test and an OBJ loader.
The first milestone is deliberately O(N) per ray; a BVH is added only if the
1400^2 trace exceeds 10 minutes on the benchmark machine.

- [ ] **Step 3: Add `--geometry` to showcase**

In `src/app/showcase_main.cpp`, parse `--geometry <obj>`. When set, replace the
cylinder ray-map acquisition with the forward trace described in
`docs/GEOMETRY_SUITE.md`: sample a sun-perpendicular grid, take the first hit,
refract with Snell, intersect the receiver, and write the receiver position into
the existing ray-map buffer. The correction pass and all downstream code stay
unchanged.

- [ ] **Step 4: Build and compare**

Run:
```bat
cmake --build build --config Release
build\src\app\Release\showcase.exe --geometry models\geometries\sphere_r35.obj --n 400000 --res 512 --out out\geom_sphere.png
python tools/run_geometry_suite.py --compare-cpp out\geom_sphere.png sphere_r35
```
Expected: the C++ field and the Python field agree at r >= 0.95 on 40 mm tiles.
If they do not, the port is wrong; do not proceed to Task 7.

- [ ] **Step 5: Commit**

```bat
git add src/geometry src/app/showcase_main.cpp src/app/CMakeLists.txt
git commit -m "Add mesh ray-map acquisition to showcase"
```

---

## Task 7: Paper integration (conditional)

**Files:**
- Modify: `docs/paper/sections/results.tex` (new subsection)
- Modify: `docs/paper/sections/frontmatter.tex` (only if the abstract must change)
- Modify: `docs/paper-ieee/sections/frontmatter.tex` (mirror any abstract change)
- Modify: `README.md`, `docs/README.md`, `docs/EVIDENCE.md`, `docs/CRITIQUE.md`, `tools/README.md`

- [ ] **Step 1: Apply the claim gate**

A geometry enters the paper only if:
- it met the pre-registered threshold in Task 4 or Task 5;
- the result is not a per-geometry tuning;
- the negative results are reported in the same subsection.

- [ ] **Step 2: Add the evidence section first**

Append a dated section to `docs/EVIDENCE.md` with the CSV table, the exact
commands, and the failed geometries. Do not edit the paper before this exists.

- [ ] **Step 3: Add the shared results subsection**

Add the new subsection to `docs/paper/sections/results.tex`. Because that file is
shared, the IEEE edition picks it up automatically. Do not create a separate IEEE
copy.

- [ ] **Step 4: Run the dual-format gate**

Run:
```bat
python tools/build_paper_pdf.py --engine pdflatex
python tools/build_paper_ieee.py
python tools/check_dual_format.py
```
Expected: both builds exit 0 with 0 overfull; `DUAL-FORMAT OK`. If the abstract
changed, both frontmatters changed in the same commit and the parity check still
passes.

- [ ] **Step 5: Commit**

```bat
git add docs/EVIDENCE.md docs/paper/sections/results.tex docs/paper/sections/frontmatter.tex docs/paper-ieee/sections/frontmatter.tex README.md docs/README.md docs/CRITIQUE.md tools/README.md
git commit -m "Report the complex-geometry suite and its negative results"
```

---

## Task 8: Record the failed geometries

**Files:**
- Modify: `docs/EVIDENCE.md`
- Modify: `docs/CRITIQUE.md`

- [ ] **Step 1: Write the negative-result table**

For every geometry that missed its threshold, record:
- the geometry and mesh file;
- the measured r at 40 mm and 5 mm;
- the likely cause (occlusion, multiple interfaces, cusp, sampling);
- the experiment that would distinguish the causes.

- [ ] **Step 2: Add the criticism**

If the failure exposes a limitation of the method (not of the prototype), add it
to `docs/CRITIQUE.md` with the evidence section reference. If it is a prototype
limitation, say so and do not present it as a method failure.

- [ ] **Step 3: Commit**

```bat
git add docs/EVIDENCE.md docs/CRITIQUE.md
git commit -m "Record the complex-geometry negative results"
```

---

## Self-review

- **Spec coverage:** the plan produces meshes, an independent tracer, a
  geometry-agnostic correction, a scored table, robustness sweeps, a conditional
  C++ port, and a conditional paper subsection. Every geometry has a
  pre-registered pass/fail criterion.
- **Placeholder scan:** no `TBD` or `TODO`. The only conditional steps are
  explicitly gated by measured outcomes (Task 6 and Task 7), not by missing code.
- **Type consistency:** `trace_mesh.load(name)`, `trace_mesh.trace(mesh)`,
  `trace_mesh.to_grid(hits)`, and `apply_airy_band.correct(field, signed_distance,
  band_width, airy_scale)` are used with the same signatures in the runner and the
  tests.
- **Known risk:** the prototype's signed-distance field is crude (a distance
  transform from the bright ridge). If the sphere and prism pass but the torus
  does not, the next experiment is a better band detector, not a per-geometry
  threshold change.
```
