"""gif_flicker_audit.py -- find where the flicker actually is.

The earlier flicker numbers (0.05% / 0.04% / 0.41%) were measured on the SOURCE
frames in out/gif_src, not on the encoded GIFs. Between those two things sits a
palette quantisation and a dither, either of which can introduce temporal noise on
its own. This measures the shipped artefacts.

Three distinct things get called "flicker":

  1. exposure ripple   -- whole-frame mean brightness moving frame to frame
  2. dither crawl      -- per-pixel temporal variance in flat regions, the classic
                          ordered-dither artefact: a static pattern that changes
                          every frame because the palette index moves
  3. content flicker   -- the renderer's own noise (Cycles/SPPM sampling)

They need separating, because the fixes are different.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

REPO = r"D:/ValueProjects/caustics"
MEDIA = os.path.join(REPO, "docs", "media")


def load_gif(path, limit=None):
    im = Image.open(path)
    frames = []
    for i in range(getattr(im, "n_frames", 1)):
        if limit and i >= limit:
            break
        im.seek(i)
        frames.append(np.asarray(im.convert("RGB"), dtype=np.float32))
    return np.stack(frames)


def audit(path):
    name = os.path.basename(path)
    fr = load_gif(path)
    n, h, w, _ = fr.shape
    print(f"\n{name}  ({n} frames, {w}x{h})")

    # ---- 1. exposure ripple: whole-frame mean per frame
    means = fr.reshape(n, -1).mean(axis=1)
    spread = (means.max() - means.min()) / means.mean() * 100
    print(f"  1. exposure ripple : mean {means.mean():7.3f}  "
          f"range {means.min():7.3f}..{means.max():7.3f}  spread {spread:6.3f}%")
    if spread > 1.0:
        print(f"     -> frame-to-frame brightness moves by more than 1%: VISIBLE")

    # ---- 2. dither crawl: temporal variance of the pixel, vs its own level.
    # In a flat region a correct encode has near-zero temporal variance; an ordered
    # dither crawls because the index pattern shifts between palette generations.
    lum = fr.mean(axis=3) if fr.shape[3] == 3 else fr[..., 0]
    lum = fr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    tv = lum.std(axis=0)                       # per-pixel temporal std
    # consider only flat-ish areas: low spatial gradient in the temporal mean
    mean_img = lum.mean(axis=0)
    gy, gx = np.gradient(mean_img)
    grad = np.hypot(gx, gy)
    flat = grad < np.percentile(grad, 40)
    print(f"  2. dither crawl    : temporal std over flat areas "
          f"mean {tv[flat].mean():6.3f}  p99 {np.percentile(tv[flat], 99):6.3f}")
    print(f"     spatial contrast : temporal std / mean level = "
          f"{(tv[flat] / max(mean_img[flat].mean(), 1e-6)).mean() * 100:.3f}%")

    # ---- 3. content: how much of the frame changes at all
    d = np.abs(np.diff(lum, axis=0))
    print(f"  3. frame-to-frame  : mean |diff| {d.mean():6.3f}  "
          f"p99 {np.percentile(d, 99):7.3f}  (high = real content change)")

    # palette behaviour. Compare only the colours actually in use: PIL's
    # getpalette() returns a 256-entry table and the UNUSED trailing entries differ
    # between frames, which made a naive whole-table comparison report "palette
    # changes" on correctly encoded GIFs and send this audit chasing a phantom.
    im = Image.open(path)
    im.seek(0)
    npal = 128 if "128" in str(im.info.get("palette_size", "")) else 256
    pals = []
    for i in range(min(n, 8)):
        im.seek(i)
        p = im.getpalette()
        if p:
            pals.append(np.asarray(p, dtype=int)[:3 * 128])
    shared = len({tuple(p) for p in pals}) == 1 if pals else False
    print(f"     palette          : {'single shared palette' if shared else 'PER-FRAME PALETTES'}")
    return dict(name=name, spread=spread, tv_flat=tv[flat].mean(),
                contrast=(tv[flat] / max(mean_img[flat].mean(), 1e-6)).mean() * 100,
                pal_shared=shared)


def main():
    rows = []
    for p in sorted(glob.glob(os.path.join(MEDIA, "*.gif"))):
        rows.append(audit(p))
    print("\n" + "=" * 72)
    print(f"{'gif':<26}{'exposure':>12}{'crawl':>10}{'contrast':>11}  palette")
    for r in rows:
        print(f"{r['name']:<26}{r['spread']:>11.3f}%{r['tv_flat']:>10.3f}"
              f"{r['contrast']:>10.3f}%  {'global' if r['pal_shared'] else 'PER-FRAME'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
