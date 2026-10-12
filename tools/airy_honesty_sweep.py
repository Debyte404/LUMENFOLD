"""airy_honesty_sweep.py -- pick the airy_scale for the ripple GIFs.

The renders so far use airy_scale = 1.5 mm, which is 12.2x the physical fringe
width (0.123 mm) and was chosen for visibility. The user wants no exaggerated
fringes, so this measures what happens as the band approaches the physical
width, and warns if the band goes sub-pixel (which would alias across frames
instead of simply disappearing).

Metrics per scale:
  band_px      how many pixels the Airy band spans (5w is the support radius)
  spread        mean per-channel deviation from the field mean (fringe colour)
  peak/mean     display saturation
  isolated     pixels that spike >3x their 8-neighbour median (aliasing signal)
"""
import io
import os
import struct
import subprocess
import sys
import zlib

import numpy as np


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
OUT = f"{ROOT}/out"
RES = 1024
PATCH_MM = 320.0
PHYSICAL_MM = 0.123          # tools/fringe_scale.py, this geometry


def read_png16(path):
    d = open(path, "rb").read()
    pos, idat = 8, b""
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 * 2
    out = np.zeros((h, w, 3), np.uint16)
    p = 0
    for y in range(h):
        p += 1
        out[y] = np.frombuffer(raw[p:p + stride], dtype=">u2").reshape(w, 3)
        p += stride
    return out.astype(np.float32) / 65535.0 * 16.0


def isolated_fraction(lum):
    """Fraction of pixels that spike relative to a local median -- an aliasing
    signature for a sub-pixel band."""
    from scipy.ndimage import median_filter
    med = median_filter(lum, size=3)
    return float((lum > 3 * med + 0.05).mean())


def main():
    print(f"=== airy_scale sweep at {RES}^2, patch {PATCH_MM:.0f} mm "
          f"({PATCH_MM/RES:.4f} mm/px) ===")
    print(f"    physical fringe width for this geometry: {PHYSICAL_MM} mm "
          f"= {PHYSICAL_MM/(PATCH_MM/RES):.2f} px")
    print()
    hdr = f"{'airy_scale':>11} {'band_px':>8} {'spread':>9} {'peak':>6} {'mean':>7} {'isolated':>9}  note"
    print(hdr)
    print("-" * len(hdr))

    scales = [0.0015, 0.0006, 0.0003, 0.000123]
    for a in scales:
        cp = f"{OUT}/_sweep_{a:.6f}.png"
        p = subprocess.run([EXE, "--res", str(RES), "--airy", f"{a:.6f}",
                            "--n", "400", "--ssaa", "1", "--wave-t", "0.0",
                            "--out", f"{OUT}/_sw.png", "--dump-caustic", cp],
                           capture_output=True, text=True, timeout=900)
        if not os.path.exists(cp):
            print(f"  {a:.6f}  BAKE FAILED: {p.stderr[-200:]}")
            continue
        f = read_png16(cp)
        lum = f.mean(axis=2)
        mid = f[:, :, 1]
        spread = float(np.abs(f - mid[..., None]).mean())
        band_px = 5 * a / (PATCH_MM / RES / 1000.0)
        iso = isolated_fraction(lum)
        ratio = a / (PHYSICAL_MM / 1000.0)
        note = ("EXAGGERATED (current)" if a == 0.0015 else
                "physical width" if abs(a - 0.000123) < 1e-6 else
                f"{ratio:.1f}x physical")
        if band_px < 3:
            note += "  <-- band under 3 px, may alias"
        print(f"{a:>11.6f} {band_px:>8.1f} {spread:>9.4f} {f.max():>6.2f} "
              f"{lum.mean():>7.3f} {100*iso:>8.3f}%  {note}")
        os.remove(cp)
    print()
    print("read: 'spread' is the visible chromatic variation the band contributes;")
    print("'isolated' is the aliasing signature. The honest choice is the smallest")
    print("scale that does NOT alias -- at or near the physical width if possible.")


if __name__ == "__main__":
    main()
