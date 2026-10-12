"""showdown_common_mask.py — re-score the head-to-head on a COMMON caustic mask.

The first scoring gave each method its own caustic mask (the brightest N% of its
own converged render). With the corrected Cycles configuration those masks are
wildly different in size — 0.2% of the frame for Cycles against 4.8% for ours —
so the two RMSE numbers were not measuring the same pixels and comparing them
was invalid.

This scores both methods over one shared region, defined from the converged
render of each method averaged together, and reports it at several thresholds.

Run:  python tools/archive/showdown_common_mask.py
"""
import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
OUT = _ROOT + "/out"


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)


def rmse(a, b, mask):
    d = (a - b)[mask]
    return float(np.sqrt((d ** 2).mean()))


ref = {m: load(f"{OUT}/rn_{m}_ref.png") for m in ("cycles", "ours")}
img = {m: {s: load(f"{OUT}/rn_{m}_s{s}.png") for s in (256, 1024)}
       for m in ("cycles", "ours")}

lum_c = ref["cycles"].mean(axis=2)
lum_o = ref["ours"].mean(axis=2)
print("converged 4096 spp references")
for m, l in (("cycles", lum_c), ("ours", lum_o)):
    med = np.median(l)
    print(f"  {m:7s} median {med:6.1f}  peak {l.max():6.1f} "
          f"({l.max()-med:+5.1f} over median)  p99 {np.percentile(l,99):6.1f}")
print()

# one shared region: where EITHER converged render says there is caustic light
for pct in (90, 95, 98):
    common = (lum_c > np.percentile(lum_c, pct)) | (lum_o > np.percentile(lum_o, pct))
    print(f"common mask = brightest {100-pct}% of either reference "
          f"-> {100*common.mean():.2f}% of the frame")
    print(f"    {'spp':>6} {'Cycles RMSE':>13} {'ours RMSE':>11} {'gain':>8}")
    for s in (256, 1024):
        rc = rmse(img["cycles"][s], ref["cycles"], common)
        ro = rmse(img["ours"][s], ref["ours"], common)
        print(f"    {s:>6} {rc:>13.2f} {ro:>11.2f} {rc/max(ro,1e-9):>7.1f}x")
    print()

# how bright is the caustic in each method's converged render, over the shared
# bright region? (this is the brightness question left open in EVIDENCE 12)
common = (lum_c > np.percentile(lum_c, 95)) | (lum_o > np.percentile(lum_o, 95))
med = np.median(np.concatenate([lum_c, lum_o]))
print(f"over the shared bright region ({100*common.mean():.2f}% of frame):")
print(f"   Cycles converged  mean {lum_c[common].mean():6.2f}  peak {lum_c[common].max():6.1f}")
print(f"   ours   converged  mean {lum_o[common].mean():6.2f}  peak {lum_o[common].max():6.1f}")
print(f"   background median (both) {med:.1f}")
