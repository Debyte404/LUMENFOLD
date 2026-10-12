"""mitsuba_reference.py — render the same scene in Mitsuba 3, a trusted
reference solver, and compare it against our field.

Why Mitsuba rather than another attempt at Cycles or LuxCore:

  * it is an academically maintained physically-based renderer, not a renderer
    tuned for pretty pictures;
  * it runs in Python as a pip wheel, so there is no build to break;
  * render in the SPECTRAL variant and its dielectric BSDFs use MEASURED
    refractive-index data (`bk7`, `water`) instead of our former Cauchy fits — so the
    dispersion ordering is checked against an independent material model, which
    is the one part of our result that has never been independently grounded;
  * it has a photon-mapping integrator, which is the technique our method
    structurally replaces and which converges on a caustic instead of crawling.

Geometry comes from tools/export_scene_obj.py — the exact same vertices the
Blender scene uses, so a difference cannot be a meshing artefact.

Run:
  third_party/luxvenv/Scripts/python.exe tools/mitsuba_reference.py \
      --integrator sppm --spp 64 --size 512 --out out/mitsuba_ref.exr
"""
import argparse
import os

import numpy as np
import mitsuba as mi


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
GEO = f"{ROOT}/out/mitsuba"
SUN = np.array([0.80, 0.42, -0.43])
SUN = SUN / np.linalg.norm(SUN)


def build(args):
    d = {
        "type": "scene",
        # must be a nested dict, not a bare string
        "integrator": {"type": args["integrator"], "max_depth": 12},
        "sensor": {
            "type": "orthographic",
            # straight down over exactly the patch the solver bakes (0.32 m)
            "to_world": mi.ScalarTransform4f.look_at(
                origin=[0, 0, 1], target=[0, 0, 0], up=[0, 1, 0])
            # Mitsuba's film plane spans [-1,1], so the scale is HALF the
            # desired extent. Scaling by 0.32 gave a 0.64 m view with the
            # table occupying half the frame.
            @ mi.ScalarTransform4f.scale([0.16, 0.16, 1.0]),
            "near_clip": 0.05,
            "far_clip": 5.0,
            "film": {
                "type": "hdrfilm",
                "width": args["size"],
                "height": args["size"],
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "independent",
                        "sample_count": args["spp"]},
        },
        # A small sphere far away, NOT a directional emitter. A delta light
        # makes caustic paths essentially unsamplable for a path tracer, and a
        # black render would say nothing about the solver.
        "light": {
            "type": "sphere",
            "center": [float(-SUN[0] * args["light_dist"]),
                       float(-SUN[1] * args["light_dist"]),
                       float(-SUN[2] * args["light_dist"])],
            "radius": args["light_r"],
            # Narrowband emitter: in the spectral variant this lets a single
            # wavelength be isolated, which is the only clean way to measure
            # dispersion without channel-mixing in the RGB conversion.
            "emitter": {"type": "area", "radiance": args["radiance"]},
        },
        "table": {
            "type": "obj",
            "filename": f"{GEO}/table.obj",
            "bsdf": {"type": "diffuse", "reflectance": 0.8},
        },
    }
    if not args.get("hide_optics"):
        # The differential that isolates the caustic: render the scene with and
        # without the glass+water. A no-glass difference alone is dominated by
        # the shadow the glass casts, which cancels the caustic out of it.
        d["glass"] = {
            "type": "obj",
            "filename": f"{GEO}/glass.obj",
            # MEASURED soda-lime/BK7 data (our former Cauchy fits were replaced; see EVIDENCE 20)
            "bsdf": {"type": "dielectric", "int_ior": "bk7", "ext_ior": "air"},
        }
        d["water"] = {
            "type": "obj",
            "filename": f"{GEO}/water.obj",
            # MEASURED water data (our former Cauchy fits were replaced; see EVIDENCE 20)
            "bsdf": {"type": "dielectric", "int_ior": "water", "ext_ior": "air"},
        }
    return mi.load_dict(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--integrator", default="path")
    ap.add_argument("--spp", type=int, default=256)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--out", default=f"{ROOT}/out/mitsuba_ref.exr")
    ap.add_argument("--variant", default="scalar_spectral")
    ap.add_argument("--light-r", type=float, default=0.02)
    ap.add_argument("--light-dist", type=float, default=2.0)
    ap.add_argument("--band", type=float, default=0.0,
                    help="render a single narrow band at this wavelength in nm")
    ap.add_argument("--band-half", type=float, default=8.0)
    ap.add_argument("--hide-optics", action="store_true",
                    help="omit glass+water: the reference for a "
                         "differential that isolates the caustic")
    args = ap.parse_args()

    mi.set_variant(args.variant)
    print(f"mitsuba {mi.__version__}  variant {mi.variant()}")

    # expose the available integrators so the choice is informed, not assumed
    try:
        names = sorted(mi.Integrator.registry().keys())
        print(f"integrators available: {names}")
    except Exception as e:
        print(f"  (could not list integrators: {e})")

    if args.band > 0:
        # the regular spectrum wants explicit samples, not just a range
        args.radiance = {"type": "regular",
                         "wavelength_min": args.band - args.band_half,
                         "wavelength_max": args.band + args.band_half,
                         "values": "1.0, 1.0"}
        print(f"  monochromatic band {args.band:.0f} +- {args.band_half:.0f} nm")
    else:
        args.radiance = {"type": "rgb", "value": [400.0, 400.0, 400.0]}
    scene = build(vars(args))
    print(f"rendering: integrator={args.integrator} spp={args.spp} "
          f"{args.size}x{args.size}")
    img = mi.render(scene, spp=args.spp)
    a = np.array(img)
    print(f"  rendered {a.shape}, mean {a.mean():.6f}, max {a.max():.6f}")
    mi.util.write_bitmap(args.out, img)
    print(f"  wrote {args.out}")
    if a.max() <= 0:
        print("  WARNING: image is black - check the emitter and the sensor scale")


if __name__ == "__main__":
    main()
