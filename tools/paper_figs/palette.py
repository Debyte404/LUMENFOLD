"""One palette for the whole paper. Import it; never type a hex again.

Why this file exists
--------------------
The figures previously each chose their own colours inline. The same quantity --
"the caustic from our method", "the 450 nm channel", "copper water" -- was drawn in
a different hue depending on which script produced the panel, and two panels that
showed the same comparison disagreed about which series was red. A reader cannot
tell which differences are physics and which are decoration.

So: a meaning gets exactly one colour, and that colour is defined here once.

Two rules that constrain the choices
------------------------------------
1. These figures must survive greyscale printing. Red, green and blue cannot all be
   far apart in luminance while still reading as red, green and blue, so every
   semantic series also carries a LINE STYLE or a HATCH. Colour is a convenience;
   the pattern is the guarantee. `figure_lint.py` checks for it.
2. Colour is never the only carrier of identity. If two things differ, they differ
   in shape as well.
"""

# --- neutrals ---------------------------------------------------------------------
INK = "#1a1a1a"          # text and axes; not pure black, which looks harsh at 8pt
INK_SOFT = "#4d4d4d"     # secondary text, annotations
GRID = "#d9d9d9"         # gridlines: visible in print, never competing with data
PANEL = "#f2f2f2"        # empty-panel fill
RULE = "#8c8c8c"         # dimension lines, scale bars, leader lines
WHITE = "#ffffff"

# --- the three channels -----------------------------------------------------------
# Saturated so they read as R/G/B, paired with distinct dash patterns so they
# separate in greyscale. Luminance also differs, but only as a third line of defence.
CHANNEL = {
    450: "#1565C0",      # blue
    550: "#2E7D32",      # green
    650: "#C62828",      # red
}
CHANNEL_DASH = {450: (0, (1, 1)), 550: (0, (5, 2)), 650: "solid"}
CHANNEL_ORDER = [650, 550, 450]          # long to short, as dispersion writes them

# --- methods compared in the evaluation -------------------------------------------
# Okabe-Ito derived: distinguishable under every common colour-vision deficiency.
METHOD = {
    "ours": "#0072B2",       # the method under test: strong blue, used consistently
    "sppm": "#D55E00",       # stochastic progressive photon mapping
    "pbrt": "#009E73",       # the PBRT reference
    "cycles": "#CC79A7",     # Blender Cycles
    "reference": "#000000",  # ground truth, always black
}
METHOD_DASH = {
    "ours": "solid", "sppm": (0, (4, 1.5)), "pbrt": (0, (1, 1.2)),
    "cycles": (0, (6, 2, 1, 2)), "reference": (0, (2, 1.5)),
}
METHOD_HATCH = {"ours": "", "sppm": "///", "pbrt": "\\\\\\", "cycles": "xxx",
                "reference": "..."}

# --- scene state ------------------------------------------------------------------
MEDIUM = {
    "clear": "#bdbdbd",      # neutral, because "clear" is the absence of tint
    "water": "#1E88A8",      # water tint
    "glass": "#8E7CC3",      # glass tint
    "copper": "#B3541E",     # copper-loaded water
    "tea": "#8B6B2E",
    "cobalt": "#2A4B9B",
    "amber": "#C98A2B",
}

# --- source colour temperature ----------------------------------------------------
SOURCE = {
    "equal": "#8c8c8c",
    "solar": "#E8A33D",
    "warm": "#D9534F",
    "cool": "#5B8FD9",
}

# --- sequential ramps -------------------------------------------------------------
# For fields and rasters. Perceptually uniform; the previous "inferno" reads as
# scientific but its dark end hides structure in print.
RAMP_FIELD = "magma"
RAMP_SIGNED = "RdBu_r"


def channel_colour(nm):
    return CHANNEL[nm]


def channel_dash(nm):
    return CHANNEL_DASH[nm]


def method_colour(name):
    return METHOD.get(name, INK)


def method_dash(name):
    return METHOD_DASH.get(name, "solid")
