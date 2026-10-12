"""compare_to_reference.py — quantitative realism check against the photograph.

There is no image-understanding model in this environment, so "does it look
photoreal" cannot be answered by looking. Instead the render is compared to the
reference photograph's measurable statistics: exposure, tonal spread, palette
warmth, local detail. That is a necessary-not-sufficient test - a match on these
does not prove photorealism - but a mismatch on them definitely refutes it.

Usage:
  python tools/compare_to_reference.py [--ref PATH] [--render PATH]
"""
import argparse
import os

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

DEFAULT_REF = "D:/hermes/hermes-agent/images/clip_20261007_093608_3.png"
DEFAULT_RENDER = _ROOT + "/out/showcase.png"

# what we consider "close enough" on each statistic
TOL = {
    "mean": 18.0,       # absolute luminance levels
    "p25": 25.0,
    "p75": 25.0,
    "range": 30.0,      # p5..p95 spread
    "warmth": 8.0,      # R-B in levels
    "detail": 0.8,      # mean |horizontal gradient|
}


def measure(path, label, target=None):
    im = Image.open(path).convert("RGB")
    orig = f"{im.width}x{im.height}"
    # Gradient energy is resolution-dependent: comparing a 1800x1125 render to an
    # 800x457 photograph inflates or deflates "detail" for reasons that have
    # nothing to do with realism. Resample the render onto the reference's grid
    # first, then every statistic is measured at the same spatial scale.
    if target is not None and (im.width, im.height) != target:
        im = im.resize(target, Image.BOX)
    a = np.asarray(im).astype(np.float32)
    lum = a.mean(axis=2)
    m = {
        "mean": float(lum.mean()),
        "p5": float(np.percentile(lum, 5)),
        "p25": float(np.percentile(lum, 25)),
        "p50": float(np.percentile(lum, 50)),
        "p75": float(np.percentile(lum, 75)),
        "p95": float(np.percentile(lum, 95)),
        "range": float(np.percentile(lum, 95) - np.percentile(lum, 5)),
        "warmth": float(a[:, :, 0].mean() - a[:, :, 2].mean()),
        "detail": float(np.abs(np.diff(lum, axis=1)).mean()),
        "size": f"{a.shape[1]}x{a.shape[0]}",
        "orig": orig,
    }
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--render", default=DEFAULT_RENDER)
    args = ap.parse_args()

    if not os.path.exists(args.ref):
        print(f"reference not found: {args.ref}")
        return 1
    r = measure(args.ref, "reference")
    m = measure(args.render, "render", target=(int(r["size"].split("x")[0]), int(r["size"].split("x")[1])))

    print(f"reference : {args.ref}  ({r['size']})")
    print(f"render    : {args.render}  ({m['orig']}, measured at {m['size']})")
    print()
    hdr = f"{'statistic':>10} {'reference':>10} {'render':>10} {'delta':>10} {'tol':>7}  verdict"
    print(hdr)
    print("-" * len(hdr))
    ok = 0
    total = 0
    for k in ("mean", "p25", "p75", "range", "warmth", "detail"):
        d = m[k] - r[k]
        passed = abs(d) <= TOL[k]
        total += 1
        ok += 1 if passed else 0
        print(f"{k:>10} {r[k]:>10.1f} {m[k]:>10.1f} {d:>+10.1f} {TOL[k]:>7.1f}  "
              f"{'ok' if passed else 'OFF'}")
    print()
    print(f"{ok}/{total} statistics within tolerance")
    if ok < total:
        print("fix the OFF rows by exposure / palette / falloff, not by eye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
