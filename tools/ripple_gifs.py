"""ripple_gifs.py -- the three ripple GIFs, one camera, no exaggerated fringes.

Renders the same animating caustic three ways and encodes each as a looping GIF:

  ours    the wave-corrected field, RE-BAKED at every frame's wave phase
  cycles  Blender Cycles tracing the caustics itself
  spmm    PBRT-v4 SPPM, the reference conforming solver

Decisions, both measured rather than guessed (see the module notes):

  * airy_scale = 0.000123 m -- the PHYSICAL fringe width for this geometry
    (tools/fringe_scale.py). The previous clips used 1.5 mm, 12.2x too wide,
    chosen for visibility. tools/airy_honesty_sweep.py shows narrowing the band
    barely changes the chromatic variation (0.054 -> 0.060) because the colour
    is carried by the measured index dispersion, not by the fringe decoration;
    so the physical width removes the exaggeration at almost no cost.
  * camera az 110 / elev 38 / dist 0.62 / lens 50 -- tools/frame_test2.py
    measured the caustic's margin from the frame edges with a differential mask
    (injection on minus off) and this view puts the whole fan in frame with
    23-31% clearance on every side, broadside to the fan rather than down its
    length. PBRT gets a perspective camera matching it exactly.

Run:
  python tools/ripple_gifs.py --validate     # frame 0 only, compare framings
  python tools/ripple_gifs.py                # all 72 frames, all three, + GIFs
"""
import argparse
import os
import subprocess
import sys
import time

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
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
PBRT = f"{ROOT}/third_party/pbrt-v4/build/Release/pbrt.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
OUT = f"{ROOT}/out"
SRC = f"{OUT}/gif_src"

# --- measured choices
AIRY = 0.000123          # physical fringe width, metres
AZ, ELEV, DIST, LENS = 110.0, 38.0, 0.62, 50.0
BW, BH = 960, 540        # Blender render size
SW, SH = 640, 360        # SPPM render size (cost scales with pixels)
GW, GH = 640, 360        # GIF size, common to all three
FPS = 24
NFRAMES = 72

STUDIO = ["--studio", "--sun", "6.5", "--world", "0.55", "--gain", "0.25",
          "--sun-angle", "0.53", "--clamp-indirect", "0"]
SPPM_SPP = 256
SPPM_PHOTONS = 1000000
SPPM_RADIUS = 0.006


def sh(cmd, timeout, tag):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        print(f"    [{tag}] rc={p.returncode} {p.stderr[-300:]}")
    return p


def phase_of(f, n):
    return 2 * np.pi * f / n


# ------------------------------------------------------------------ our clip
def ours_frame(f, n):
    ph = phase_of(f, n)
    cb = f"{SRC}/_cb_{f:04d}.png"
    t0 = time.time()
    sh([EXE, "--res", "1024", "--airy", f"{AIRY:.6f}", "--n", "400", "--ssaa", "1",
        "--wave-t", f"{ph:.6f}", "--out", f"{OUT}/_g.png", "--dump-caustic", cb],
       900, "bake")
    tb = time.time() - t0
    t0 = time.time()
    sh([BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
        "--caustic", cb, "--out", f"{SRC}/ours/f{f:04d}.png",
        "--samples", "320", "--w", str(BW), "--h", str(BH),
        "--az", str(AZ), "--elev", str(ELEV), "--dist", str(DIST),
        "--lens", str(LENS), "--wave-t", f"{ph:.6f}"] + STUDIO, 3600, "blender")
    tr = time.time() - t0
    if os.path.exists(cb):
        os.remove(cb)
    return tb, tr


# --------------------------------------------------------------- cycles clip
def cycles_frame(f, n):
    ph = phase_of(f, n)
    t0 = time.time()
    sh([BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
        "--caustic", f"{OUT}/caustic_wavy.png", "--out", f"{SRC}/cycles/f{f:04d}.png",
        "--samples", "320", "--w", str(BW), "--h", str(BH),
        "--az", str(AZ), "--elev", str(ELEV), "--dist", str(DIST),
        "--lens", str(LENS), "--wave-t", f"{ph:.6f}",
        "--cycles-caustics", "--no-caustic"] + STUDIO, 3600, "blender")
    return time.time() - t0


# ----------------------------------------------------------------- spmm clip
def spmm_frame(f, n):
    ph = phase_of(f, n)
    geo = f"{SRC}/geo/f{f:04d}"
    t0 = time.time()
    sh([sys.executable, f"{ROOT}/tools/export_scene_obj.py",
        "--wave-t", f"{ph:.6f}", "--out-dir", geo], 600, "export")
    sh([sys.executable, f"{ROOT}/tools/pbrt_reference.py", "--build-scene",
        "--persp", "--az", str(AZ), "--elev", str(ELEV), "--dist", str(DIST),
        "--lens", str(LENS), "--w", str(SW), "--h", str(SH),
        "--geo", geo, "--spp", str(SPPM_SPP), "--photons", str(SPPM_PHOTONS),
        "--radius", str(SPPM_RADIUS), "--out", f"{SRC}/spmm/f{f:04d}.exr"],
       7200, "pbrt")
    return time.time() - t0


# -------------------------------------------------------------- exr -> png
def exr_to_png(src_dir, exr_names, png_dir):
    """PBRT writes EXR; convert via Mitsuba's bitmap reader (luxvenv)."""
    os.makedirs(png_dir, exist_ok=True)
    script = f'''
import sys
sys.path.insert(0, r"{ROOT}/third_party/luxvenv/Lib/site-packages")
import mitsuba as mi
mi.set_variant("scalar_spectral")
import numpy as np
from PIL import Image
for name in {exr_names!r}:
    a = np.array(mi.Bitmap(r"{src_dir}/" + name)).astype(np.float32)
    # PBRT's LookAt builds a left-handed frame; undo the X mirror so the SPMM
    # frames are oriented like the Blender ones (EVIDENCE 19.2)
    a = a[:, ::-1, :]
    rgb = np.clip(a ** (1 / 2.2), 0, 1) ** 2.2   # keep linear, just clamp
    rgb = np.clip(a, 0, None)
    m = rgb.max()
    rgb = np.clip(rgb / (m if m > 0 else 1), 0, 1) ** (1 / 2.2)
    Image.fromarray((rgb * 255).astype(np.uint8)).save(
        r"{png_dir}/" + name.replace(".exr", ".png"))
print("converted", len({exr_names!r}))
'''
    p = subprocess.run([f"{ROOT}/third_party/luxvenv/Scripts/python.exe", "-c", script],
                       capture_output=True, text=True, timeout=3600)
    return p.stdout.strip(), p.stderr[-400:] if p.returncode else ""


# ------------------------------------------------------------------- encode
def find_ffmpeg():
    """Return an ffmpeg that actually has palettegen.

    The ffmpeg first on PATH on this machine is N-55702 (Aug 2013), which
    predates palettegen/paletteuse entirely -- a GIF encode with it fails with
    "No such filter: palettegen". The WinGet Gyan full build has them.
    """
    import glob
    cands = [
        _WINGET_PKGS +
        r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-7.1-full_build/bin/ffmpeg.exe",
    ]
    cands += glob.glob(_WINGET_PKGS +
                       r"Gyan.FFmpeg*/**/bin/ffmpeg.exe", recursive=True)
    cands.append("ffmpeg")
    for c in cands:
        try:
            r = subprocess.run([c, "-hide_banner", "-filters"],
                               capture_output=True, text=True, timeout=60)
            if "palettegen" in r.stdout:
                return c
        except Exception:
            continue
    print("  WARNING: no ffmpeg with palettegen found; fallback will be lossy")
    return "ffmpeg"


FFMPEG = find_ffmpeg()


def encode_gif(png_dir, out_gif, w=GW, h=GH):
    pal = f"{png_dir}/_palette.png"
    sh([FFMPEG, "-y", "-framerate", str(FPS), "-i", f"{png_dir}/f%04d.png",
        "-vf", f"scale={w}:{h}:flags=lanczos,palettegen=max_colors=128:stats_mode=diff",
        pal], 1800, "palettegen")
    p = sh([FFMPEG, "-y", "-framerate", str(FPS), "-i", f"{png_dir}/f%04d.png",
            "-i", pal, "-lavfi",
            f"scale={w}:{h}:flags=lanczos[x];[x][1:v]paletteuse="
            f"dither=bayer:bayer_scale=3:diff_mode=rectangle",
            "-loop", "0", out_gif], 3600, "paletteuse")
    ok = os.path.exists(out_gif)
    if os.path.exists(pal):
        os.remove(pal)
    print(f"  gif -> {out_gif} {'OK' if ok else 'FAILED'} "
          f"({os.path.getsize(out_gif)/1e6:.2f} MB)" if ok else "  gif FAILED")
    return ok


# ------------------------------------------------------------------ validate
def validate():
    print("=== validate: frame 0 from each renderer, compare framing ===")
    for d in ("ours", "cycles", "spmm"):
        os.makedirs(f"{SRC}/{d}", exist_ok=True)
    tb, tr = ours_frame(0, NFRAMES)
    print(f"  ours   bake {tb:.2f}s render {tr:.1f}s")
    tc = cycles_frame(0, NFRAMES)
    print(f"  cycles render {tc:.1f}s")
    ts = spmm_frame(0, NFRAMES)
    print(f"  spmm   render {ts:.1f}s")
    out, err = exr_to_png(f"{SRC}/spmm", ["f0000.exr"], f"{SRC}/spmm")
    print(f"  exr->png: {out} {err}")

    def bbox(path, tag):
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
        lum = a.mean(axis=2)
        # caustic = the bright warm core; top 0.5% of luminance
        thr = np.percentile(lum, 99.5)
        m = lum >= thr
        ys, xs = np.nonzero(m)
        H, W = lum.shape
        print(f"    {tag:<7} {W}x{H}  bbox x[{xs.min():>3}..{xs.max():>3}] "
              f"y[{ys.min():>3}..{ys.max():>3}]  "
              f"centroid ({xs.mean()/W:.2f}, {ys.mean()/H:.2f})")
        return W, H, xs, ys

    print("  framing comparison (fractions of each frame):")
    for tag, path in (("ours", f"{SRC}/ours/f0000.png"),
                      ("cycles", f"{SRC}/cycles/f0000.png"),
                      ("spmm", f"{SRC}/spmm/f0000.png")):
        if os.path.exists(path):
            W, H, xs, ys = bbox(path, tag)
            print(f"            rel bbox x[{xs.min()/W:.2f}..{xs.max()/W:.2f}] "
                  f"y[{ys.min()/H:.2f}..{ys.max()/H:.2f}]")
        else:
            print(f"    {tag}: MISSING {path}")
    print()
    print("  cameras agree if the relative bboxes overlap and the centroids")
    print("  land in the same region of the frame.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="frame 0 only")
    ap.add_argument("--frames", type=int, default=NFRAMES)
    ap.add_argument("--skip-ours", action="store_true")
    ap.add_argument("--skip-cycles", action="store_true")
    ap.add_argument("--skip-spmm", action="store_true")
    ap.add_argument("--encode-only", action="store_true")
    args = ap.parse_args()

    if args.validate:
        validate()
        return

    os.makedirs(f"{SRC}/ours", exist_ok=True)
    os.makedirs(f"{SRC}/cycles", exist_ok=True)
    os.makedirs(f"{SRC}/spmm", exist_ok=True)
    n = args.frames

    if not args.encode_only:
        if not args.skip_ours:
            print(f"=== ours: {n} frames, re-baked at each phase, airy {AIRY} ===")
            tb = tr = 0.0
            for f in range(n):
                a, b = ours_frame(f, n)
                tb += a
                tr += b
                if f % 8 == 0 or f == n - 1:
                    print(f"    {f+1}/{n}  bake {a:.2f}s render {b:.1f}s  "
                          f"cum render {tr:.0f}s")
            print(f"  ours total: bake {tb:.1f}s render {tr:.1f}s")

        if not args.skip_cycles:
            print(f"=== cycles: {n} frames, path-traced caustics ===")
            tr = 0.0
            for f in range(n):
                tr += cycles_frame(f, n)
                if f % 8 == 0 or f == n - 1:
                    print(f"    {f+1}/{n}  cum render {tr:.0f}s")
            print(f"  cycles total: render {tr:.1f}s")

        if not args.skip_spmm:
            print(f"=== spmm: {n} frames at {SW}x{SH}, {SPPM_SPP} iter x "
                  f"{SPPM_PHOTONS//1000}k photons ===")
            ts = 0.0
            for f in range(n):
                ts += spmm_frame(f, n)
                if f % 4 == 0 or f == n - 1:
                    print(f"    {f+1}/{n}  cum {ts:.0f}s")
            print(f"  spmm total: render {ts:.1f}s")
            names = [f"f{f:04d}.exr" for f in range(n)]
            out, err = exr_to_png(f"{SRC}/spmm", names, f"{SRC}/spmm")
            print(f"  exr->png: {out}")
            if err:
                print(f"  stderr: {err}")

    print("=== encoding GIFs ===")
    for tag, d in (("ours", f"{SRC}/ours"), ("cycles", f"{SRC}/cycles"),
                   ("spmm", f"{SRC}/spmm")):
        if os.path.exists(f"{d}/f0000.png"):
            encode_gif(d, f"{OUT}/ripple_{tag}.gif")
        else:
            print(f"  {tag}: no frames, skipped")


if __name__ == "__main__":
    main()
