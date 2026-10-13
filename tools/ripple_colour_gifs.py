"""ripple_colour_gifs.py -- the ripple animation rendered through RED media.

Same camera, Airy width, studio rig and frame count as docs/media/ripple_ours.gif,
so the three new clips sit beside it as a like-for-like comparison. The only
difference is the medium.

The colour has to be set in TWO places, because the pipeline is bake -> render and
each stage carries a different part of the light:

  * `showcase --water-abs/--glass-abs` tints the BAKED caustic field. The caustic is
    a light-side quantity, so its colour is set by what the sunlight crossed before
    landing (see EVIDENCE 14.5p). This is what makes the caustic pattern red.
  * `blender_scene --water-absorb/--glass-absorb` tints the glass and water BODIES,
    through a Blender Volume Absorption node driven by the same per-metre
    coefficients.

A note on why the Blender side needs care: `scene.cycles.volume_bounces` defaults
to 0, and with it at 0 Cycles SILENTLY ignores a connected volume shader -- the
absorption is built into the material, never integrated, and the medium renders
colourless with no warning anywhere. blender_scene.py now sets it.

Exposure is deliberately NOT re-solved per clip. The Blender render is the final
image, so a red medium gives a genuinely darker frame. Re-normalising each clip
would hide exactly the light loss the medium causes.

Coefficients are per-metre Beer-Lambert, chosen so each medium transmits roughly
T = (0.90, 0.15, 0.03) over its real path in this scene -- ~90 mm of water and
~3.5 mm of glass. They are experiment parameters, not measured materials.
"""
import argparse
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

EXE = f"{_ROOT}/build/src/app/Release/showcase.exe"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{_ROOT}/tools/blender_scene.py"
OUT = f"{_ROOT}/out/gif_colour"
MEDIA = f"{_ROOT}/docs/media"

# --- identical to ripple_gifs.py: the clip must be comparable to ripple_ours.gif
AIRY = 0.000123
AZ, ELEV, DIST, LENS = 110.0, 38.0, 0.62, 50.0
BW, BH = 960, 540
GW, GH = 640, 360
FPS = 24
NFRAMES = 72
STUDIO = ["--studio", "--sun", "6.5", "--world", "0.55", "--gain", "0.25",
          "--sun-angle", "0.53", "--clamp-indirect", "0"]

# per-metre, tuned so each medium transmits ~(0.90, 0.15, 0.03) over its path here
RED_WATER = (1.17, 21.0, 38.9)     # ~90 mm of water
RED_GLASS = (30.0, 344.0, 721.0)   # ~3.5 mm of glass

CASES = {
    "water": (RED_WATER, None),
    "glass": (None, RED_GLASS),
    "both": (RED_WATER, RED_GLASS),
}


def sh(cmd, timeout, tag):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        print(f"    [{tag}] rc={p.returncode} {p.stderr[-300:]}")
    return p


def phase_of(f, n):
    return 2 * 3.141592653589793 * f / n


def frame(f, n, water, glass, tmp):
    """One frame: bake the caustic with the medium, then render the scene."""
    ph = phase_of(f, n)
    cb = f"{tmp}/_cb_{f:04d}.png"
    png = f"{tmp}/f{f:04d}.png"
    cmd = [EXE, "--res", "1024", "--airy", f"{AIRY:.6f}", "--n", "400", "--ssaa", "1",
           "--wave-t", f"{ph:.6f}", "--out", f"{tmp}/_g.png", "--dump-caustic", cb]
    if water:
        cmd += ["--water-abs", ",".join("%.6g" % v for v in water)]
    if glass:
        cmd += ["--glass-abs", ",".join("%.6g" % v for v in glass)]
    sh(cmd, 900, "bake")

    bc = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
          "--caustic", cb, "--out", png, "--samples", "320", "--w", str(BW), "--h", str(BH),
          "--az", str(AZ), "--elev", str(ELEV), "--dist", str(DIST), "--lens", str(LENS),
          "--wave-t", f"{ph:.6f}"] + STUDIO
    if water:
        bc += ["--water-absorb", ",".join("%.6g" % v for v in water)]
    if glass:
        bc += ["--glass-absorb", ",".join("%.6g" % v for v in glass)]
    sh(bc, 3600, "blender")
    if os.path.exists(cb):
        os.remove(cb)
    return os.path.exists(png)


def find_ffmpeg():
    """The WinGet Gyan build: the 2013 ffmpeg on PATH predates palettegen."""
    import glob
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft", "WinGet", "Packages")
    for pat in ("Gyan.FFmpeg*/**/bin/ffmpeg.exe", "Gyan.FFmpeg*/**/ffmpeg.exe"):
        for p in glob.glob(os.path.join(base, pat), recursive=True):
            r = subprocess.run([p, "-filters"], capture_output=True, text=True)
            if "palettegen" in r.stdout:
                return p
    return "ffmpeg"


def encode(tmp, out_gif, ffmpeg):
    """The proven encode: 128-colour diff-mode palette, bayer scale 3, rectangle."""
    pal = f"{tmp}/_pal.png"
    sh([ffmpeg, "-y", "-framerate", str(FPS), "-start_number", "0",
        "-i", f"{tmp}/f%04d.png", "-vf",
        f"scale={GW}:{GH}:flags=lanczos,palettegen=max_colors=128:stats_mode=diff",
        pal], 1800, "palettegen")
    sh([ffmpeg, "-y", "-framerate", str(FPS), "-start_number", "0",
        "-i", f"{tmp}/f%04d.png", "-i", pal, "-lavfi",
        f"scale={GW}:{GH}:flags=lanczos[x];[x][1:v]paletteuse="
        f"dither=bayer:bayer_scale=3:diff_mode=rectangle",
        "-loop", "0", out_gif], 1800, "paletteuse")
    return os.path.exists(out_gif)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all", choices=["all"] + list(CASES))
    ap.add_argument("--frames", type=int, default=NFRAMES)
    ap.add_argument("--samples", type=int, default=320)
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(MEDIA, exist_ok=True)
    ffmpeg = find_ffmpeg()
    print(f"  ffmpeg: {ffmpeg}")

    todo = list(CASES) if a.case == "all" else [a.case]
    for name in todo:
        water, glass = CASES[name]
        tmp = f"{OUT}/{name}"
        os.makedirs(tmp, exist_ok=True)
        for f in os.listdir(tmp):
            if f.startswith(("f", "_")):
                os.remove(os.path.join(tmp, f))
        t0 = time.time()
        ok = 0
        for f in range(a.frames):
            if frame(f, a.frames, water, glass, tmp):
                ok += 1
            if f % 8 == 0 or f == a.frames - 1:
                print(f"    {name}: frame {f + 1}/{a.frames}  ({time.time() - t0:.0f}s)")
        gif = f"{MEDIA}/ripple_{name}_red.gif"
        if ok == a.frames and encode(tmp, gif, ffmpeg):
            print(f"  wrote {gif}  ({os.path.getsize(gif) / 1048576:.2f} MB)")
        else:
            print(f"  FAILED {name}: {ok}/{a.frames} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
