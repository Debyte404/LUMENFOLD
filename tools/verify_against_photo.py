"""verify_against_photo.py — measure a real caustic and compare it with the
simulation's predictions.

This is the only tool in the repo that touches reality. Everything else compares
simulation to simulation.

What it needs, all measurable off the photograph:

  --photo     the image
  --centre    glass centre, in pixels, as "x,y"
  --radius    glass OUTER radius, in pixels (this fixes the mm mapping)
  --light-az  direction to the light in IMAGE coordinates, degrees, measured from
              +x to the right and +y up. 0 = light to the right, 90 = light above.

It then measures the same quantities tools/physical_predictions.py predicts:
the caustic's centroid radius in glass radii, its azimuth relative to the light,
the fan's angular span, and the per-colour radii that establish dispersion order.

Deliberately NOT measured: fringe structure. See docs/PHYSICAL_TEST.md - the
physical fringe width is 123 um but a 0.53 deg source blurs the pattern by
925 um, so the fringes do not exist under sunlight, and what we render is a
visibility choice rather than a prediction.

Run:
  python tools/verify_against_photo.py --photo shot.jpg \
      --centre 410,250 --radius 96 --light-az 235
"""
import argparse

import numpy as np
from PIL import Image

SUN_AZ_PRED = 27.7          # deg, simulation
CENTROID_R_PRED = 1.50      # x glass radius
RB_SEP_PRED = 2.9           # % of radius


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True)
    ap.add_argument("--centre", required=True, help="glass centre, px, 'x,y'")
    ap.add_argument("--radius", type=float, required=True,
                    help="glass OUTER radius in pixels")
    ap.add_argument("--light-az", type=float, required=True,
                    help="direction to the light, deg in image coords, +x right, "
                         "+y up")
    ap.add_argument("--bg-percentile", type=float, default=60.0,
                    help="percentile used as the table's unlit background level")
    ap.add_argument("--thresh-mode", choices=("percentile", "sigma"),
                    default="percentile",
                    help="percentile (default) takes the brightest tail, which is "
                         "robust; sigma compares against the frame's MAD, which "
                         "is only usable on a flat, shadow-free photo")
    ap.add_argument("--caustic-percentile", type=float, default=98.0)
    ap.add_argument("--thresh-sigma", type=float, default=6.0)
    args = ap.parse_args()

    cx, cy = (float(v) for v in args.centre.split(","))
    a = np.asarray(Image.open(args.photo).convert("RGB")).astype(np.float32)
    H, W, _ = a.shape
    lum = a.mean(axis=2)
    print(f"photo {W}x{H}, glass centre ({cx:.0f},{cy:.0f}), "
          f"radius {args.radius:.1f} px  ->  {1/args.radius:.5f} glass-radii/px")

    bg = np.percentile(lum, args.bg_percentile)
    mad = np.median(np.abs(lum - bg)) * 1.4826
    if args.thresh_mode == "percentile":
        # The caustic is the brightest thing in a photograph of a caustic, so
        # take the brightest tail. A sigma threshold against the frame's MAD is
        # useless here: the shadow and the glass make the MAD huge, and the
        # resulting threshold lands above 255 where nothing can qualify. That is
        # exactly what happened on the first real photo this tool was pointed at.
        thr = np.percentile(lum, args.caustic_percentile)
        print(f"table background {bg:.1f} (MAD {mad:.1f}), caustic = brightest "
              f"{100-args.caustic_percentile:.0f}% (> {thr:.1f})")
    else:
        thr = bg + args.thresh_sigma * max(mad, 1e-6)
        print(f"table background {bg:.1f} +- {mad:.1f}, "
              f"caustic threshold {thr:.1f}")
    hot = lum > thr
    print(f"caustic pixels: {int(hot.sum())} ({100*hot.mean():.2f}% of the frame)")
    if hot.sum() < 30:
        print("too few caustic pixels: raise the exposure or lower --thresh-sigma")
        return 1
    clipped = int((lum > 250).sum())
    print(f"clipped pixels (>250): {clipped}"
          + ("   <-- intensity comparison NOT possible, geometry only"
             if clipped > 50 else ""))

    # image coords -> mm relative to the glass, in glass radii, with +y up
    ys, xs = np.where(hot)
    gx = (xs - cx) / args.radius
    gy = (cy - ys) / args.radius
    r = np.hypot(gx, gy)
    az = np.degrees(np.arctan2(gy, gx))

    # angular difference from the light's direction
    def wrap(d):
        return (d + 180.0) % 360.0 - 180.0
    rel = wrap(az - args.light_az)

    print()
    print("=== measured ===")
    print(f"  caustic centroid radius  {r.mean():6.2f} x glass radius "
          f"(predicted {CENTROID_R_PRED:.2f})")
    print(f"  azimuth relative to the light {rel.mean():+7.1f} deg "
          f"(predicted +0.3 deg)")
    print(f"  angular span {rel.min():+.0f} to {rel.max():+.0f} deg "
          f"(predicted -40 to +95)")
    print(f"  radial span  {r.min():.2f} to {r.max():.2f} x glass radius "
          f"(predicted 0.46 to 3.40)")

    print()
    print("=== dispersion ordering (the sharpest test) ===")
    radii = {}
    for i, ch in enumerate("RGB"):
        ch_lum = a[:, :, i]
        m = ch_lum > np.percentile(ch_lum, args.caustic_percentile)
        if m.sum() > 30:
            rr = np.hypot((np.where(m)[1] - cx) / args.radius,
                          (cy - np.where(m)[0]) / args.radius)
            radii[ch] = float(rr.mean())
    if len(radii) == 3:
        for ch in "RGB":
            print(f"  {ch}: {radii[ch]:.3f} x glass radius")
        sep = 100.0 * (radii["R"] - radii["B"]) / radii["B"]
        print(f"  R-B separation {sep:+.1f}% (predicted {RB_SEP_PRED:+.1f}%)")
        order = radii["R"] > radii["G"] > radii["B"]
        print(f"  ORDER red > green > blue: {'CORRECT' if order else 'INVERTED'}"
              + ("" if order else "   <-- this refutes the per-channel ray map"))
    else:
        print("  not enough per-channel pixels to test ordering")

    print()
    print("=== not tested here ===")
    print("  fringe structure: physical width 123 um, but a 0.53 deg source")
    print("  blurs the pattern by 925 um, so the fringes do not exist under")
    print("  sunlight. See docs/PHYSICAL_TEST.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
