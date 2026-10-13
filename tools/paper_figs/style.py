"""One style for the whole paper. Import it; never set rcParams locally again.

Why this file exists
--------------------
Four producer scripts each carried their own rcParams copy. They had drifted: body
text 8pt in two and 7.5pt in two, rasters at 300, 400 and 600 dpi, one with
transparency flattening and three without. So fixing a defect meant fixing it two to
four times, and the figures did not look like one paper.

Typography
----------
Times New Roman, which is metrically identical to the Nimbus Roman the EG class
typesets with, so a figure label and a caption line up. If the font is missing
matplotlib substitutes DejaVu Serif silently and the figures stop matching the text --
`missing_fonts()` exists so the linter can fail instead of letting that pass.
"""
import re

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

MM = 1.0 / 25.4

# --- EG two-column geometry -------------------------------------------------------
# MEASURED from the compiled paper, not assumed from the class. The text block runs
# x = 48.6 .. 551.2 pt, i.e. 177.1 mm, and the most common block width (209 blocks) is
# 84.4 mm. Authoring at 174 mm against a 177.1 mm text block left every full-width
# figure scaled up by 1.8%, which is exactly the drift this module exists to remove.
COL_MM = 84.4        # single column
FULL_MM = 177.1      # full text width
MAX_H_MM = 232.0     # text height, so a figure can never overflow a page

FONT_SERIF = ["Times New Roman", "Nimbus Roman No9 L", "DejaVu Serif"]

# --- typography -------------------------------------------------------------------
# One hierarchy: titles, axis labels, ticks, legend, annotation, micro.
SZ_TITLE = 8.0
SZ_LABEL = 8.0
SZ_TICK = 7.0
SZ_LEGEND = 7.0
SZ_ANNOT = 6.5
SZ_MICRO = 6.0
SZ_MIN = 6.0          # nothing smaller survives print; the linter enforces this

# --- strokes ----------------------------------------------------------------------
LW_AXIS = 0.6
LW_DATA = 1.0
LW_THIN = 0.4
LW_GRID = 0.35
MS_DATA = 3.0         # marker size

RASTER_DPI = 600      # authored resolution for embedded rasters
PAD_IN = 0.06         # tight-bbox padding; below ~0.03 clips rotated labels


def apply():
    """Install the house style. Call once, before building any figure."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": FONT_SERIF,
        "mathtext.fontset": "stix",       # matches Times, unlike "dejavusans"
        "font.size": SZ_LABEL,
        "axes.titlesize": SZ_TITLE,
        "axes.labelsize": SZ_LABEL,
        "xtick.labelsize": SZ_TICK,
        "ytick.labelsize": SZ_TICK,
        "legend.fontsize": SZ_LEGEND,
        "axes.linewidth": LW_AXIS,
        "xtick.major.width": LW_AXIS,
        "ytick.major.width": LW_AXIS,
        "xtick.minor.width": LW_THIN,
        "ytick.minor.width": LW_THIN,
        "xtick.major.size": 2.4,
        "ytick.major.size": 2.4,
        "xtick.minor.size": 1.4,
        "ytick.minor.size": 1.4,
        "lines.linewidth": LW_DATA,
        "lines.markersize": MS_DATA,
        "grid.linewidth": LW_GRID,
        "grid.color": "#d9d9d9",
        "grid.alpha": 1.0,                # alpha would need an ExtGState
        "axes.grid": False,               # opt in per axis, never globally on
        "axes.spines.top": False,         # chartjunk by default
        "axes.spines.right": False,
        "figure.dpi": 200,
        "savefig.dpi": RASTER_DPI,
        # NOT "tight". A tight bounding box CROPS to the drawn content, so a figure
        # asked for at 84 mm (the column width) came out at 78 mm and LaTeX then
        # scaled it back up. That rescale is what made the type sizes and the raster
        # dpi differ from figure to figure: the numbers in the source were not the
        # numbers on the page. Figures are now authored at their true size and the
        # margins are set explicitly, so include them at natural size.
        "savefig.bbox": None,
        "savefig.pad_inches": 0.0,
        "savefig.transparent": False,
        "pdf.fonttype": 42,               # embed TrueType, keep text extractable
        "ps.fonttype": 42,
        "axes.unicode_minus": False,
    })


def missing_fonts():
    """Families in FONT_SERIF that are not installed, best first.

    If this is non-empty matplotlib silently substitutes and the figures stop
    matching the paper's text face. The linter treats it as a failure.
    """
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in FONT_SERIF if f not in have]


def new_fig(width_mm, height_mm=None, rows=1, cols=1, **kw):
    """A figure sized in millimetres, which is the only unit the paper uses."""
    w = width_mm * MM
    h = (height_mm if height_mm is not None else width_mm * 0.62) * MM
    if rows == 1 and cols == 1:
        fig, ax = plt.subplots(figsize=(w, h), **kw)
        return fig, ax
    fig, axes = plt.subplots(rows, cols, figsize=(w, h), **kw)
    return fig, axes


def polish(ax, grid="y", spines=("left", "bottom")):
    """The house axis treatment: hairline ticks, light grid behind, no top/right."""
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(s in spines)
        if s in spines:
            ax.spines[s].set_linewidth(LW_AXIS)
    if grid:
        ax.set_axisbelow(True)
        ax.grid(True, axis=grid, color="#d9d9d9", lw=LW_GRID)
    ax.tick_params(which="both", direction="out")
    return ax


def panel_label(ax, text, dx=-0.14, dy=1.04):
    """(a), (b) ... in the same place on every panel, outside the axes."""
    return ax.text(dx, dy, text, transform=ax.transAxes, ha="left", va="bottom",
                   fontsize=SZ_TITLE, fontweight="bold", color="#1a1a1a")


# --- schematic primitives ---------------------------------------------------------
def dimension(ax, p0, p1, label, offset=0.0, fontsize=None, color="#8c8c8c",
              text_offset=0.0, ha="center", va="bottom"):
    """A dimension line with arrowheads at both ends and a label above it.

    Drawn previously as hand-placed text and ticks, which is why the numbers drifted
    from the geometry. This derives everything from the two endpoints.
    """
    import numpy as np
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    d = p1 - p0
    n = np.array([-d[1], d[0]], float)
    n = n / (np.linalg.norm(n) or 1.0)
    a, b = p0 + n * offset, p1 + n * offset
    ax.annotate("", xy=b, xytext=a,
                arrowprops=dict(arrowstyle="<->", lw=LW_THIN, color=color,
                                shrinkA=0, shrinkB=0))
    mid = (a + b) / 2 + n * text_offset
    ax.text(mid[0], mid[1], label, ha=ha, va=va, fontsize=fontsize or SZ_MICRO,
            color=color)


def leader(ax, xy, xytext, text, fontsize=None, color="#8c8c8c", ha="left"):
    """An annotation with a thin leader line, for labels that must clear the art."""
    ax.annotate(text, xy=xy, xytext=xytext, fontsize=fontsize or SZ_MICRO,
                color=color, ha=ha, va="center",
                arrowprops=dict(arrowstyle="-", lw=LW_THIN, color=color,
                                shrinkA=0, shrinkB=1.5))


def scale_bar(ax, x0, y0, length, label, height=None, color="#1a1a1a"):
    """A true-length scale bar. Every scene drawing needs one."""
    h = height if height is not None else length * 0.012
    ax.add_patch(plt.Rectangle((x0, y0), length, h, facecolor=color,
                               edgecolor="none", zorder=6))
    ax.text(x0 + length / 2, y0 + h * 1.6, label, ha="center", va="bottom",
            fontsize=SZ_MICRO, color=color, zorder=6)


# --- save: always the same guarantees ---------------------------------------------
_ALPHA_RE = re.compile(rb"/CA (\d*\.?\d+)")
_ALPHA_RE2 = re.compile(rb"/ca (\d*\.?\d+)")


def flatten_alpha(path):
    """Rewrite non-opaque ExtGState alphas to 1, preserving BYTE LENGTH.

    The venue forbids transparent figure content, and matplotlib emits constant-alpha
    ExtGState entries even for an ordinary plot. The xref table stores absolute byte
    offsets, so a shorter substitution corrupts every later offset and viewers that
    honour the xref refuse the file. Hence the fixed-width rewrite.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if b"/SMask" in data:
        pass  # a real soft mask is reported by the linter, not silently fixed
    out = data
    for rx in (_ALPHA_RE, _ALPHA_RE2):
        def sub(m):
            old = m.group(1)
            if old in (b"1", b"1.0", b"1.00"):
                return m.group(0)
            new = b"1" + b"0" * (len(old) - 1) if old[0:1] == b"0" else b"1." + b"0" * (len(old) - 2)
            new = new[:len(old)].ljust(len(old), b"0")
            return m.group(0).replace(old, new)
        out = rx.sub(sub, out)
    if len(out) != len(data):
        raise RuntimeError("alpha flatten changed file length (%d -> %d)"
                           % (len(data), len(out)))
    with open(path, "wb") as fh:
        fh.write(out)
    return path


def strip_softmask(path, min_opaque=0.995):
    """Remove a soft mask that carries no transparency, and refuse one that does.

    matplotlib emits a /SMask whenever it writes a raster with an alpha channel. For
    fig11's orbit strip the mask is 99.89% fully opaque -- the rest is edge
    antialiasing -- so it encodes no transparency, and the venue forbids transparent
    figure content regardless.

    Blanking the /SMask reference is done with SPACES of equal length, because the
    xref table stores absolute byte offsets: a shorter substitution corrupts every
    later offset. Whitespace between dictionary entries is legal PDF.

    If a mask is genuinely transparent (more than `min_opaque` non-opaque) this RAISES
    rather than quietly flattening it: that would change what the figure shows, and
    silently altering a figure to satisfy a checker is worse than failing the check.
    """
    import numpy as np
    import pymupdf

    with open(path, "rb") as fh:
        data = fh.read()

    pat = re.compile(rb"/SMask\s+(\d+)\s+(\d+)\s+R")
    matches = list(pat.finditer(data))
    if not matches:
        return path          # stored in an object stream, or none present

    doc = pymupdf.open(path)
    for m in matches:
        xref = int(m.group(1))
        try:
            info = doc.extract_image(xref)
            raw = info["image"]
            import io as _io
            from PIL import Image
            a = np.asarray(Image.open(_io.BytesIO(raw)).convert("L"))
            frac_opaque = float((a == 255).mean())
        except Exception as e:
            raise RuntimeError("cannot inspect /SMask xref %d: %s" % (xref, e))
        if frac_opaque < min_opaque:
            raise RuntimeError(
                "%s: /SMask xref %d is genuinely transparent (%.2f%% opaque) -- "
                "flattening it would change the figure"
                % (path, xref, frac_opaque * 100))
        print("      strip_softmask: xref %d %.2f%% opaque -> dropped"
              % (xref, frac_opaque * 100))

    out = pat.sub(lambda m: b" " * len(m.group(0)), data)
    if len(out) != len(data):
        raise RuntimeError("softmask strip changed file length")
    with open(path, "wb") as fh:
        fh.write(out)
    return path


def save(fig, path, width_mm=None, flatten=True):
    """Save with every guarantee applied, so no producer can forget one.

    If `width_mm` is given the produced page must match it: that is the contract
    LaTeX relies on when it includes the figure at natural size. A mismatch means the
    figure will be rescaled on the page and its type size and raster dpi will no
    longer be what the source says, which is the defect this whole module exists to
    prevent. Fail loudly here instead.
    """
    fig.savefig(path, format="pdf")
    plt.close(fig)
    if flatten and path.endswith(".pdf"):
        strip_softmask(path)
        flatten_alpha(path)

    if width_mm is not None:
        import pymupdf
        got = pymupdf.open(path)[0].rect.width / 72.0 * 25.4
        if abs(got - width_mm) > 0.6:
            raise RuntimeError(
                "%s came out %.1f mm wide, asked for %.1f mm -- it would be rescaled "
                "on the page" % (path, got, width_mm))
    return path


def fit(fig, pad=0.32):
    """Fit all artists inside the fixed canvas.

    Figures are no longer auto-cropped, so a label that would have been included by
    the tight bounding box now runs off the edge instead. This squeezes the axes to
    make room, WITHOUT changing the figure size, so the width contract with LaTeX
    still holds.

    A figure that already has a constrained layout engine must be left alone:
    tight_layout would override it ("The figure layout has changed to tight"), and
    constrained layout is the one that understands a colorbar carved out of a panel,
    which is precisely the case it was chosen for.
    """
    eng = fig.get_layout_engine()
    if eng is not None and eng.__class__.__name__.startswith("Constrained"):
        return fig
    try:
        fig.tight_layout(pad=pad)
    except Exception:
        pass
    return fig


def margins(fig, left=0.11, right=0.975, bottom=0.17, top=0.94, wspace=None, hspace=None):
    """Set explicit margins, since figures are no longer auto-cropped."""
    kw = {}
    if wspace is not None:
        kw["wspace"] = wspace
    if hspace is not None:
        kw["hspace"] = hspace
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top, **kw)
    return fig
