"""make_hero.py -- the README's headline visual.

A three-panel side-by-side of the SAME frame of the SAME animation: our
wave-corrected field, Blender Cycles tracing the caustics itself, and PBRT-v4 SPPM.
These are the exact frames the shipped ripple GIFs were encoded from, so the hero
cannot drift from the artefacts it advertises.

Emits:
  docs/media/hero_comparison.png    one representative frame, labelled
  docs/media/hero_comparison.gif    the full 72-frame cycle, labelled
"""
import io
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

REPO = r"D:/ValueProjects/caustics"
SRC = os.path.join(REPO, "out", "gif_src")
MEDIA = os.path.join(REPO, "docs", "media")

PANELS = [
    ("ours", "Ours — wave-corrected", (255, 255, 255)),
    ("cycles", "Blender Cycles — path traced", (255, 255, 255)),
    ("spmm", "PBRT-v4 SPPM — photon mapping", (255, 255, 255)),
]

LABEL_H = 26
BORDER = 3
BG = (16, 16, 18)


def frames_for(name):
    """The frame sequence, selected by a STRICT numeric pattern.

    A bare `*.png` glob plus sort is wrong here: out/gif_src/spmm also holds a
    leftover `_pal.png` (the palette scratch file from an earlier encode) and the
    .pbrt and .exr scene files that sit beside them. `_` sorts before `f`, so the palette image became
    frame 0 and every subsequent SPMM panel was shifted one frame ahead of the other
    two -- which is exactly the "weird flicker" it looks like: a bright flash on the
    first frame and a permanent one-frame desynchronisation after it.

    ripple_gifs.py never had this bug because it hands ffmpeg the printf pattern
    `f%04d.png`, which the scratch file cannot match. Same discipline here.
    """
    d = os.path.join(SRC, name)
    out = []
    for fn in os.listdir(d):
        m = re.fullmatch(r"f(\d{4})\.png", fn)
        if m:
            out.append((int(m.group(1)), os.path.join(d, fn)))
    return [p for _, p in sorted(out)]


def label(im, text):
    """Return the frame with a caption bar above it."""
    w = im.size[0]
    canvas = Image.new("RGB", (w, im.size[1] + LABEL_H), BG)
    canvas.paste(im, (0, LABEL_H))
    d = ImageDraw.Draw(canvas)
    try:
        tw = d.textlength(text)
    except Exception:
        tw = len(text) * 6
    d.text(((w - tw) / 2, 7), text, fill=(255, 255, 255))
    return canvas


def row(idx, panel_w=None):
    """The three panels for frame `idx`, side by side, with a border each.

    `panel_w` rescales each panel; composing at the final display size keeps the
    ffmpeg graph trivial (palettegen/paletteuse with no scaling filters), because
    paletteuse fails with an internal error when the graph rescales between the
    palette and its use.
    """
    panels = []
    for name, cap, _c in PANELS:
        fs = frames_for(name)
        im = Image.open(fs[idx % len(fs)]).convert("RGB")
        if panel_w:
            h = max(1, round(im.size[1] * panel_w / im.size[0]))
            im = im.resize((panel_w, h), Image.LANCZOS)
        im = label(im, cap)
        b = Image.new("RGB", (im.size[0] + 2 * BORDER, im.size[1] + 2 * BORDER), (60, 60, 66))
        b.paste(im, (BORDER, BORDER))
        panels.append(b)
    h = max(p.size[1] for p in panels)
    W = sum(p.size[0] for p in panels) + (len(panels) - 1) * 8
    out = Image.new("RGB", (W, h), BG)
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.size[0] + 8
    return out


def find_ffmpeg():
    for c in [
        r"C:/Users/Lenovo/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-7.1-full_build/bin/ffmpeg.exe",
    ]:
        if os.path.exists(c):
            return c
    import glob
    h = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                               "Microsoft", "WinGet", "Packages",
                               "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"), recursive=True)
    return h[0] if h else "ffmpeg"


def main():
    n = min(len(frames_for(p[0])) for p in PANELS)
    print(f"frames per panel: {n}")

    # The three sources are NOT the same resolution: ours and cycles render at
    # 960x540, the SPPM frames at 640x360, and spmm/ also holds .pbrt and .exr
    # siblings. Composing the still at native size therefore produced panels of
    # 966, 966 and 646 px -- a visibly lopsided comparison. Match the SMALLEST
    # source rather than upscaling it: enlarging the SPPM panel would make it
    # blurrier than the other two and misrepresent what was compared.
    PANEL_W = 640

    # ---- static: the frame one third into the cycle, mid-ripple
    pick = n // 3
    still = row(pick, panel_w=PANEL_W)
    p_still = os.path.join(MEDIA, "hero_comparison.png")
    still.save(p_still, optimize=True)
    print(f"  {p_still}  ({still.size[0]}x{still.size[1]}, "
          f"{os.path.getsize(p_still)/1048576:.2f} MB)")

    # ---- animated: all frames, labelled, then palette-encoded
    tmp = os.path.join(REPO, "out", "_hero_frames")
    os.makedirs(tmp, exist_ok=True)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    PANEL_W = 308          # 3*308 + 2*8 gaps + borders ~= 960
    for i in range(n):
        row(i, panel_w=PANEL_W).save(os.path.join(tmp, f"h{i:04d}.png"))
    print(f"  {n} composite frames written")

    ff = find_ffmpeg()
    pal = os.path.join(tmp, "_pal.png")
    out_gif = os.path.join(MEDIA, "hero_comparison.gif")
    # The filtergraph must name its INPUT: a bare `scale=...` has nothing attached
    # and ffmpeg rejects the graph. [0:v] first, then palettegen / paletteuse.
    # Match the configuration tools/ripple_gifs.py already proved out: a smaller
    # palette with a coarse Bayer dither and rectangle diffing. The bare
    # `dither=bayer` used first diffuses far more, and diffing whole frames each
    # time re-dithers regions that did not change -- both read as crawl.
    for label, args in (
        ("palettegen", [ff, "-y", "-loglevel", "error",
                        "-i", os.path.join(tmp, "h%04d.png"),
                        "-vf", "palettegen=max_colors=128:stats_mode=diff", pal]),
        ("paletteuse", [ff, "-y", "-loglevel", "error",
                        "-i", os.path.join(tmp, "h%04d.png"), "-i", pal,
                        "-lavfi", "[0:v][1:v]paletteuse=dither=bayer:bayer_scale=3:"
                                  "diff_mode=rectangle",
                        "-loop", "0", out_gif]),
    ):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ffmpeg {label} FAILED:\n{r.stderr[-600:]}")
            return 1
    print(f"  {out_gif}  ({os.path.getsize(out_gif)/1048576:.2f} MB)")

    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
