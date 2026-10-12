"""ensemble_study.py -- is the validation robust across wave phases?

Every number in EVIDENCE is at ONE wave phase (t = 0/1.7 s) and ONE sun
angle. PAPER_PLAN S2 lists ensemble statistics as NEEDS MEASUREMENT. This
runs the cheapest meaningful ensemble: 8 wave phases over a full ripple
cycle, solver bake + brute-force trace + correlation + edge dispersion at
each, reporting mean/std/min/max. If agreement collapses at some phases,
the single-phase numbers are cherry-picked whether we meant it or not.

Both sides share the identical phase convention: h += amp*sin(k*(u.x+u.y) +
t*(1+i)) -- solver water_h (showcase_main.cpp) and tracer wave_h
(verify_ray_map.py). Apples to apples.

Run:  luxvenv/Scripts/python tools/ensemble_study.py
"""
import os
import struct
import subprocess
import sys
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ray_map as V

ROOT = "D:/ValueProjects/caustics"
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
OUT = f"{ROOT}/out"
NPH = 8
NGRID = 512


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


def corr(a, b, k):
    h, w = a.shape
    A = a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    B = b[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    A = A - A.mean()
    B = B - B.mean()
    dd = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / dd) if dd > 0 else 0.0


def edges(field):
    H, W, _ = field.shape
    yy, xx = np.mgrid[0:H, 0:W]
    R = np.hypot((xx / (W - 1) - 0.5) * 320.0, (0.5 - yy / (H - 1)) * 320.0)
    out = []
    for c in range(3):
        v = field[:, :, c]
        mx = v.max()
        nb = 160
        b = np.clip((R / 160.0 * nb).astype(int), 0, nb - 1)
        prof = np.bincount(b.ravel(), weights=v.ravel(), minlength=nb)
        cnt = np.bincount(b.ravel(), minlength=nb)
        mean = np.where(cnt > 0, prof / np.maximum(cnt, 1), 0.0)
        idx = np.nonzero(mean > 0.02 * mx)[0]
        out.append(float((idx.max() + 1) / nb * 160.0) if idx.size else float("nan"))
    return out


def main():
    print(f"=== ensemble: {NPH} wave phases, {NGRID}^2 bake + brute-force each ===")
    rs8, rs64, edger, edgeb, offs = [], [], [], [], []
    for j in range(NPH):
        phase = 2 * np.pi * j / NPH
        cp = f"{OUT}/_ens_{j:02d}.png"
        p = subprocess.run(
            [EXE, "--res", str(NGRID), "--airy", "0.0015", "--n", "400",
             "--ssaa", "1", "--wave-t", f"{phase:.6f}",
             "--out", f"{OUT}/_ens_throw.png", "--dump-caustic", cp],
            capture_output=True, text=True, timeout=900)
        if not os.path.exists(cp):
            raise RuntimeError(f"bake failed at phase {phase}: {p.stderr[-300:]}")
        field = read_png16(cp)
        fld = field.mean(axis=2)
        V.PHASE = phase
        X, Y, nhit, nwall, nesc = V.trace(n_side=700)
        brute = V.to_grid(X, Y)
        fr = np.asarray(Image.fromarray(fld.astype(np.float32), mode="F")
                         .resize(brute.shape[::-1], Image.BOX))
        a = brute - brute.mean()
        b = fr - fr.mean()
        r8 = corr(a, b, 8)
        r64 = corr(a, b, 64)
        e = edges(field)
        # centroid offset
        t = V.tiles(brute, 32)
        u = V.tiles(fr, 32)
        tc = np.clip(t - np.median(t), 0, None)
        uc = np.clip(u - np.median(u), 0, None)
        k = 32
        rr, cc = np.mgrid[0:k, 0:k]
        bx = ((cc * tc).sum() / tc.sum() + 0.5) / k * 320.0 - 160.0
        by = 160.0 - ((rr * tc).sum() / tc.sum() + 0.5) / k * 320.0
        fx = ((cc * uc).sum() / uc.sum() + 0.5) / k * 320.0 - 160.0
        fy = 160.0 - ((rr * uc).sum() / uc.sum() + 0.5) / k * 320.0
        off = float(np.hypot(bx - fx, by - fy))
        rs8.append(r8)
        rs64.append(r64)
        edger.append(e[0])
        edgeb.append(e[2])
        offs.append(off)
        print(f"  phase {j + 1}/{NPH} t={phase:.3f}  r8 {r8:+.3f}  r64 {r64:+.3f}  "
              f"edge R {e[0]:.1f} B {e[2]:.1f}  R-B {e[0]-e[2]:+.1f}  off {off:.1f} mm")
        os.remove(cp)
    print()
    print("ensemble summary (mean +- std, min..max):")
    for tag, v in (("r@40mm", rs8), ("r@5mm", rs64), ("edge R", edger),
                   ("edge B", edgeb), ("offset mm", offs)):
        a = np.array(v)
        print(f"  {tag:10s} {a.mean():+.3f} +- {a.std():.3f}   [{a.min():+.3f}..{a.max():+.3f}]")
    rb = np.array(edger) - np.array(edgeb)
    print(f"  R-B split  {rb.mean():+.1f} +- {rb.std():.1f} mm   "
          f"[{'..'.join(f'{x:+.1f}' for x in (rb.min(), rb.max()))}]  "
          f"order holds all phases: {bool((rb > 0).all())}")


if __name__ == "__main__":
    main()
