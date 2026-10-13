"""colour_study.py -- colour of the caustic and of the fringes, under coloured media
and a coloured sun.

The estimator is three-channel (650 / 550 / 450 nm) and everything above it is
monochromatic in the sense that it never asks what colour the light IS. This study
asks three questions the paper has not:

  A. what colour is the CAUSTIC once the glass and the water absorb, and once the
     source has a spectrum rather than a fixed white;
  B. what colour are the FRINGES, given that the band width scales as lambda^(2/3)
     so the three channels put their fringes at three different places;
  C. how much of either is the sun's colour rather than the medium's.

The geometry is not re-derived here. Caustic path lengths come from
tools/verify_ray_map.py's trace with return_paths=True, so the ray map is the same
one the paper's ground-truth check uses; the fringes come from
tools/verify_wave_correction.py's fold_intensity, which is the independent cubic-
phase diffraction integral, so the per-wavelength fringe positions are physics
rather than a fitted profile.

Absorption is Beer-Lambert with per-channel coefficients in reciprocal metres. The
media below are stated explicitly as the experiment's parameterisation -- they are
not claimed to be specific commercial dyes -- and the optical depth each produces
over the scene's own path lengths is printed so the reader can see what was asked.
"""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_ray_map as V            # noqa: E402  (needs the path insert above)
from verify_wave_correction import fold_intensity, airy_scale   # noqa: E402

LAMBDAS = np.array([650.0, 550.0, 450.0])      # the solver's R, G, B channels, nm

# ---------------------------------------------------------------------------
# A. media and illuminants
# ---------------------------------------------------------------------------

# Beer-Lambert absorption per metre at 650 / 550 / 450 nm.
# Glass sees ~7 mm of path (two wall crossings), water ~90 mm to the table, so the
# two are given coefficients two orders of magnitude apart to be comparably visible.
GLASS = {
    "clear":  (0.10, 0.08, 0.07),      # the renderer's current, near-neutral
    "cobalt": (300.0, 30.0, 8.0),      # blue glass: absorbs red hard
    "amber":  (12.0, 60.0, 300.0),     # absorbs blue hard
    "green":  (160.0, 12.0, 190.0),    # absorbs red and blue
}

WATER = {
    "clear":    (0.02, 0.02, 0.02),
    "faint":    (0.35, 0.06, 0.025),   # the renderer's current water
    "copper":   (28.0, 3.0, 0.6),      # dissolved copper salt: strongly red-absorbing
    "tea":      (1.2, 5.0, 22.0),      # strongly blue-absorbing
    "ink":      (16.0, 16.0, 30.0),    # near-neutral but dense: a brightness control
}


def planck(lam_nm, T):
    """Planck spectral radiance, arbitrary scale (shape only)."""
    h, c, kB = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    lam = np.asarray(lam_nm, float) * 1e-9
    return (2 * h * c ** 2 / lam ** 5) / (np.expm1(h * c / (lam * kB * T)))


ILLUMINANTS = {
    "flat":     None,                            # equal energy
    "solar":    5778.0,                          # the sun's photosphere
    "warm":     3400.0,
    "cool":    10000.0,
}


def illuminant_weights(name):
    """Relative per-channel weights after the source spectrum."""
    T = ILLUMINANTS[name]
    if T is None:
        return np.ones(3)
    w = planck(LAMBDAS, T)
    return w / w[1]                              # normalise on green


# ---------------------------------------------------------------------------
# B. the caustic
# ---------------------------------------------------------------------------

def caustic_channels(n_side=900):
    """Trace once per wavelength; return per-channel hit maps and path lengths.

    Geometry does not depend on the medium, so this is done once and every medium /
    illuminant combination below is a cheap post-process on the same rays.
    """
    out = {}
    for i, lam in enumerate(LAMBDAS):
        X, Y, lg, lw, hit, onwall, esc = V.trace(n_side=n_side, lam_nm=float(lam),
                                                 return_paths=True)
        g = V.to_grid(X, Y)
        # Mean path lengths per pixel, weighted by hits, so a pixel's attenuation
        # uses the rays that actually landed there rather than a global average.
        gl = np.zeros_like(g)
        wl = np.zeros_like(g)
        ix = ((X + V.EXT) / (2 * V.EXT) * V.N).astype(int)
        iy = ((V.EXT - Y) / (2 * V.EXT) * V.N).astype(int)
        ok = (ix >= 0) & (ix < V.N) & (iy >= 0) & (iy < V.N)
        np.add.at(gl, (iy[ok], ix[ok]), lg[ok])
        np.add.at(wl, (iy[ok], ix[ok]), lw[ok])
        with np.errstate(invalid="ignore", divide="ignore"):
            gl = np.where(g > 0, gl / np.maximum(g, 1), 0.0)
            wl = np.where(g > 0, wl / np.maximum(g, 1), 0.0)
        out[lam] = dict(field=g, l_glass=gl, l_water=wl, hits=hit)
    return out


def caustic_rgb(chan, glass="clear", water="clear", ill="flat", top_pct=2.0):
    """RGB of the caustic core for one medium pair and one illuminant.

    The core is the brightest `top_pct` of binned pixels of the achromatic trace;
    its colour is the transmission-weighted, source-weighted sum of the three
    channel fields over exactly those pixels.
    """
    ach = sum(chan[l]["field"] for l in LAMBDAS)
    thr = np.percentile(ach[ach > 0], 100.0 - top_pct)
    core = ach >= thr

    sg, sw = np.array(GLASS[glass]), np.array(WATER[water])
    src = illuminant_weights(ill)
    acc = np.zeros(3)
    for i, lam in enumerate(LAMBDAS):
        f = chan[lam]["field"]
        F = f[core].sum()
        Tc = np.exp(-(sg[i] * chan[lam]["l_glass"][core]
                      + sw[i] * chan[lam]["l_water"][core]))
        acc[i] = src[i] * (F * Tc).sum() if F > 0 else 0.0
    return acc, core


def chroma(rgb):
    """Simple saturation proxy: (max-min)/max, 0 for neutral."""
    rgb = np.asarray(rgb, float)
    m = rgb.max()
    return 0.0 if m <= 0 else float((m - rgb.min()) / m)


def hue_name(rgb):
    r, g, b = (np.asarray(rgb, float) / max(np.asarray(rgb).max(), 1e-12))
    if chroma(rgb) < 0.05:
        return "neutral"
    if r > g and r > b:
        return "red" if b < 0.7 * r else "magenta"
    if g >= r and g >= b:
        return "green" if abs(r - b) < 0.25 * g else ("yellow" if r > b else "cyan")
    return "blue" if r < 0.7 * b else "cyan"


# ---------------------------------------------------------------------------
# C. the fringes
# ---------------------------------------------------------------------------

_PATTERN_CACHE = {}


def _patterns(c, npts):
    """The three channel patterns, cached.

    The diffraction patterns do not depend on the medium or the source: those only
    reweight them. Recomputing three 120001-point oscillatory integrals for every
    (medium, illuminant) pair made the study needlessly slow -- 60 integrals where
    3 will do.
    """
    key = (c, npts)
    if key not in _PATTERN_CACHE:
        d_r = airy_scale(650e-9, c)
        x = np.linspace(-3.2 * d_r, 1.6 * d_r, npts)
        _PATTERN_CACHE[key] = (x, np.array([fold_intensity(x, lam * 1e-9, c)
                                            for lam in LAMBDAS]))
    return _PATTERN_CACHE[key]


def fringe_colours(glass="clear", water="clear", ill="flat", c=1e-3,
                   path_glass=0.007, path_water=0.090, npts=641):
    """Colour across the fold band, from the real per-wavelength diffraction.

    The band width goes as lambda^(2/3), so at a common position x each channel is
    at a different point of its own pattern: X_c = x / d_c. Summing the three
    weighted patterns gives the colour the band actually shows, and how that colour
    varies across the band is the chromatic fringe sequence.

    Two things matter for this to be physics rather than aliasing, both taken from
    the verified usage in tools/verify_wave_correction.py:

      * `c` is the cubic coefficient of the phase, not a scale. The default here is
        the 1e-3 that the verification uses; changing it moves d and changes how
        fast the phase turns over across the pupil.
      * the window must stay within a FEW Airy scales of the fold. The phase turns
        over k*x + k*c*rho^3/6 cycles across the pupil, so a wide window needs
        enormous quadrature and aliases silently otherwise. A first attempt used a
        window 12 Airy scales wide and the per-channel peaks landed at X = -0.91,
        -1.23 and -1.13 instead of the -1.0188 that Ai^2 demands -- which reads as
        a colour effect and is numerical noise.
    """
    x, pats = _patterns(c, npts)
    sg, sw = np.array(GLASS[glass]), np.array(WATER[water])
    src = illuminant_weights(ill)
    Tc = np.exp(-(sg * path_glass + sw * path_water))
    rgb = pats * (src * Tc)[:, None]
    total = rgb.sum(axis=0)
    return x, rgb, total, total.max(), airy_scale(550e-9, c)


def fringe_summary(*args, **kw):
    """Chromatic behaviour of the band, as chromaticity coordinates.

    Two measures were tried and both fail. Normalising each position by its own
    maximum forces the strongest channel to 1.000 everywhere and reports the same
    spread whatever the media do. Pairwise ratios (B/R) explode wherever the
    denominator channel has an Airy zero: the red channel does exactly that inside
    the lit band, so B/R reached 7.7e4 and the "range" measured a division by
    almost-zero rather than a colour.

    Chromaticity coordinates r = R/(R+G+B) are bounded in [0,1] with no division by
    a single channel, and they are the standard way to state a colour, so that is
    what is reported.
    """
    x, rgb, total, peak, d_g = fringe_colours(*args, **kw)
    s = np.maximum(rgb.sum(axis=0), 1e-30)
    chrom = rgb / s                                   # (3, N) chromaticity
    lit = total > 0.05 * peak                         # the lit side, with signal
    core = int(np.argmax(total))
    out = {
        "x": x, "rgb": rgb, "total": total, "peak": peak, "d_g": d_g,
        "chrom": chrom,
        "core_chroma": chrom[:, core].copy(),
        "core_bg_ratio": float(rgb[2, core] / max(rgb[0, core], 1e-12)),
        "core_gr_ratio": float(rgb[1, core] / max(rgb[0, core], 1e-12)),
    }
    if lit.sum() > 4:
        c = chrom[:, lit]
        out["r_range"] = (float(c[0].min()), float(c[0].max()))
        out["b_range"] = (float(c[2].min()), float(c[2].max()))
        # hue drift = the largest change in any coordinate across the lit band
        out["drift"] = float(max(c[0].max() - c[0].min(), c[2].max() - c[2].min()))
        out["n_lit"] = int(lit.sum())
    else:
        out["r_range"] = out["b_range"] = (0.0, 0.0)
        out["drift"] = 0.0
        out["n_lit"] = 0
    peaks = []
    for i in range(3):
        d = airy_scale(LAMBDAS[i] * 1e-9, kw.get("c", 1e-3))
        peaks.append(float(x[np.argmax(rgb[i])] / d))
    out["channel_peaks_X"] = peaks
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _pack(fs, nd=5):
    """Round before serialising.

    Full float repr of fifteen 641-point RGB triples made a 2.0 MB sidecar for a
    figure that reads it at 174 mm wide. Five decimals is far below what the plot
    can resolve and takes the file to a fraction of that.
    """
    return {
        "x_um": np.round(fs["x"] * 1e6, 3).tolist(),
        "rgb": np.round(fs["rgb"], nd).tolist(),
        "total": np.round(fs["total"], nd).tolist(),
        "chroma": np.round(fs["chrom"], nd).tolist(),
        "core_b": round(float(fs["core_chroma"][2]), nd),
        "drift": round(float(fs["drift"]), nd),
    }


def main():
    print("Colour of the caustic and of its fringes")
    print("=" * 74)
    print(f"channels: {LAMBDAS[0]:.0f} / {LAMBDAS[1]:.0f} / {LAMBDAS[2]:.0f} nm "
          f"(R / G / B)")

    # ---- A. what the media do over the scene's own path lengths -------------
    print("\nA. Absorption over the scene's own path lengths")
    print("   (glass ~7 mm of wall, water ~90 mm to the table)")
    for name in GLASS:
        t = np.exp(-np.array(GLASS[name]) * 0.007)
        print(f"   glass {name:7s} over 7 mm : "
              f"{t[0]:.4f} {t[1]:.4f} {t[2]:.4f}")
    for name in WATER:
        t = np.exp(-np.array(WATER[name]) * 0.090)
        print(f"   water {name:7s} over 90 mm: "
              f"{t[0]:.4f} {t[1]:.4f} {t[2]:.4f}")

    # ---- B. the source spectra ---------------------------------------------
    print("\nB. Source spectra, per-channel weight (green = 1)")
    for name in ILLUMINANTS:
        w = illuminant_weights(name)
        T = ILLUMINANTS[name]
        label = "equal energy" if T is None else f"{T:.0f} K"
        print(f"   {name:6s} {label:12s} {w[0]:.4f} {w[1]:.4f} {w[2]:.4f}")

    # ---- C. colour of the fringes -------------------------------------------
    print("\nC. Colour of the FRINGES (real per-wavelength diffraction)")
    print("   the three channels put their fringes at different places because the")
    print("   band width goes as lambda^(2/3):")
    print(f"     {'channel':>8}  {'Airy scale':>11}  {'ratio to green':>14}")
    for lam in LAMBDAS:
        d = airy_scale(lam * 1e-9, 1e-3)
        print(f"     {lam:6.0f}nm  {d*1e6:9.3f} um  "
              f"{d/airy_scale(550e-9,1e-3):14.4f}   (analytic {(lam/550)**(2/3):.4f})")

    print("\n   and here is what that does to the colour down the band.")
    print("   coordinates are chromaticity r = R/(R+G+B); drift is the largest")
    print("   change in any coordinate across the lit band:")
    print(f"     {'illuminant':>11} {'medium':>16} {'b core':>7} {'b range':>16} "
          f"{'drift':>7}")
    for ill in ("flat", "solar", "warm", "cool"):
        for water in ("clear", "copper", "tea"):
            fs = fringe_summary(water=water, ill=ill)
            lo, hi = fs["b_range"]
            print(f"     {ill:>11} {water:>16} {fs['core_chroma'][2]:7.3f} "
                  f"{lo:7.3f} - {hi:5.3f} {fs['drift']:7.3f}")

    print("\n   same, varying the GLASS (the light crosses the shell twice):")
    print(f"     {'illuminant':>11} {'glass':>9} {'b core':>7} {'b range':>16} "
          f"{'drift':>7}")
    for ill in ("flat", "solar", "warm"):
        for glass in ("clear", "cobalt", "amber", "green"):
            fs = fringe_summary(glass=glass, ill=ill)
            lo, hi = fs["b_range"]
            print(f"     {ill:>11} {glass:>9} {fs['core_chroma'][2]:7.3f} "
                  f"{lo:7.3f} - {hi:5.3f} {fs['drift']:7.3f}")

    print("\n   the two effects are separable: the MEDIUM multiplies the channels,")
    print("   the SOURCE multiplies them, and the FRINGE colour comes from the")
    print("   lambda^(2/3) displacement, which neither of them can change.")

    # Collect everything for tools/make_colour_figure.py, so the figure reads the
    # same numbers this report printed instead of recomputing them.
    res = {"lambdas": LAMBDAS.tolist(),
           "airy_scales_um": [airy_scale(l * 1e-9, 1e-3) * 1e6 for l in LAMBDAS],
           "sources": {k: illuminant_weights(k).tolist() for k in ILLUMINANTS},
           "media": {"glass": GLASS, "water": WATER},
           "fringes": {}, "caustic": {}}

    for water in ("clear", "copper", "tea"):
        for ill in ("flat", "solar", "warm", "cool"):
            fs = fringe_summary(water=water, ill=ill)
            key = f"{water}|{ill}"
            res["fringes"][key] = _pack(fs)
    for glass in ("clear", "cobalt", "amber", "green"):
        key = f"{glass}|flat"
        res["fringes"][key] = _pack(fringe_summary(glass=glass, ill="flat"))

    # ---- D. colour of the caustic itself ------------------------------------
    n_side = int(os.environ.get("COLOUR_NSIDE", "900"))
    print(f"\nD. Colour of the CAUSTIC (traced ray map, {n_side}x{n_side} per channel)")
    print("   the caustic core is the brightest 2% of the achromatic trace; its")
    print("   colour is the source- and transmission-weighted sum over those pixels")
    chan = caustic_channels(n_side=n_side)
    tot = sum(chan[l]["hits"] for l in LAMBDAS)
    print(f"   rays landing on the patch, all channels: {tot}")
    res["caustic_n_side"] = n_side
    res["caustic_hits"] = tot

    print(f"\n     {'illuminant':>11} {'glass':>8} {'water':>8} "
          f"{'R':>8} {'G':>8} {'B':>8}   {'colour':>8}")
    for ill in ("flat", "solar", "warm", "cool"):
        for glass, water in (("clear", "clear"), ("cobalt", "clear"),
                             ("clear", "copper"), ("clear", "tea"),
                             ("amber", "clear")):
            rgb, _core = caustic_rgb(chan, glass=glass, water=water, ill=ill)
            n = rgb / max(rgb.max(), 1e-12)
            res["caustic"][f"{glass}|{water}|{ill}"] = {
                "rgb": rgb.tolist(), "norm": n.tolist(), "hue": hue_name(rgb)}
            print(f"     {ill:>11} {glass:>8} {water:>8} "
                  f"{n[0]:8.4f} {n[1]:8.4f} {n[2]:8.4f}   {hue_name(rgb):>8}")

    print("\n   how much of the caustic's colour is the SUN rather than the medium:")
    for glass, water in (("clear", "clear"), ("clear", "copper")):
        base = caustic_rgb(chan, glass=glass, water=water, ill="solar")[0]
        for ill in ("warm", "cool"):
            rgb = caustic_rgb(chan, glass=glass, water=water, ill=ill)[0]
            a = base / max(base.max(), 1e-12)
            b = rgb / max(rgb.max(), 1e-12)
            print(f"     {glass}/{water} solar -> {ill}: "
                  f"RGB shift {np.abs(a-b).max():.4f}")

    # _HERE is the tools/ directory, so its parent is the repo root.
    out = os.path.join(os.path.dirname(_HERE), "docs", "data", "colour_results.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    import json
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
