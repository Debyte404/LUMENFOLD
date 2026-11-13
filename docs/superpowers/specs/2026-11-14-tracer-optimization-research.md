# Tracer Optimization — Literature Review and Phased Plan

**Hardware (measured 2026-11-14):** Intel i7-14650HX, 16 cores / 24 threads,
2.2 GHz base; NVIDIA RTX 4060 Laptop (OptiX + CUDA exposed by Blender 5.2.3);
16 GB DDR5-5600. The RTX 4060 has 3rd-generation RT cores and 4th-generation
tensor cores, so hardware BVH traversal and hardware denoising are both
available.

**Where the time goes today:** the addon's mesh bake is a pure-numpy tracer:
1024^2 rays x 34,938 triangles x 3 channels = 1.05M x 35k x 3 intersection
tests, measured at 13.9 ms/ray on this machine (13,914 s for the last bake).
A numpy BVH cut that to 1.84x; the remaining cost is Python-level per-ray
overhead, not the tree.

## Papers that bear on this

| Paper | What it gives us |
|---|---|
| Parker et al., *OptiX: A General Purpose Ray Tracing Engine*, TOG 2010 | The GPU ray-tracing engine; BVH build/traversal on the device, user-supplied intersection programs. The template for a GPU tracer that is not a renderer rewrite. |
| Hachisuka, Ogaki, Jensen, *Progressive Photon Mapping*, TOG 2008 | The right algorithm class for caustics: a ray-tracing pass plus repeated photon passes with a shrinking radius, converging to the correct radiance with bounded memory. Our bake is a one-pass photon map; PPM is the route to Cycles-grade smoothness. |
| Hachisuka, Jensen, *Parallel Progressive Photon Mapping on GPUs*, SIGGRAPH Asia 2010 | Data-parallel photon-map construction and range queries (stochastic spatial hashing). The implementation strategy for PPM on the GPU. |
| Ernst, Akenine-Möller, Jensen, *Interactive Rendering of Caustics using Interpolated Warped Volumes*, GI 2005 | Caustic volumes on the GPU; a reminder that caustics can be rasterized as volumes instead of splatted as points. |
| Yan et al., *Rendering Specular Microgeometry with Wave Optics*, TOG 2018 | Wave-optical BRDF evaluation over a coherence area; the same wave-vs-geometric split our Airy correction lives in. |
| *A Generalized Ray Formulation for Wave-Optics Rendering*, TOG 2023/24 | Wave-optical path tracing with generalized rays; the state of the art for making wave effects affordable in a renderer. |
| Borghi, *Catastrophe optics of sharp-edge diffraction*, Opt. Lett. 2016 | The Airy-function formulation at fold caustics — the theoretical footing of our band correction. |
| *An Evaluation of Existing BVH Traversal Algorithms for Efficient Multi-Hit Ray Tracing*, HPG 2015 poster | Traversal-order and layout choices for multi-hit rays; relevant because our secondary rays are incoherent. |
| *RTNN: Accelerating Neighbor Search Using Hardware Ray Tracing*, PPoPP 2022 | Shows the RT-core payoff for incoherent queries: 2.2-65x over optimized CUDA. Our rays are incoherent in the same way. |
| *Interactive Calculation of Light Refraction and Caustics Using a GPU*, Program. Comput. Softw. 2024 | A modern GPU refraction/caustic pipeline; confirms the volume/propagation split is still the practical approach. |

## What the literature says to do, in order

1. **Move the per-ray work out of Python.** The 1.84x numpy BVH is bounded by
   Python overhead, not the tree. A C++ BVH (Blender's `BVHTree`, already
   available inside the addon) removes that ceiling with no build step.
2. **Use the RT cores for the coherent part.** The bake's primary rays are
   coherent (a grid through the mesh), the secondary rays are not. OptiX
   handles both; the measured RT-core gains on incoherent queries (RTNN) are
   2-65x over optimized CUDA, so 100x+ over Python is the right expectation.
3. **Adopt the PPM convergence model, not a bigger one-pass grid.** The
   remaining noise is a sampling problem: 0.26-1.4 hits/texel. PPM's shrinking
   radius converges with bounded memory; a 4x grid does not.
4. **Denoise the beauty pass with OptiX.** The 4060's tensor cores run the
   OptiX denoiser; the render is already Cycles, so this is a one-line device
   setting, not a project.
5. **Keep wave optics where it is.** The Airy band correction is the method's
   contribution; the optimization is in the transport, not in the physics.

## Phased plan

### Phase 1 — Blender BVHTree in the addon (days, no build step)

`mathutils.bvhtree.BVHTree.FromPolygons` is a C++ BVH in Blender's Python.
Replace `_shoot`'s numpy triangle loop with `bv.ray_cast` for both interfaces.
Expected 10-100x (target: the 3.86 h bake in under 5 min). Parity gate: hit
sets within 1e-6 of the numpy tracer on the fixture and the dragon. Plan:
`docs/superpowers/plans/2026-11-14-mesh-tracer-bvhtree-addon.md`.

### Phase 2 — OptiX tracer (weeks, optional binary)

A standalone C++/OptiX two-interface tracer that writes the same field format
as the addon (`caustic_mesh.png` + a JSON sidecar). Invoked as a subprocess,
like `showcase.exe`, so the addon keeps its "no build" contract: if the
binary is present, use it; otherwise fall back to the BVHTree path. Expected
100-1000x. This is the only route to GPU speed for *our* field; Cycles cannot
be used as the tracer because we need the field, not a render.

### Phase 3 — Progressive photon mapping (weeks, quality)

Move from a one-pass histogram to PPM's shrinking-radius estimate (Hachisuka
2008), with the GPU photon-map construction from Hachisuka & Jensen 2010.
This is what turns "1.4 hits/texel grain" into a converged caustic, and it is
the honest path to rivaling Cycles in beauty: the remaining gap is sampling,
not transport.

### Immediate quality wins (independent of the above)

- **Smooth shading normals.** The dragon is 87,130 polygons, all smooth-shaded,
  with custom corner normals; the tracer was refracting off the geometric face
  normal, so each facet produced its own caustic patch ("boxes"). Interpolating
  the mesh's corner normals barycentrically at both interfaces removes the
  facet structure. This is the single largest appearance win after the grid.
- Achromatic IOR for the dragon (the material is achromatic; per-channel BK7
  is a spurious rainbow for this comparison).
- OptiX denoiser on the beauty render (`scene.cycles.device = "GPU"`,
  denoiser `OPTIX`).
- Sharper display band (`airy_scale` ~0.5 mm) if the ribbon looks flat.

## What this does not fix

A baked emission texture is not transported light. Even a converged PPM field
composited as emission lacks specular interaction and volumetric coupling.
The ceiling is transport; the paper's claim is placement (r = 0.999), and the
beauty panel should be presented as an estimate, not a renderer parity claim.
