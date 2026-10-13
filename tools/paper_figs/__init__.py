"""Shared design system for the paper's figures.

Import the house style, palette and primitives from here:

    from paper_figs import style, palette
    style.apply()
    fig, ax = style.new_fig(style.COL_MM, 55)
    ax.plot(x, y, color=palette.method_colour("ours"))

`figure_lint.py` checks that what you produced meets the spec.
"""

from . import palette, style        # noqa: F401

__all__ = ["palette", "style"]
