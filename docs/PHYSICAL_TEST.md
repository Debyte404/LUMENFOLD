# How to verify this against reality

Every check in this project so far is simulation against simulation: Cycles,
a brute-force tracer, and a closed-form analytic cylinder. Those establish that
the maths is implemented correctly and that the ray map is right for the geometry
we model. **None of them can tell us whether a real glass of water on a real table
under real light produces the pattern we draw.** Only a measurement can.

This file is the protocol, the falsifiable predictions, and — importantly — the
list of what a photograph *cannot* settle.

## 1. What a photograph CAN verify

| quantity | predicted | how to measure | tolerance |
|---|---|---|---|
| where the caustic lands | centroid at **1.5 x glass radius** from the glass centre, on the **sun's azimuth (+0.3 deg)** | bright-region centroid vs glass centre, with a scale reference | +-5% of radius |
| the fan's angular span | spans roughly **-40 to +95 deg** of azimuth, **16 to 119 mm** radius | bounding the bright region | qualitative |
| the fold's position | the sharp bright edge at the radius where the ray map folds | visual/radial profile | few mm |
| dispersion ORDER | **red lands farther out than blue** | per-colour centroids in the photo | direction |
| dispersion SIZE | R-B separation = **2.9% of the radius** | per-colour centroids | +-1% |
| peak boundedness | the fold's intensity is **finite**, a ridge not a spike | HDR exposure, peak/background ratio | see below |

`tools/physical_predictions.py` prints these from the current bake;
`tools/verify_against_photo.py` measures the same quantities from a photograph.

## 2. What a photograph CANNOT verify — and why it matters

**The fringe structure. Not the spacing, not the count, nothing about it.**

Two independent reasons, both fatal:

1. **The fringes do not exist under this illumination.** A fold has a physical
   diffraction width of **123 um** for this geometry (`tools/fringe_scale.py`,
   from the ray map's cubic term). But a source of finite angular size blurs the
   pattern by `angle x distance`: the sun is 0.53 deg, and at ~100 mm to where
   the caustic forms that is **925 um — 7.5x the fringe spacing**. The fringes are
   washed out. Under a real sun, this caustic is a smooth bright ridge with no
   visible fringes at all. That matches everyday experience: nobody sees fringes
   in a glass of water's caustic in sunlight.

2. **What we render is 12x coarser than even that.** Our `airy_scale` is
   1500 um against a physical 123 um. It was chosen for *visibility* — at least
   3 pixels per fringe at the bake resolution — and documented as such, but that
   makes it a drawing, not a prediction.

So the honest position: **the fringes in our renders make the wave correction
legible; they do not depict reality, and no photograph can confirm them.** Any
statement implying the fringe pattern has been or could be experimentally
validated should be removed.

**What survives that critique is boundedness.** The physical claim of the wave
model is not "there are fringes" but "the intensity stays finite at the fold
instead of diverging". That IS testable: photograph the caustic with HDR
(exposed for the caustic, not the background) and compare the peak-to-background
ratio against the prediction. A geometric ray model predicts a divergence; a
wave model predicts a bounded ridge. If the measured peak is finite and matches
the bounded prediction, that is real evidence.

## 3. The apparatus

1. **Scene**: the glass from the simulation — outer radius 35 mm, height 90 mm,
   filled to 59 mm — on a matte surface. The surface must be matte; a glossy one
   reflects the source's disc back and swamps the caustic.
2. **Light**: the sun, or a lamp far enough away to be effectively parallel. Its
   direction must be *known*, not eyeballed: a timestamp and location for the
   sun, or a measured speaker-to-glass geometry for a lamp. Elevation and azimuth
   both matter, and the caustic's position moves with them.
3. **Scale reference**: one known length in frame. A ruler beside the glass, or
   the glass's outer diameter measured with calipers. Everything above is
   expressed in glass radii precisely so that this is the only absolute number
   needed.
4. **Exposure**: bracket at least three stops and merge to HDR. The reference
   photograph we already have is **clipped across 2,919 pixels** — its caustic
   core is blown, so its intensities are unusable and only its geometry could
   ever be compared.
5. **Calibration for the tool**: the glass centre in pixels, the glass's outer
   radius in pixels, and the direction to the light in image coordinates.

## 4. What would refute the model

In rough order of how badly it would hurt:

* the caustic's bright centroid landing off the sun's azimuth, or at a radius far
  from 1.5 glass radii;
* **blue landing farther out than red** — that inverts the index ordering and
  the per-channel ray map is simply wrong;
* a fold intensity consistent with a divergence, with no bounded ridge;
* a caustic with fine fringes visible under sunlight, which would mean our
  understanding of the source-blur argument is wrong.

## 5. Why the existing photograph cannot do this

`clip_20261007_180753_5.png` is a real caustic, but four parameters are unknown:
the glass's dimensions, the water level, the light direction, and the camera's
scale and pose. Two measurable features fitted with four free parameters is not a
test — a match would be meaningless and a mismatch uninterpretable. It also
clips. It is useful as a *target* for what a real caustic looks like, not as
evidence.

> NOTICE (2026-10-11): the chromatic-split MAGNITUDES in this document are
> STALE. The index model they rested on was a fitted Cauchy whose dispersion was
> 1.97x the measured value; both indices are now measured data (Daimon & Masumura
> 2007 for water, Rubin 1985 for soda-lime glass) and our geometric split is 1.4x
> smaller. The ORDER (red outside blue, monotonic) is verified against PBRT SPPM
> with a like-for-like estimator, but the stills and clips here predate the fix
> and must be re-rendered before any dispersion number is quoted. See
> docs/EVIDENCE.md section 20.
