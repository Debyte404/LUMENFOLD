"""fix_spmm_exposure.py -- calibrate the SPMM clip's exposure to the Blender one.

PBRT writes linear HDR; Blender's frames are AgX-tonemapped. Two things went
wrong before this version, both recorded because they are the same class of
estimator error this project keeps finding:

  1. the first attempt divided by each frame's own max -- that injects
     brightness flicker into an animation;
  2. the second matched medians against the inverse-sRGB of an AgX image, which
     is not scene radiance. The frame is also 46% BLACK BACKGROUND, so its
     whole-frame median (0.036) is a background statistic, not the table's. That
     produced a scale of 15 when the correct value is ~0.6, blowing 49% of the
     frame.

The right statistic is the TABLE, and the right target is the reference's own
output value at the same percentile. This solves for one global scale by
bisection so that the SPMM table's p75 in the OUTPUT domain equals the Blender
frame's p75, then applies that single scale to every frame.
"""
import glob
import os
import subprocess
import sys

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

# WinGet's package root, resolved per-account instead of hardcoded.
_WINGET_PKGS = _os.path.join(
    _os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"
).replace("\\", "/") + "/"

ROOT = _ROOT
SRC = f"{ROOT}/out/gif_src"
PBRT_DIR = f"{SRC}/spmm"
REF = f"{SRC}/ours/f0000.png"
PCT = 75.0          # the lit table; the frame is ~46% black background


def linear_to_srgb(a):
    return np.where(a <= 0.0031308, a * 12.92,
                    1.055 * np.power(np.clip(a, 0, None), 1 / 2.4) - 0.055)


def main():
    sys.path.insert(0, f"{ROOT}/third_party/luxvenv/Lib/site-packages")
    import mitsuba as mi
    mi.set_variant("scalar_spectral")

    ref = np.asarray(Image.open(REF).convert("RGB")).astype(np.float32) / 255.0
    ref_lum = ref.mean(axis=2)
    target = float(np.percentile(ref_lum, PCT))
    print(f"reference (ours): p{PCT:.0f} = {target:.4f} (normalised), "
          f"median {np.median(ref_lum):.4f}")

    exrs = sorted(glob.glob(f"{PBRT_DIR}/*.exr"))
    a0 = np.array(mi.Bitmap(exrs[0])).astype(np.float32)[:, ::-1, :]
    lum0 = a0.mean(axis=2)
    print(f"spmm raw: p{PCT:.0f} = {np.percentile(lum0, PCT):.5f} (linear), "
          f"p1 = {np.percentile(lum0,1):.5f}, frac black = "
          f"{100*(lum0 < 0.001).mean():.1f}%")

    # bisect one global scale so the output p75 matches the reference
    lo, hi = 0.01, 4.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        v = float(np.percentile(np.clip(linear_to_srgb(a0 * mid), 0, 1).mean(axis=2), PCT))
        if v < target:
            lo = mid
        else:
            hi = mid
    scale = 0.5 * (lo + hi)
    print(f"-> solved global scale {scale:.4f}")

    out0 = np.clip(linear_to_srgb(a0 * scale), 0, 1)
    lum_out = out0.mean(axis=2)
    print(f"   check: spmm p{PCT:.0f} -> {np.percentile(lum_out,PCT):.4f} "
          f"(target {target:.4f})   blown {(out0.max(axis=2)>=254).mean()*100:.2f}% "
          f"(ours {(ref.max(axis=2)>=254).mean()*100:.2f}%)")

    for p in exrs:
        a = np.array(mi.Bitmap(p)).astype(np.float32)[:, ::-1, :]
        srgb = np.clip(linear_to_srgb(a * scale), 0, 1)
        Image.fromarray((srgb * 255).astype(np.uint8)).save(p.replace(".exr", ".png"))
    print(f"converted {len(exrs)} frames with the single global scale")

    # re-encode with a palettegen-capable ffmpeg
    cands = glob.glob(_WINGET_PKGS +
                      r"Gyan.FFmpeg*/**/bin/ffmpeg.exe", recursive=True) + ["ffmpeg"]
    FF = next((c for c in cands if "palettegen" in subprocess.run(
        [c, "-hide_banner", "-filters"], capture_output=True, text=True).stdout), "ffmpeg")
    pal = f"{PBRT_DIR}/_pal.png"
    subprocess.run([FF, "-y", "-framerate", "24", "-i", f"{PBRT_DIR}/f%04d.png",
                    "-vf", f"scale=640:360:flags=lanczos,palettegen=max_colors=128:stats_mode=diff",
                    pal], capture_output=True, text=True, timeout=1800)
    gif = f"{ROOT}/out/ripple_spmm.gif"
    subprocess.run([FF, "-y", "-framerate", "24", "-i", f"{PBRT_DIR}/f%04d.png",
                    "-i", pal, "-lavfi",
                    "scale=640:360:flags=lanczos[x];[x][1:v]paletteuse="
                    "dither=bayer:bayer_scale=3:diff_mode=rectangle",
                    "-loop", "0", gif], capture_output=True, text=True, timeout=3600)
    print(f"re-encoded {gif} ({os.path.getsize(gif)/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
