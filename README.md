# Wave-corrected caustics over photon splatting

A caustic estimator that replaces the geometric fold singularity with the wave-optical
Airy profile inside a detected fold band, plus a measured comparison of it against the
caustic solvers in current practice — **PBRT-v4 SPPM, Blender Cycles, and Mitsuba 3**.

**The paper:** [`docs/paper/main.pdf`](docs/paper/main.pdf) — typeset in the official
Computer Graphics Forum class (`egpubl.cls`, Eurographics), 21 pages, with lemmas,
theorems and proofs. Source is `docs/paper/main.tex`; rebuild with
`python tools/build_paper_pdf.py`. The earlier markdown draft is kept at
[`docs/PAPER.md`](docs/PAPER.md).
Every number in it traces to a measurement in [`docs/EVIDENCE.md`](docs/EVIDENCE.md),
including the ones that went against us — the adversarial audit of our own claims is
[`docs/CRITIQUE.md`](docs/CRITIQUE.md), and every citation was verified against
Crossref by `tools/verify_refs.py`.

## Headline result

Quality, scored on one independent axis (a brute-force geometric trace of 810 k
explicit rays that neither method produced) with an identical metric:

| correlation vs ground truth | ours | PBRT-v4 SPPM | Cycles |
|---|---|---|---|
| 40 mm tiles | **0.917** | 0.853 | 0.828 |
| 5 mm tiles | 0.721 | 0.722 | 0.405 |
| coverage of the ground-truth caustic core | **99.9%** | — | 54.7% |

Speed, and it is *not* a uniform win:

| workload | ours | Cycles | PBRT-v4 SPPM |
|---|---|---|---|
| produce a caustic, 512² | **36.22 ms** (8 threads) | — | 34 s |
| production still, 1600×1000 @ 2048 spp | 34.1 s | 36.1 s | — |
| orbit clip, 1280×720, 120 frames | **773.3 s** | 1043.2 s | — |
| ripple clip, 960×540, 72 frames | 481.9 s | **453.0 s** | — |

The method is 2–3 orders of magnitude cheaper at *producing* a caustic for this
geometry family, and wins on animations that re-bake per frame (1.35×, with 7.9× less
caustic flicker) — but it ties on a single still, loses to Cycles on the static-camera
clip, and plain Monte-Carlo is more accurate below ~262 k splats. Our caustic is also
**too smooth**: 2.30× broader than the brute-force trace at 1024² (1.87× at 4096²).

## The three ripple GIFs

The same animating caustic, three ways, for side-by-side viewing:

| file | what it shows |
|---|---|
| `docs/media/ripple_ours.gif` | our wave-corrected field, re-baked at every frame's wave phase |
| `docs/media/ripple_cycles.gif` | Blender Cycles tracing the caustics itself |
| `docs/media/ripple_spmm.gif` | PBRT-v4 SPPM, the reference conforming solver |

72 frames (one full wave cycle), 640×360, looping. One camera for all three —
verified identical by projecting known world points through both camera models
(worst disagreement 0.0000, `tools/cam_projection_check.py`) — zoomed out far
enough that the whole fan is in frame with 23–31% clearance. The band uses the
**physical** fringe width (0.123 mm), not the 12.2× visibility exaggeration the
older clips used, so there are no decorative fringes: the colour you see is the
measured index dispersion. The subject exposure is matched across all three
(the PBRT scene is bare, so its background is black rather than lit — a scene
difference, documented in `docs/EVIDENCE.md` §14.5f).

Regenerate with `python tools/ripple_gifs.py`.

## No exaggerated fringes

Earlier versions of this repo baked the fold band at `airy_scale = 1.5 mm` so the
fringes would be visible on screen. That value is **12.2× the physical fringe width**
for this geometry (0.123 mm), and the real-time baker's own default of 20 mm is 163×.
Those renders are honest pictures of a model that is not this one, and every result
in the paper now uses the physical width.

![physical vs exaggerated](docs/media/no_exaggeration.png)

Left: our solution at the **physical** fringe width, which is what the paper and the
GIFs use. Middle: the same band stretched 12.2× for visibility, which is what the
older stills in `out/` show and what no result is quoted from. Right: the difference.

Worth noticing from the difference panel: exaggeration changes the *fringe structure*
inside the band, not the position or the extent of the caustic — the bright region
keeps the same footprint in both. So an exaggerated render is not "wrong about where
the light goes", it is wrong about the texture inside the fold, and at the physical
width that texture is below the resolution of the bake anyway (the band is about 2 px
at 1024²). That is the same conclusion the paper reaches from the coherence argument:
the fringes are the visible signature of the correction, not its justification.

Regenerate with `python tools/make_no_exaggeration_figure.py`.

## What the method does

1. **Geometric backbone.** Refract the surface by Snell's law and splat to the
   receiver, with the ray map `H(x)` and its Jacobian `det J`. Efficient wherever the
   map is smooth, divergent where it folds.
2. **Fold locus.** Detect `det J = 0` analytically (2nd percentile) instead of by
   intensity percentile — the percentile detector always flags 2% of pixels and
   therefore never converges.
3. **Band-local Airy replacement.** Inside the band, redistribute the band's *own*
   energy by `|Ai(-s/w)|²` with per-channel width `w ∝ λ^(2/3)`, so fringes stay finite
   and chromatic ordering follows from the profile and the measured index laws rather
   than being added as an effect.

Verified independently of the solver: the profile equals true Airy to 8.118e-03 of
peak, the canonical cubic-phase fold integral peaks at `X = −1.00` against the analytic
`−1.0188`, the fringe exponent measures 0.6977 against an analytic `2/3`, and a
closed-form cylinder caustic is reproduced to **0.1 mm**.

## Repository map

```
src/render/caustic.*          pool-scene caustic field baker (1-D, real-time path)
src/render/airy_lut.*         the 2048-entry Airy profile table (+ generator)
src/app/showcase_main.cpp     the paper's offline estimator + showcase renderer
src/app/bench_main.cpp        bake timing harness
src/app/dump_main|parity_main parity / dump helpers
src/physics/two_medium.*      ORIGIN of the scene: air/water buoyancy (see History)
src/app/viewer_*.cpp          MuJoCo + Filament viewer from that earlier stage
models/, blender_addon/       MJCF scene, Blender caustic injector
tools/                        measurement + verification harnesses  -> tools/README.md
docs/                         paper, evidence, audit, figures, media -> docs/README.md
third_party/                  prebuilt drops, NOT committed (fetch script in tools/)
out/                          working artefacts (gitignored); out/probes = superseded
```

## Build

```bash
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

The measurement and verification harnesses are Python:

```bash
python tools/verify_ray_map.py            # the independent brute-force ground truth
python tools/verify_wave_correction.py    # Airy profile, fold integral, λ^(2/3)  (needs scipy)
python tools/accuracy_vs_ground_truth.py  # three-way accuracy against that truth
python tools/spmm_vs_groundtruth.py       # SPPM scored on the same axis
python tools/analytic_caustic.py          # closed-form cylinder reference
python tools/energy_audit.py              # Fresnel-weighted energy bookkeeping
python tools/ensemble_study.py            # robustness across 8 wave phases
python tools/make_paper_figures.py        # regenerate docs/figures/
python tools/make_paper_figures_pdf.py    # the paper's vector PDF figures
python tools/build_paper_pdf.py           # compile the CGF paper (tectonic)
python tools/check_paper.py               # dangling refs / uncited bibliography
python tools/scan_ai_tells.py             # AI-writing tells in the manuscript
python tools/verify_refs.py               # every citation, against Crossref
```

The full reproduction list, including the renderer-side harnesses (PBRT-v4 SPPM,
Mitsuba 3, Blender/Cycles) is Section 9 of the paper.

## Honest scope

One scene, one machine, no laboratory ground truth — this is a **computational
evaluation** and physical-apparatus validation is deliberately out of scope. The
physical claim is one of *form* (finite fringes, chromatic ordering, no
`1/√·` divergence), not absolute fringe width: for a glass this size the real fringes
are 0.123 mm wide and a 0.53° sun blurs them away entirely, so a photograph would not
show them however they are rendered. The GIFs and the paper therefore use the physical
width and show no decorative fringes at all; the exaggerated renders exist only in
`out/` and are labelled as superseded. The efficiency claim is amortised against **one
fixed geometry family**; change the optic and the solver needs new work. Ten further
limits are itemised in Section 7 of the paper, and three claims from our own earlier
record are explicitly withdrawn there.

## History

This repo began as an air/water interaction demo: `src/physics/two_medium.*` implements
the Archimedes force with a centre of buoyancy for MuJoCo (the gap filed as
google-deepmind/mujoco#3452, closed unmerged), rendered through Filament. `models/pool.xml`
and the `viewer_*` binaries are that stage, kept because the caustic work grew out of the
same scene. The caustics estimator and the comparison against SPPM/Cycles/Mitsuba — the
current work — live in `src/render/caustic.*` and `src/app/showcase_main.cpp`.
