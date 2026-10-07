"""tail_study.py — where rays actually fail: unbounded intensity at folds.

RMSE says the two models are 'close on average' and hides the thing that makes
caustics hard. At a fold the geometric map has zero area element, so intensity
diverges; a Monte Carlo estimator responds with fireflies (isolated huge pixels)
that dominate the histogram tail and never fully settle. The wave (Airy) model
is bounded by construction.

We measure the TAIL, not the mean: max intensity, 99.9th percentile, and the
fraction of the image blown past the display cap, for
  * geometric Monte Carlo at M samples per cell, and
  * our deterministic pass at the same grid, and at higher grids,
against the converged wave-corrected truth.
"""
import numpy as np

import efficiency_study as es
import fold_diag as fd

CAP = 6.0  # the display cap used by the tonemapper; >CAP is "blown out"


def stats(field, ref=None):
    f = field[..., 1] if field.ndim == 3 else field
    out = dict(
        max=float(f.max()),
        p999=float(np.percentile(f, 99.9)),
        frac_gt_cap=float((f > CAP).mean()),
        frac_gt_8=float((f > 8.0).mean()),
    )
    if ref is not None:
        out["rmse"] = es.rmse(f, ref[..., 1] if ref.ndim == 3 else ref)
    return out


def wave_field(t, n, airy=0.02):
    g, Hx, Hy = fd.geom_field(t, n)
    det = fd.jacobian_det(Hx, Hy, n)
    thr = np.percentile(np.abs(det), 2.0)
    fold = np.abs(det) < thr
    return fd.correct_bandlocal(g, airy, fold), g


def wave_field_percentile(t, n, airy=0.02):
    g, _, _ = fd.geom_field(t, n)
    return fd.correct_bandlocal(g, airy, g > np.percentile(g, 98)), g


def main():
    t = 1.7
    print(f"fold intensity ceiling study (t={t}, display cap = {CAP}x)\n")

    # truth at 2048^2 so every estimator below is compared to something finer
    truth_hi, _ = wave_field(t, 2048)
    truth = fd.to_n(truth_hi, 256)
    ref_geom_hi, _, _ = fd.geom_field(t, 2048)
    ref_geom = fd.to_n(ref_geom_hi, 256)

    print("--- geometric Monte Carlo, 256^2 grid ---")
    print(f"{'M':>6} {'splats':>9} {'max':>10} {'p99.9':>8} {'%>cap':>7} {'%>8x':>7} {'RMSE vs truth':>14}")
    rng_rows = []
    m = 1
    while m <= 256:
        f = es.mc_geometric(t, 256, m)
        s = stats(f, truth)
        rng_rows.append((m, s))
        print(f"{m:>6} {m*256*256:>9} {s['max']:>10.2f} {s['p999']:>8.2f} "
              f"{s['frac_gt_cap']*100:>6.2f}% {s['frac_gt_8']*100:>6.2f}% {s['rmse']:>14.5f}")
        m *= 4

    print("\n--- our deterministic pass ---")
    print(f"{'grid':>6} {'mode':>11} {'splats':>9} {'max':>10} {'p99.9':>8} {'%>cap':>7} "
          f"{'%>8x':>7} {'RMSE vs truth':>14}")
    for n in (256, 512, 1024, 2048):
        for label, wf in (("percentile", wave_field_percentile), ("detJ", wave_field)):
            w, _ = wf(t, n)
            wr = fd.to_n(w, 256)
            s = stats(wr, truth)
            tag = "  (truth grid)" if n == 2048 else ""
            print(f"{n:>6} {label:>11} {n*n:>9} {s['max']:>10.2f} {s['p999']:>8.2f} "
                  f"{s['frac_gt_cap']*100:>6.2f}% {s['frac_gt_8']*100:>6.2f}% {s['rmse']:>14.5f}{tag}")

    print("\n--- reference fields (256^2) ---")
    for name, f in (("converged wave truth", truth), ("converged geometric", ref_geom)):
        s = stats(f)
        print(f"{name:>22}: max={s['max']:>8.2f} p99.9={s['p999']:>7.2f} "
              f"%>cap={s['frac_gt_cap']*100:>6.2f}% %>8x={s['frac_gt_8']*100:>6.2f}%")

    print(f"\ngeometric tail: max {rng_rows[0][1]['max']:.1f}x -> {rng_rows[-1][1]['max']:.1f}x "
          f"over 256x more samples (slow tail decay)")
    print(f"wave model ceiling: cap*1.35 = {CAP*1.35:.2f}x (respect only if renormalized before clamp)")


if __name__ == "__main__":
    main()
