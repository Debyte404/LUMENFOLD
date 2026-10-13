"""colour_experiments.py -- the rendered visual proof for the colour experiments.

tools/colour_study.py computes the colours numerically from the ray map. This drives
the actual renderer (src/app/showcase_main.cpp) so the colours are seen rather than
tabulated, and so the two can be compared.

Three experiments:

  media      every glass x water combination, one still each, as a contact sheet
  sun        FIXED CAMERA, the sun swept in azimuth about the glass. This is the
             one that needs --cam-fixed: by default the frame follows the caustic,
             and a following frame turns a rotating caustic into an apparently
             static one -- the pan cancels exactly the motion being measured.
  suncolour  the source spectrum swept from warm to cool with the medium clear, so
             the source's own contribution is visible on its own.

Media come from tools/colour_study.py, so the rendered absorption is the same set
of coefficients the numeric study uses and the two cannot drift apart.

Usage:  python tools/colour_experiments.py [--mode media|sun|suncolour|verify|all]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from colour_study import GLASS, WATER, LAMBDAS, ILLUMINANTS, illuminant_weights  # noqa: E402

EXE = os.path.join(_ROOT, "build", "src", "app", "Release", "showcase.exe")
MEDIA = os.path.join(_ROOT, "docs", "media")
TMP = os.path.join(_ROOT, "out", "colour_frames")

# The reference frame, from a default-sun run's [frame] line. Used to lock the
# camera for the rotation experiment.
REF_CENTROID = (0.0473, 0.0246)
REF_EXTENT = 0.0984
# az = atan2(0.42, 0.80), el = asin(0.43/|kSun|): reproduces the default direction.
REF_AZ, REF_EL = 27.699472808054995, 25.449840953628105

# The renderer's own sun irradiance, used as the reference when no --sun-rgb is given.
REF_SUN_RGB = (19.0, 17.6, 15.8)

# The renderer's default fringe width, and the physical Airy scale for this geometry at
# 550 nm. The default is 12.2x the physical value: at 600 px the physical fringe is
# under two pixels and would not be visible, so the exaggeration is deliberate -- but it
# must be STATED wherever it is shown, or a reader measures a fringe and gets 12x the
# truth. Ripple clips and the no-exaggeration figure pass --airy 0.000123 explicitly.
AIRY_RENDER = 0.0015
AIRY_PHYSICAL = 0.000123
AIRY_FACTOR = AIRY_RENDER / AIRY_PHYSICAL


def render(out_png, n=900, sun_az=None, sun_el=None, glass=None, water=None,
           sun_rgb=None, fixed_cam=False, res=None, ssaa=None, eye=None, extra=()):
    """One frame.

    `n` is the OUTPUT WIDTH in pixels, not a sample count -- the flag is named that
    way in the renderer. `res` is the caustic bake resolution: the airy fringe rule
    wants about 4.8 px per feature at 1024, so a finer bake resolves finer fringes.
    `eye` is (azimuth, elevation, zoom) in degrees and a distance factor; the default
    (-120, 26, 1.0) reproduces the renderer's original hardcoded direction.
    """
    cmd = [EXE, "--n", str(n), "--out", out_png]
    if res is not None:
        cmd += ["--res", str(res)]
    if ssaa is not None:
        cmd += ["--ssaa", str(ssaa)]
    if eye is not None:
        cmd += ["--eye-az", "%.3f" % eye[0], "--eye-el", "%.3f" % eye[1],
                "--eye-zoom", "%.3f" % eye[2]]
    if sun_az is not None or sun_el is not None:
        cmd += ["--sun-az", str(REF_AZ if sun_az is None else sun_az),
                "--sun-el", str(REF_EL if sun_el is None else sun_el)]
    if glass is not None:
        cmd += ["--glass-abs", ",".join("%.6g" % v for v in glass)]
    if water is not None:
        cmd += ["--water-abs", ",".join("%.6g" % v for v in water)]
    if sun_rgb is not None:
        cmd += ["--sun-rgb", ",".join("%.6g" % v for v in sun_rgb)]
    if fixed_cam:
        cmd += ["--cam-fixed", "%.6f" % REF_CENTROID[0], "%.6f" % REF_CENTROID[1],
                "%.6f" % REF_EXTENT]
    cmd += list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_png):
        raise RuntimeError(f"render failed: {' '.join(cmd)}\n{r.stdout[-400:]}{r.stderr[-400:]}")
    return r.stdout


def sun_rgb_for(name):
    """Planck shape mapped onto the renderer's irradiance scale.

    illuminant_weights is normalised on green, so scaling the reference irradiance
    by it keeps the green channel fixed and moves only the tint -- which is what a
    source-colour experiment should vary.
    """
    w = np.asarray(illuminant_weights(name), float)
    w = w / w[1]
    return tuple(np.round(np.asarray(REF_SUN_RGB, float) * w, 4))


# ---------------------------------------------------------------------------
# experiments
# ---------------------------------------------------------------------------

def exp_media(n=1100):
    """Every glass x water combination, as one labelled contact sheet."""
    os.makedirs(TMP, exist_ok=True)
    glasses = list(GLASS.keys())
    waters = list(WATER.keys())
    tiles = {}
    for g in glasses:
        for w in waters:
            p = os.path.join(TMP, f"{g}_{w}.png")
            render(p, n=n, glass=GLASS[g], water=WATER[w])
            tiles[(g, w)] = p
            print(f"  rendered glass={g:7s} water={w:7s}")

    im0 = Image.open(tiles[(glasses[0], waters[0])])
    scale = 340.0 / im0.size[0]
    tw, th = 340, int(round(im0.size[1] * scale))
    LAB, PAD = 20, 6
    W = len(waters) * (tw + PAD) + 130
    H = len(glasses) * (th + LAB + PAD) + 46
    sheet = Image.new("RGB", (W, H), (22, 22, 24))
    d = ImageDraw.Draw(sheet)
    for j, wname in enumerate(waters):
        d.text((130 + j * (tw + PAD) + tw / 2 - 26, 8), wname, fill=(240, 240, 240))
    for i, gname in enumerate(glasses):
        y = 30 + i * (th + LAB + PAD)
        d.text((10, y + th / 2), gname, fill=(240, 240, 240))
        for j, wname in enumerate(waters):
            x = 130 + j * (tw + PAD)
            sheet.paste(Image.open(tiles[(gname, wname)]).resize((tw, th), Image.LANCZOS), (x, y))
            d.rectangle([x - 1, y - 1, x + tw, y + th], outline=(70, 70, 74))
    out = os.path.join(MEDIA, "colour_media_grid.png")
    sheet.save(out, optimize=True)
    print(f"  wrote {out}  ({sheet.size[0]}x{sheet.size[1]}, "
          f"{os.path.getsize(out)/1048576:.2f} MB)")
    return out


def exp_sun(n=1520, frames=96, sweep=360.0, res=2048, eye=None):
    """Fixed camera, sun swept in azimuth: the caustic orbits the glass.

    `eye` is (azimuth, elevation, zoom). The default of (None) keeps the renderer's own
    direction; tools/camera_sweep.py picks a better one by measuring which camera keeps
    the caustic in frame for the WHOLE revolution, since the worst sun position is what
    a viewer sees as the animation losing its subject.
    """
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):
        if f.startswith("sun_"):
            os.remove(os.path.join(TMP, f))
    for i in range(frames):
        az = REF_AZ + sweep * i / frames
        p = os.path.join(TMP, f"sun_{i:04d}.png")
        render(p, n=n, sun_az=az, fixed_cam=True, res=res, eye=eye)
        if i % 12 == 0:
            print(f"  frame {i}/{frames}  az={az:.1f}")
    out = os.path.join(MEDIA, "colour_sun_orbit.gif")
    _encode(os.path.join(TMP, "sun_%04d.png"), out)
    return out


def exp_suncolour(n=620, frames=32):
    """Source spectrum swept warm -> cool, medium clear."""
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):
        if f.startswith("sc_"):
            os.remove(os.path.join(TMP, f))
    # 2000 K .. 12000 K in reciprocal space, so the eye sees even steps in tint,
    # and then back again. A one-way ramp loops with a 20x jump at the wrap: the
    # last frame is the cool end and the first is the warm end, so a viewer
    # repeating the GIF sees a flash rather than a sweep. Measured loop-to-median
    # ratio was 20.2 for the ramp; the palindrome makes the wrap a normal step.
    half = max(2, frames // 2)
    up = 1.0 / np.linspace(1 / 2000.0, 1 / 12000.0, half)
    Temps = np.concatenate([up, up[::-1][1:]])
    for i, T in enumerate(Temps):
        w = np.asarray([_planck(l, T) for l in LAMBDAS])
        w = w / w[1]
        rgb = tuple(np.round(np.asarray(REF_SUN_RGB) * w, 4))
        p = os.path.join(TMP, f"sc_{i:04d}.png")
        render(p, n=n, sun_rgb=rgb, fixed_cam=True)
        if i % 6 == 0:
            print(f"  frame {i}/{frames}  T={T:.0f} K")
    out = os.path.join(MEDIA, "colour_sun_sweep.gif")
    _encode(os.path.join(TMP, "sc_%04d.png"), out)
    return out


def _planck(lam_nm, T):
    h, c, kB = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    lam = lam_nm * 1e-9
    return (2 * h * c ** 2 / lam ** 5) / (np.expm1(h * c / (lam * kB * T)))


def find_ffmpeg():
    import glob
    c = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                               "Microsoft", "WinGet", "Packages",
                               "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"), recursive=True)
    return c[0] if c else "ffmpeg"


def _encode(pattern, out, max_w=1520):
    """Encode frames to a GIF, capped in width.

    `max_w` is a safety rail, not a policy: the render stays high-resolution because the
    FIGURE panel needs the pixels, and the GIF is allowed up to the render width. An
    earlier cap of 900 px was there to keep the repository small; the author has said the
    extra size is wanted, so the cap now only prevents an accidental blow-up.
    """
    import glob
    ff = find_ffmpeg()
    tmp = os.path.dirname(pattern)
    pal = os.path.join(tmp, "_pal.png")
    scale = "scale='min(%d,iw)':-1:flags=lanczos" % max_w
    for stage, args in (
        ("palettegen", [ff, "-y", "-loglevel", "error", "-i", pattern,
                        "-vf", "%s,palettegen=max_colors=96:stats_mode=diff" % scale,
                        pal]),
        ("paletteuse", [ff, "-y", "-loglevel", "error", "-i", pattern, "-i", pal,
                        "-lavfi", "%s[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:"
                                  "diff_mode=rectangle" % scale, "-loop", "0", out]),
    ):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg {stage} failed: {r.stderr[-400:]}")
    print(f"  wrote {out}  ({os.path.getsize(out)/1048576:.2f} MB)")
    for f in glob.glob(os.path.join(tmp, "*.png")):
        os.remove(f)
    return out


def verify():
    """The flag must reproduce the default, or every comparison is confounded.

    Bit-equality is achievable and is what is asserted. Getting there needed the
    azimuth and elevation at FULL double precision: kSun is {0.80, 0.42, -0.43},
    not exactly unit length (|kSun| = 1.000650), and normalising it is what the
    renderer does, so az/el must round-trip to the last bit. At six decimals the
    image differed by up to 5 levels on 0.04% of pixels -- small, but a real
    direction change rather than the identity, and enough to confound a
    frame-by-frame comparison. At full precision the difference is exactly zero.
    """
    a = render(os.path.join(_ROOT, "out", "_ver_default.png"), n=500)
    b = render(os.path.join(_ROOT, "out", "_ver_ref.png"), n=500,
               sun_az=REF_AZ, sun_el=REF_EL)

    def edges(s):
        return [l.split("r")[1].split("mm")[0].strip()
                for l in s.splitlines() if "edge  ch" in l]

    ea, eb = edges(a), edges(b)
    print(f"  default edges      : {ea}")
    print(f"  explicit az/el     : {eb}")
    same_diag = ea == eb

    ia = np.asarray(Image.open(os.path.join(_ROOT, "out", "_ver_default.png")), dtype=float)
    ib = np.asarray(Image.open(os.path.join(_ROOT, "out", "_ver_ref.png")), dtype=float)
    mad = float(np.abs(ia - ib).mean())
    mxd = float(np.abs(ia - ib).max())
    frac = float((np.abs(ia - ib) > 0).mean())
    print(f"  diagnostics identical : {same_diag}")
    print(f"  pixel mean |diff|     : {mad:.6f}  (of 255)")
    print(f"  pixel max  |diff|     : {mxd:.0f} levels")
    print(f"  fraction differing    : {frac*100:.4f}%")
    ok = same_diag and mxd == 0.0
    print(f"  bit-identical         : {ok}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all",
                    choices=["media", "sun", "suncolour", "verify", "all"])
    ap.add_argument("--frames", type=int, default=72)
    # Camera for the rotating-source sweep. Chosen by tools/camera_sweep.py, which
    # measures which direction keeps the caustic in frame across the whole revolution.
    ap.add_argument("--eye-az", type=float, default=None)
    ap.add_argument("--eye-el", type=float, default=None)
    ap.add_argument("--eye-zoom", type=float, default=1.0)
    a = ap.parse_args()

    if a.mode in ("verify", "all"):
        print("verify: --sun-az/--sun-el reproduce the default")
        if not verify():
            print("  FAILED: the override does not reproduce the default")
            return 1
    if a.mode in ("media", "all"):
        print("\nmedia: every glass x water combination")
        exp_media()
    if a.mode in ("sun", "all"):
        print("\nsun: fixed camera, sun swept about the glass")
        exp_sun(frames=a.frames, eye=(a.eye_az, a.eye_el, a.eye_zoom)
                if a.eye_az is not None else None)
    if a.mode in ("suncolour", "all"):
        print("\nsuncolour: source spectrum swept 2000 K -> 12000 K")
        exp_suncolour()
    return 0


if __name__ == "__main__":
    sys.exit(main())
