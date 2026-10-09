"""make_comparison_figure.py — one image that shows the comparison.

Layout:
  row 1   reference photograph | our injected caustic | Cycles' own caustics
  row 2   matching crops of the caustic, zoomed, so the noise difference is
          visible rather than merely tabulated

All three row-1 panels are scaled to the same width. The crop region is chosen
from the caustic's brightest area in our render so both methods are shown at
their best-known location.

Run:  python tools/make_comparison_figure.py
"""
from PIL import Image, ImageDraw

OUT = "D:/ValueProjects/caustics/out"
DOCS = "D:/ValueProjects/caustics/docs"
REF = "D:/hermes/hermes-agent/images/clip_20261007_180753_5.png"
W = 720                      # panel width
LABEL = 26


def fit(img, w):
    return img.resize((w, max(1, int(img.height * w / img.width))), Image.LANCZOS)


def label(img, text):
    canvas = Image.new("RGB", (img.width, img.height + LABEL), (16, 16, 18))
    canvas.paste(img, (0, LABEL))
    d = ImageDraw.Draw(canvas)
    d.text((6, 7), text, fill=(235, 235, 235))
    return canvas


def find_caustic_crop(path, size=340):
    """Brightest region of the render, as a crop box."""
    import numpy as np
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32).mean(axis=2)
    # ignore the top strip (the glass's specular highlight) to land on the table
    a[: int(a.shape[0] * 0.25)] = 0
    # box-blur by downsampling so a single firefly cannot win
    k = 24
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    t = a[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    r, c = np.unravel_index(np.argmax(t), t.shape)
    cy, cx = (r + 0.5) * k, (c + 0.5) * k
    half = size // 2
    x0 = int(min(max(cx - half, 0), im.width - size))
    y0 = int(min(max(cy - half, 0), im.height - size))
    return im.crop((x0, y0, x0 + size, y0 + size))


def main():
    ref = fit(Image.open(REF).convert("RGB"), W)
    ours = fit(Image.open(f"{OUT}/hero_ours.png").convert("RGB"), W)
    cyc = fit(Image.open(f"{OUT}/hero_cycles.png").convert("RGB"), W)

    panels = [label(ref, "REFERENCE PHOTOGRAPH"),
              label(ours, "OURS: baked wave-corrected caustic injected"),
              label(cyc, "COMPETITOR: Cycles path-traced caustics")]
    h1 = max(p.height for p in panels)
    row1 = Image.new("RGB", (sum(p.width for p in panels) + 16, h1), (16, 16, 18))
    x = 0
    for p in panels:
        row1.paste(p, (x, 0))
        x += p.width + 8

    crop_size = 340
    co = find_caustic_crop(f"{OUT}/hero_ours.png", crop_size)
    cc = find_caustic_crop(f"{OUT}/hero_cycles.png", crop_size)
    z = 2
    co = co.resize((crop_size * z, crop_size * z), Image.NEAREST)
    cc = cc.resize((crop_size * z, crop_size * z), Image.NEAREST)
    row2 = Image.new("RGB", (co.width + cc.width + 8, co.height + LABEL), (16, 16, 18))
    a = label(co, "OURS: caustic crop, no denoise")
    b = label(cc, "COMPETITOR: same crop, equal samples")
    row2.paste(a, (0, 0))
    row2.paste(b, (co.width + 8, 0))

    total_w = max(row1.width, row2.width)
    total_h = row1.height + row2.height + 8
    fig = Image.new("RGB", (total_w, total_h), (16, 16, 18))
    fig.paste(row1, (0, 0))
    fig.paste(row2, (0, row1.height + 8))
    path = f"{DOCS}/comparison_ours_vs_cycles.png"
    fig.save(path)
    print(f"wrote {path}  {fig.width}x{fig.height}")


if __name__ == "__main__":
    main()
