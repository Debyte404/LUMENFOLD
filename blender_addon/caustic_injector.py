"""Wave Caustic Injector — a Blender add-on that replaces Cycles' stochastic
caustics with a baked, wave-corrected caustic from the solver in
this repository.

Why: Cycles discovers caustics by random path tracing, so they are the noisiest
thing in a glass render and get worse as the light source shrinks. This add-on
bakes the caustic deterministically (wave-corrected: fold locus + Airy profile +
band-local flux conservation, per channel) in a few hundred milliseconds, then
injects it into the shader as light. The result is a caustic that is noise-free
at ANY sample count, keeps finite energy at the fold (where ray tracing explodes)
and carries per-channel dispersion.

Install: Edit > Preferences > Add-ons > Install from Disk -> pick this file.
Use:     N-panel (3D View sidebar) > "Caustic" tab.
"""

import os
import subprocess
import sys
import time

import bpy


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

bl_info = {
    "name": "Wave Caustic Injector",
    "author": "caustics project",
    "version": (0, 3, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Caustic",
    "description": "Bake wave-corrected caustics and inject them into Cycles "
                   "materials as noise-free light",
    "category": "Render",
}

DEFAULT_SOLVER = _ROOT + "/build/src/app/Release/showcase.exe"
TMP_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp",
                       "blender_caustic")


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------
class CausticProps(bpy.types.PropertyGroup):
    solver: bpy.props.StringProperty(
        name="Solver",
        description="Path to showcase.exe (bakes the caustic and dumps it)",
        default=DEFAULT_SOLVER, subtype="FILE_PATH")
    resolution: bpy.props.IntProperty(
        name="Resolution", description="Caustic bake grid",
        default=1024, min=128, max=4096)
    airy_scale: bpy.props.FloatProperty(
        name="Airy scale (m)",
        description="Fringe width used near the fold. Documented visibility "
                    "parameter, not a physical prediction",
        default=0.006, min=0.0005, max=0.05, precision=4)
    wave_amp: bpy.props.FloatProperty(
        name="Ripple amplitude (mm)",
        description="Water-surface ripple amplitude; 0 gives the smooth "
                    "cylindrical fan",
        default=0.65, min=0.0, max=5.0)
    wave_time: bpy.props.FloatProperty(
        name="Ripple phase", description="Phase of the ripple field",
        default=0.0)
    gain: bpy.props.FloatProperty(
        name="Injection gain",
        description="How bright the injected caustic is", default=0.25,
        min=0.0, max=4.0)
    uv_scale: bpy.props.FloatProperty(
        name="UV scale", description="Fit the baked patch to the target's UVs",
        default=1.0, min=0.01, max=100.0)
    disable_cycles_caustics: bpy.props.BoolProperty(
        name="Disable Cycles caustics",
        description="Turn off Cycles' own refractive/reflective caustics so the "
                    "injected caustic is the only one (that is the point)",
        default=True)
    target: bpy.props.PointerProperty(
        name="Target", type=bpy.types.Object,
        description="Object that receives the caustic (usually the table)")
    # --- mesh bake (any closed mesh) -----------------------------------------
    # Solver scene mode is untouched; these only feed CAUSTIC_OT_bake_mesh.
    bake_source: bpy.props.EnumProperty(
        name="Bake source",
        items=[("SOLVER", "Solver scene", "Calibrated pool scene via showcase.exe"),
               ("MESH", "Selected mesh", "Any closed mesh via the in-addon tracer")],
        default="SOLVER")
    mesh_object: bpy.props.PointerProperty(
        name="Mesh object", type=bpy.types.Object,
        description="Closed glass mesh to bake (mesh Bake mode)")
    mesh_resolution: bpy.props.IntProperty(
        name="Mesh res", description="Tracer grid per side (cost ~ res^2 x tris)",
        default=128, min=16, max=4096)
    mesh_airy: bpy.props.FloatProperty(
        name="Mesh Airy (m)",
        description="Fringe width used near the fold. Documented visibility "
                    "parameter, not a physical prediction. Below half a texel "
                    "the fringe cannot be resolved, so the bake shows the "
                    "geometric field instead (canonical 6.77 um at 550 nm)",
        default=0.006, min=1e-6, max=0.05, precision=7)
    mesh_ray_mult: bpy.props.IntProperty(
        name="Ray mult",
        description="Rays per grid line (n_side = res x mult). Above 1 it "
                    "supersamples rays above grid resolution, trading bake "
                    "time for less shot noise",
        default=2, min=1, max=8)
    mesh_accel: bpy.props.EnumProperty(
        name="Accel",
        description="Ray-caster backend. BVHTree uses Blender's compiled "
                    "C++ BVH (10-100x faster); Numpy is the reference "
                    "implementation and the parity target",
        items=[("BVHTREE", "BVHTree (fast)", "Blender's C++ BVH, per-ray ray_cast"),
               ("NUMPY", "Numpy (reference)", "Pure-numpy brute force, for parity")],
        default="BVHTREE")
    mesh_achromatic: bpy.props.BoolProperty(
        name="Achromatic IOR",
        description="Use the material's scalar IOR instead of per-channel BK7 "
                    "dispersion. Match a renderer that carries no dispersion "
                    "(e.g. Cycles' Principled glass) before comparing beauty",
        default=False)
    mesh_physical_exposure: bpy.props.BoolProperty(
        name="Physical exposure",
        description="Write the field in physical radiance (sun irradiance x "
                    "ray cell area / texel area x albedo/pi) instead of "
                    "peak-normalising it. Requires Injection gain = 1.0",
        default=False)
    inject_mode: bpy.props.EnumProperty(
        name="Inject mode",
        description="SURFACE adds emission to the receiver (matched panel). "
                    "LIGHT_CARD puts the field on an invisible emissive card "
                    "above the receiver, so the caustic is transported light: "
                    "the table's BSDF shades it and the glass receives it",
        items=[("SURFACE", "Surface emission", "Emission added to the target material"),
               ("LIGHT_CARD", "Light card (transport)",
                "Invisible emissive card above the receiver; the table's BSDF shades it")],
        default="SURFACE")
    directional: bpy.props.BoolProperty(
        name="Directional response",
        description="Modulate the injected caustic by the receiver's specular "
                    "BRDF for the sun direction (GGX): the caustic answers to "
                    "gloss instead of glowing view-independently. Lambertian "
                    "receivers are unchanged by construction",
        default=False)
    mesh_frame: bpy.props.EnumProperty(
        name="Frame",
        description="Receiver framing. AUTO probes the hit bbox and bins the "
                    "same rays into a fan-sized patch: finer texels and more "
                    "hits per texel at no extra trace cost",
        items=[("FULL", "Full receiver", "Bin over the whole receiver patch"),
               ("AUTO", "Fan-framed", "Probe, then bin only around the fan")],
        default="AUTO")
    mesh_frame_margin: bpy.props.FloatProperty(
        name="Frame margin (m)",
        description="Padding around the probe hit bbox when framing",
        default=0.15, min=0.01, max=2.0, precision=3)
    # state set by the last mesh bake; identity/zero means "full receiver"
    frame_uv: bpy.props.FloatVectorProperty(
        name="Frame UV", size=4, default=(0.0, 0.0, 1.0, 1.0),
        description="u0, v0, du, dv of the last baked patch in the target's "
                    "UVs; (0, 0, 1, 1) is the whole receiver")
    frame_rect: bpy.props.FloatVectorProperty(
        name="Frame rect", size=3, default=(0.0, 0.0, 0.0),
        description="World cx, cy, half of the last baked patch; half 0 means "
                    "the full receiver")
    sun_dir: bpy.props.FloatVectorProperty(
        name="Sun dir", size=3, default=(0.80, 0.42, -0.43),
        description="Fallback sun travel direction when the scene has no SUN lamp")
    seq_start: bpy.props.IntProperty(
        name="Seq start", default=1, min=1,
        description="First frame for sequence Bake")
    seq_end: bpy.props.IntProperty(
        name="Seq end", default=3, min=1,
        description="Last frame for sequence Bake (vertex count must not change)")
    # --- coloured media -----------------------------------------------------
    # Beer-Lambert, per metre, per channel. Two caveats worth stating where the
    # user meets them:
    #  * these are EXPERIMENT PARAMETERS, not measured materials. Cobalt glass is
    #    (300, 30, 8); a colour that reads correctly is a choice, not a datum.
    #  * the glass path is only ~3.5 mm (the wall) and the water ~90 mm, so a
    #    coefficient that looks small for water is large for glass. The defaults
    #    below are chosen to give a visible red in each.
    glass_absorb: bpy.props.FloatVectorProperty(
        name="Glass absorb", size=3, default=(30.0, 344.0, 721.0),
        min=0.0, max=5000.0, precision=1,
        description="Beer-Lambert per metre, R,G,B, through ~3.5 mm of glass")
    water_absorb: bpy.props.FloatVectorProperty(
        name="Water absorb", size=3, default=(1.17, 21.0, 38.9),
        min=0.0, max=5000.0, precision=1,
        description="Beer-Lambert per metre, R,G,B, through ~90 mm of water")
    medium_objects: bpy.props.PointerProperty(
        name="Medium objects", type=bpy.types.Object,
        description="Object whose materials get the volume tint. Run once per "
                    "object (glass object, then water object)")
    volumes_on: bpy.props.BoolProperty(default=False)
    image_path: bpy.props.StringProperty(default="")
    status: bpy.props.StringProperty(default="idle")
    last_ms: bpy.props.FloatProperty(default=0.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _absorb_into_material(mat, mu):
    """Connect a Volume Absorption node: Blender attenuates as
    exp(-Density*(1-Color)*L), so a per-channel mu becomes Density = max(mu) and
    Color = 1 - mu/max(mu). Idempotent: an existing MEDIUM_ node is replaced."""
    d = max(mu)
    if d <= 0.0 or not mat.use_nodes:
        return False
    nt = mat.node_tree
    for node in list(nt.nodes):
        if node.name.startswith("MEDIUM_"):
            nt.nodes.remove(node)
    out = nt.nodes.get("Material Output")
    if out is None:
        return False
    va = nt.nodes.new("ShaderNodeVolumeAbsorption")
    va.name = "MEDIUM_absorb"
    va.label = "MEDIUM_absorb"
    va.inputs["Color"].default_value = tuple(1.0 - v / d for v in mu) + (1.0,)
    va.inputs["Density"].default_value = d
    nt.links.new(va.outputs["Volume"], out.inputs["Volume"])
    return True


def _run_hidden(cmd, timeout=600):
    """Run the solver without flashing a console window on Windows."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _receiver_albedo(obj, default=(0.5, 0.5, 0.5)):
    """Base colour of the receiver's first Principled BSDF.

    The light card needs it: the baked field is a plate *radiance*
    (irradiance x albedo / pi), while a card emitting radiance L delivers
    pi*L to a coplanar receiver, which the receiver's BSDF turns into
    L*albedo. Dividing the card's emission by the albedo makes the plate
    reproduce the field instead of albedo times it.
    """
    for mat in (obj.data.materials if obj else []):
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                c = node.inputs["Base Color"].default_value
                return (float(c[0]), float(c[1]), float(c[2]))
    return tuple(default)


def _sun_light_dir(scene, fallback):
    """Unit vector toward the sun (world space) for the directional term.

    Reads the first SUN lamp's -Z axis; falls back to minus the configured
    sun travel direction when the scene has no SUN lamp.
    """
    from mathutils import Vector
    for o in getattr(scene, "objects", []):
        if o.type != "LIGHT":
            continue
        if getattr(getattr(o, "data", None), "type", None) != "SUN":
            continue
        d = o.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
        if d.length > 1e-9:
            return (float(-d[0] / d.length),
                    float(-d[1] / d.length),
                    float(-d[2] / d.length))
    f = Vector(tuple(fallback))
    if f.length < 1e-9:
        return (0.0, 0.0, 1.0)
    return (float(-f[0] / f.length),
            float(-f[1] / f.length),
            float(-f[2] / f.length))


def _math(nt, op, a=None, b=None, name=""):
    """One scalar Math node; a/b are sockets or floats (floats become defaults)."""
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    if name:
        n.name = name
    for i, v in ((0, a), (1, b)):
        if v is None:
            continue
        if isinstance(v, float):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n


def _vmath(nt, op, a=None, b=None, name=""):
    """One Vector Math node; a/b are sockets or 3-tuples (tuples become defaults)."""
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = op
    if name:
        n.name = name
    for i, v in ((0, a), (1, b)):
        if v is None:
            continue
        if isinstance(v, tuple):
            n.inputs[i].default_value = (float(v[0]), float(v[1]), float(v[2]))
        else:
            nt.links.new(v, n.inputs[i])
    return n


def _directional_factor(nt, sun_L, albedo, roughness, spec_level):
    """Per-channel caustic directional factor as a shader-node graph.

    Returns the RGB outputs socket of the ``CAUSTIC_dir_factor`` CombineXYZ
    node. The factor is ``1 + (pi/a_c) * f_s`` with ``f_s`` the scalar GGX
    specular term (Trowbridge-Reitz D, Schlick Fresnel, Schlick-GGX Smith G)
    evaluated for the sun direction, so a Lambertian receiver (F0 = 0)
    yields exactly 1. Geometry Normal/Incoming are world-space; ``sun_L``
    must already be a world-space unit vector toward the sun.
    """
    import math
    pi = math.pi
    a = [max(float(c), 0.02) for c in albedo]
    rough = min(max(float(roughness), 0.0), 1.0)
    f0 = min(max(0.08 * float(spec_level), 0.0), 1.0)

    if f0 <= 0.0:
        # Specular IOR Level 0 means no specular lobe at any angle, so the
        # caustic keeps its diffuse response: the factor is exactly 1. (The
        # Schlick (1-cos)^5 tail would otherwise add a grazing-only sheen
        # that a Lambertian receiver must not have.)
        one = nt.nodes.new("ShaderNodeCombineXYZ")
        one.name = "CAUSTIC_dir_factor"
        one.inputs["X"].default_value = 1.0
        one.inputs["Y"].default_value = 1.0
        one.inputs["Z"].default_value = 1.0
        return one.outputs[0]

    try:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
    except Exception:
        geo = nt.nodes.new("ShaderNodeGeometry")
    geo.name = "CAUSTIC_dir_geo"

    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    comb.name = "CAUSTIC_dir_L"
    comb.inputs["X"].default_value = float(sun_L[0])
    comb.inputs["Y"].default_value = float(sun_L[1])
    comb.inputs["Z"].default_value = float(sun_L[2])

    nrm = _vmath(nt, "NORMALIZE", geo.outputs["Normal"], name="CAUSTIC_dir_N")
    # Geometry Incoming already points from the surface toward the camera
    # (measured: it equals origin->camera), so the view vector is just its
    # normalisation — no sign flip.
    view = _vmath(nt, "NORMALIZE", geo.outputs["Incoming"],
                  name="CAUSTIC_dir_V")
    hsum = _vmath(nt, "ADD", comb.outputs[0], view.outputs[0],
                  name="CAUSTIC_dir_LplusV")
    half = _vmath(nt, "NORMALIZE", hsum.outputs[0], name="CAUSTIC_dir_H")

    ndl = _vmath(nt, "DOT_PRODUCT", nrm.outputs[0], comb.outputs[0],
                 name="CAUSTIC_dir_NdotL")
    ndv = _vmath(nt, "DOT_PRODUCT", nrm.outputs[0], view.outputs[0],
                 name="CAUSTIC_dir_NdotV")
    ndh = _vmath(nt, "DOT_PRODUCT", nrm.outputs[0], half.outputs[0],
                 name="CAUSTIC_dir_NdotH")
    vdh = _vmath(nt, "DOT_PRODUCT", view.outputs[0], half.outputs[0],
                 name="CAUSTIC_dir_VdotH")
    nL = _math(nt, "MAXIMUM", ndl.outputs[1], 1e-3, name="CAUSTIC_dir_cNL").outputs[0]
    nV = _math(nt, "MAXIMUM", ndv.outputs[1], 1e-3, name="CAUSTIC_dir_cNV").outputs[0]
    nH = _math(nt, "MINIMUM", _math(
        nt, "MAXIMUM", ndh.outputs[1], 0.0,
        name="CAUSTIC_dir_cNH0").outputs[0], 1.0,
        name="CAUSTIC_dir_cNH").outputs[0]
    vH = _math(nt, "MINIMUM", _math(
        nt, "MAXIMUM", vdh.outputs[1], 0.0,
        name="CAUSTIC_dir_cVH0").outputs[0], 1.0,
        name="CAUSTIC_dir_cVH").outputs[0]

    alpha = _math(nt, "MAXIMUM", _math(
        nt, "POWER", rough, 2.0,
        name="CAUSTIC_dir_r2").outputs[0], 1e-3,
        name="CAUSTIC_dir_alpha").outputs[0]
    a2 = _math(nt, "MULTIPLY", alpha, alpha, name="CAUSTIC_dir_a2").outputs[0]
    nH2 = _math(nt, "MULTIPLY", nH, nH, name="CAUSTIC_dir_nH2").outputs[0]
    a2m1 = _math(nt, "ADD", a2, -1.0, name="CAUSTIC_dir_a2m1").outputs[0]
    inner = _math(nt, "ADD", _math(
        nt, "MULTIPLY", nH2, a2m1,
        name="CAUSTIC_dir_in0").outputs[0], 1.0,
        name="CAUSTIC_dir_inner").outputs[0]
    # Floor guards denormals only: inner >= a2 >= 1e-3^2 always, so the real
    # denom never drops below pi*1e-12. A larger floor would crush the GGX
    # peak itself (the peak IS a ~1e-10 denom) and silently cap gloss.
    denom = _math(nt, "MAXIMUM", _math(
        nt, "MULTIPLY", pi, _math(
            nt, "POWER", inner, 2.0,
            name="CAUSTIC_dir_in2").outputs[0],
        name="CAUSTIC_dir_pii").outputs[0], 1e-20,
        name="CAUSTIC_dir_den").outputs[0]
    D = _math(nt, "DIVIDE", a2, denom, name="CAUSTIC_dir_D").outputs[0]

    om = _math(nt, "SUBTRACT", 1.0, vH, name="CAUSTIC_dir_om").outputs[0]
    om5 = _math(nt, "POWER", om, 5.0, name="CAUSTIC_dir_om5").outputs[0]
    F = _math(nt, "ADD", f0, _math(
        nt, "MULTIPLY", 1.0 - f0, om5,
        name="CAUSTIC_dir_F1").outputs[0],
        name="CAUSTIC_dir_F").outputs[0]

    k = _math(nt, "DIVIDE", alpha, 2.0, name="CAUSTIC_dir_k").outputs[0]
    omk = _math(nt, "SUBTRACT", 1.0, k, name="CAUSTIC_dir_omk").outputs[0]
    gL = _math(nt, "DIVIDE", nL, _math(
        nt, "ADD", _math(nt, "MULTIPLY", nL, omk,
                        name="CAUSTIC_dir_gL0").outputs[0], k,
        name="CAUSTIC_dir_gL1").outputs[0],
        name="CAUSTIC_dir_GL").outputs[0]
    gV = _math(nt, "DIVIDE", nV, _math(
        nt, "ADD", _math(nt, "MULTIPLY", nV, omk,
                        name="CAUSTIC_dir_gV0").outputs[0], k,
        name="CAUSTIC_dir_gV1").outputs[0],
        name="CAUSTIC_dir_GV").outputs[0]
    G = _math(nt, "MULTIPLY", gL, gV, name="CAUSTIC_dir_G").outputs[0]

    fs = _math(nt, "DIVIDE", _math(
        nt, "MULTIPLY", _math(nt, "MULTIPLY", D, F,
                             name="CAUSTIC_dir_DF").outputs[0], G,
        name="CAUSTIC_dir_DFG").outputs[0], _math(
        nt, "MAXIMUM", _math(
            nt, "MULTIPLY", 4.0, _math(nt, "MULTIPLY", nV, nL,
                                      name="CAUSTIC_dir_NVNL").outputs[0],
            name="CAUSTIC_dir_4NVNL").outputs[0], 1e-6,
        name="CAUSTIC_dir_fden").outputs[0],
        name="CAUSTIC_dir_fs").outputs[0]

    outs = []
    for ax, cc in zip(("X", "Y", "Z"), a):
        gain_c = pi / cc
        m = _math(nt, "MULTIPLY", fs, gain_c,
                 name=f"CAUSTIC_dir_g{ax}").outputs[0]
        outs.append(_math(nt, "ADD", 1.0, m,
                         name=f"CAUSTIC_dir_f{ax}").outputs[0])
    fac = nt.nodes.new("ShaderNodeCombineXYZ")
    fac.name = "CAUSTIC_dir_factor"
    for ax, s in zip(("X", "Y", "Z"), outs):
        nt.links.new(s, fac.inputs[ax])
    return fac.outputs[0]


def _mix_multiply(nt, a_socket, b_value, label):
    """Multiply a colour by a constant, compatible across Blender versions."""
    try:  # Blender 3.4+ unified Mix node: 0=Factor, 6=A, 7=B
        n = nt.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = "MULTIPLY"
        n.inputs[0].default_value = 1.0
        nt.links.new(a_socket, n.inputs[6])
        n.inputs[7].default_value = b_value
        out = n.outputs[2]
    except Exception:  # legacy
        n = nt.nodes.new("ShaderNodeMixRGB")
        n.blend_type = "MULTIPLY"
        n.inputs["Fac"].default_value = 1.0
        nt.links.new(a_socket, n.inputs["Color1"])
        n.inputs["Color2"].default_value = b_value
        out = n.outputs["Color"]
    n.label = label
    return n, out


def _emit_into_material(mat, image, gain, frame_uv=(0.0, 0.0, 1.0, 1.0),
                        directional=False, sun_L=None):
    """Image (Non-Color) -> x64 -> x gain [x directional factor] -> Emission.

    frame_uv (u0, v0, du, dv) places the baked patch inside the target's UVs:
    the bake may cover only the fan-framed sub-rect of the receiver, so the
    UV is rescaled by 1/(du, dv) and offset by -(u0, v0)/(du, dv) before it
    reaches the texture. Identity (0, 0, 1, 1) leaves the UVs untouched.
    Two explicit vector-math nodes rather than one Mapping node, because the
    node's Scale/Location order is version-dependent and this must be exact.

    With directional=True the field is additionally multiplied by the
    per-channel factor 1 + (pi/a)*f_s from _directional_factor (GGX for the
    sun direction), so a glossy receiver answers the caustic at the right
    reflection angles. A Lambertian receiver (F0 = 0) yields exactly 1.
    """
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    for n in list(nt.nodes):  # replace any previous injection
        if n.name.startswith("CAUSTIC_"):
            nt.nodes.remove(n)
    for l in list(nt.links):
        if l.from_node.name.startswith("CAUSTIC_") or l.to_node.name.startswith("CAUSTIC_"):
            nt.links.remove(l)

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "CAUSTIC_img"
    tex.image = image
    tex.interpolation = "Cubic"  # smooths coarse-bake texels; detail still needs bake res
    tex.extension = "EXTEND"
    if image is not None:
        # the baked field is linear, not sRGB: 16-bit PNG scaled by 1/64
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    tex.location = (-900, -300)

    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.name = "CAUSTIC_uv"
    uv.location = (-1100, -300)
    u0, v0, du, dv = (float(v) for v in frame_uv)
    if (u0, v0, du, dv) == (0.0, 0.0, 1.0, 1.0):
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    else:
        if not (1e-9 < du and 1e-9 < dv):
            raise ValueError("frame_uv degenerate: cannot place the bake")
        mul = nt.nodes.new("ShaderNodeVectorMath")
        mul.name = "CAUSTIC_map_mul"
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = (1.0 / du, 1.0 / dv, 1.0)
        mul.location = (-1000, -300)
        add = nt.nodes.new("ShaderNodeVectorMath")
        add.name = "CAUSTIC_map_add"
        add.operation = "ADD"
        add.inputs[1].default_value = (-u0 / du, -v0 / dv, 0.0)
        add.location = (-950, -300)
        nt.links.new(uv.outputs["UV"], mul.inputs[0])
        nt.links.new(mul.outputs["Vector"], add.inputs[0])
        nt.links.new(add.outputs["Vector"], tex.inputs["Vector"])

    scale, s_out = _mix_multiply(nt, tex.outputs["Color"], (64.0,) * 3 + (1.0,),
                                 "CAUSTIC_x64")
    scale.name = "CAUSTIC_x64"
    scale.location = (-650, -300)
    gm, g_out = _mix_multiply(nt, s_out, (gain,) * 3 + (1.0,), "CAUSTIC_gain")
    gm.name = "CAUSTIC_gain"
    gm.location = (-450, -300)

    if directional:
        _bc = bsdf.inputs["Base Color"].default_value
        alb = (float(_bc[0]), float(_bc[1]), float(_bc[2]))
        rough = 1.0
        spec = 0.5
        try:
            rough = float(bsdf.inputs["Roughness"].default_value)
            spec_in = bsdf.inputs.get("Specular IOR Level")
            if spec_in is not None:
                spec = float(spec_in.default_value)
        except Exception:
            pass
        if sun_L is None:
            sun_L = (0.0, 0.0, 1.0)
        f_out = _directional_factor(nt, tuple(sun_L), alb, rough, spec)
        dm = nt.nodes.new("ShaderNodeMix")
        try:
            dm.data_type = "RGBA"
            dm.blend_type = "MULTIPLY"
            dm.inputs[0].default_value = 1.0
            nt.links.new(g_out, dm.inputs[6])
            nt.links.new(f_out, dm.inputs[7])
            dir_out = dm.outputs[2]
        except Exception:
            dm = nt.nodes.new("ShaderNodeMixRGB")
            dm.blend_type = "MULTIPLY"
            dm.inputs["Fac"].default_value = 1.0
            nt.links.new(g_out, dm.inputs["Color1"])
            nt.links.new(f_out, dm.inputs["Color2"])
            dir_out = dm.outputs["Color"]
        dm.name = "CAUSTIC_dir_apply"
        dm.label = "CAUSTIC_dir_apply"
        dm.location = (-350, -300)
        g_out = dir_out

    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "CAUSTIC_emission"
    em.inputs["Strength"].default_value = 1.0
    em.location = (-200, -300)
    nt.links.new(g_out, em.inputs["Color"])

    add = nt.nodes.new("ShaderNodeAddShader")
    add.name = "CAUSTIC_add"
    add.location = (0, -200)
    nt.links.new(em.outputs["Emission"], add.inputs[0])
    nt.links.new(bsdf.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return True


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------
class CAUSTIC_OT_bake(bpy.types.Operator):
    """Bake the wave-corrected caustic with the solver"""
    bl_idname = "caustic.bake"
    bl_label = "Bake caustic"

    def execute(self, context):
        p = context.scene.caustic
        if not os.path.exists(p.solver):
            self.report({"ERROR"}, f"solver not found: {p.solver}")
            return {"CANCELLED"}
        os.makedirs(TMP_DIR, exist_ok=True)
        out = os.path.join(TMP_DIR, "caustic.png")
        cmd = [p.solver,
               "--res", str(p.resolution),
               "--airy", str(p.airy_scale),
               "--n", "400", "--ssaa", "1",
               "--out", os.path.join(TMP_DIR, "throwaway.png"),
               "--dump-caustic", out]
        if p.wave_amp <= 0.0:
            cmd.append("--flat")
        # A non-zero coefficient tints the BAKED CAUSTIC. The caustic is a
        # light-side quantity: its colour is set by what the sunlight crossed
        # before landing, so the bake is the only stage that can tint it.
        if any(v > 0.0 for v in p.glass_absorb):
            cmd += ["--glass-abs", ",".join("%.6g" % v for v in p.glass_absorb)]
        if any(v > 0.0 for v in p.water_absorb):
            cmd += ["--water-abs", ",".join("%.6g" % v for v in p.water_absorb)]
        t0 = time.time()
        try:
            rc, log = _run_hidden(cmd)
        except subprocess.TimeoutExpired:
            self.report({"ERROR"}, "solver timed out")
            return {"CANCELLED"}
        p.last_ms = (time.time() - t0) * 1000.0
        if rc != 0 or not os.path.exists(out):
            self.report({"ERROR"}, f"solver failed (rc={rc})")
            for line in log.splitlines()[-3:]:
                print("   ", line)
            return {"CANCELLED"}
        img = bpy.data.images.load(out, check_existing=False)
        img.name = "CAUSTIC_bake"
        p.image_path = out
        # the solver bakes the whole receiver; clear any framed placement
        p.frame_uv = (0.0, 0.0, 1.0, 1.0)
        p.frame_rect = (0.0, 0.0, 0.0)
        metrics = [l for l in log.splitlines() if l.startswith("[caustic]")]
        p.status = metrics[0].strip() if metrics else "baked"
        for line in metrics:
            print("[solver]", line.strip())
        self.report({"INFO"}, f"baked in {p.last_ms:.0f} ms")
        return {"FINISHED"}


class CAUSTIC_OT_inject(bpy.types.Operator):
    """Inject the baked caustic into the target object's material"""
    bl_idname = "caustic.inject"
    bl_label = "Inject into material"

    def execute(self, context):
        p = context.scene.caustic
        obj = p.target or context.active_object
        if obj is None:
            self.report({"ERROR"}, "no target object")
            return {"CANCELLED"}
        img = bpy.data.images.get("CAUSTIC_bake")
        if img is None:
            self.report({"ERROR"}, "bake first")
            return {"CANCELLED"}
        if p.inject_mode == "LIGHT_CARD":
            return self._inject_light_card(context, obj, img)
        if not obj.data.materials:
            obj.data.materials.append(bpy.data.materials.new("caustic_receiver"))
        ok = 0
        sun_L = _sun_light_dir(context.scene, tuple(p.sun_dir))
        for mat in obj.data.materials:
            if _emit_into_material(mat, img, p.gain, tuple(p.frame_uv),
                                   directional=bool(p.directional),
                                   sun_L=sun_L):
                ok += 1
        if p.disable_cycles_caustics and context.scene.render.engine == "CYCLES":
            context.scene.cycles.caustics_refractive = False
            context.scene.cycles.caustics_reflective = False
        self.report({"INFO"}, f"injected into {ok} material slot(s)")
        return {"FINISHED"}

    @staticmethod
    def _card_object(context, corners):
        """Create or reuse the CAUSTIC_card plane from 4 world corners."""
        card = bpy.data.objects.get("CAUSTIC_card")
        if card is None:
            me = bpy.data.meshes.new("CAUSTIC_card")
            card = bpy.data.objects.new("CAUSTIC_card", me)
            context.scene.collection.objects.link(card)
        else:
            me = card.data
        me.clear_geometry()
        me.from_pydata(corners, [], [(0, 1, 2), (0, 2, 3)])
        me.update()
        if not me.uv_layers:
            me.uv_layers.new(name="UVMap")
        uvl = me.uv_layers[0].data
        # one UV per corner, indexed by vertex: the mesh has two triangles, so
        # six loops and writing uvl[0:4] would leave the second triangle with
        # default UVs (the field folds across it).
        corner_uv = {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (1.0, 1.0), 3: (0.0, 1.0)}
        for loop in me.loops:
            uvl[loop.index].uv = corner_uv[loop.vertex_index]
        return card

    def _inject_light_card(self, context, obj, img):
        """Transport injection: an emissive card above the receiver that is
        invisible to camera rays. The table's BSDF shades the caustic (cosine
        falloff) and the glass receives it from below, instead of the field
        being pasted onto the table as surface emission."""
        import numpy as np
        p = context.scene.caustic
        # the card replaces the surface emission
        for mat in (obj.data.materials if obj else []):
            if not mat or not mat.use_nodes:
                continue
            nt = mat.node_tree
            for node in list(nt.nodes):
                if node.name.startswith("CAUSTIC_"):
                    nt.nodes.remove(node)
            for link in list(nt.links):
                if (link.from_node.name.startswith("CAUSTIC_")
                        or link.to_node.name.startswith("CAUSTIC_")):
                    nt.links.remove(link)
        cx, cy, half = tuple(p.frame_rect)
        if half <= 0.0:
            ws = [obj.matrix_world @ v.co for v in obj.data.vertices]
            xs = [v.x for v in ws]
            ys = [v.y for v in ws]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
        zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
        z = sum(zs) / len(zs) + 0.0005
        corners = [(cx - half, cy - half, z), (cx + half, cy - half, z),
                   (cx + half, cy + half, z), (cx - half, cy + half, z)]
        card = self._card_object(context, corners)
        card.data.materials.clear()
        mat = bpy.data.materials.new("CAUSTIC_card")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = "CAUSTIC_img"
        tex.image = img
        tex.interpolation = "Cubic"
        tex.extension = "EXTEND"
        try:
            img.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mul, m_out = _mix_multiply(nt, tex.outputs["Color"],
                                   (64.0,) * 3 + (1.0,), "CAUSTIC_x64")
        alb = _receiver_albedo(obj)
        gain_rgb = tuple(p.gain / max(a, 0.02) for a in alb)
        gm, g_out = _mix_multiply(nt, m_out, gain_rgb + (1.0,),
                                  "CAUSTIC_gain")
        lp = nt.nodes.new("ShaderNodeLightPath")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(g_out, em.inputs["Color"])
        # Is Camera Ray = 1 on camera rays -> Transparent; everything else emits
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(em.outputs["Emission"], mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        card.data.materials.append(mat)
        card.visible_shadow = False
        card.visible_camera = False
        self.report({"INFO"}, "injected as a light card")
        return {"FINISHED"}


class CAUSTIC_OT_remove(bpy.types.Operator):
    """Remove the injected caustic from the target's material"""
    bl_idname = "caustic.remove"
    bl_label = "Remove injection"

    def execute(self, context):
        p = context.scene.caustic
        obj = p.target or context.active_object
        n = 0
        for mat in (obj.data.materials if obj else []):
            if not mat or not mat.use_nodes:
                continue
            nt = mat.node_tree
            for node in list(nt.nodes):
                if node.name.startswith("CAUSTIC_"):
                    nt.nodes.remove(node)
                    n += 1
        card = bpy.data.objects.get("CAUSTIC_card")
        if card is not None:
            bpy.data.objects.remove(card, do_unlink=True)
            n += 1
        self.report({"INFO"}, f"removed {n} injection node(s)")
        return {"FINISHED"}


class CAUSTIC_OT_tint_medium(bpy.types.Operator):
    """Give an object's materials Beer-Lambert absorption (a coloured medium)"""
    bl_idname = "caustic.tint_medium"
    bl_label = "Tint this object's medium"

    def execute(self, context):
        p = context.scene.caustic
        obj = p.medium_objects or context.active_object
        if obj is None:
            self.report({"ERROR"}, "no object selected")
            return {"CANCELLED"}
        mu = tuple(p.glass_absorb)
        n = 0
        for mat in obj.data.materials:
            if mat and mat.use_nodes and _absorb_into_material(mat, mu):
                n += 1
        # The setting that silently defeats all of the above. Cycles defaults
        # scene.cycles.volume_bounces to 0, and at 0 it IGNORES a connected volume
        # shader completely: the absorption is in the material, is never
        # integrated, and the medium renders colourless with no warning anywhere.
        # Four isolation renders came back pixel-identical before this was found.
        if context.scene.render.engine == "CYCLES":
            if context.scene.cycles.volume_bounces < 1:
                context.scene.cycles.volume_bounces = 8
        p.volumes_on = True
        self.report({"INFO"}, "tinted %d material(s); volume bounces = %d"
                    % (n, context.scene.cycles.volume_bounces
                       if context.scene.render.engine == "CYCLES" else 0))
        return {"FINISHED"}


class CAUSTIC_OT_untint_medium(bpy.types.Operator):
    """Remove the volume tint from an object's materials"""
    bl_idname = "caustic.untint_medium"
    bl_label = "Remove medium tint"

    def execute(self, context):
        p = context.scene.caustic
        obj = p.medium_objects or context.active_object
        n = 0
        for mat in (obj.data.materials if obj else []):
            if not mat or not mat.use_nodes:
                continue
            nt = mat.node_tree
            for node in list(nt.nodes):
                if node.name.startswith("MEDIUM_"):
                    nt.nodes.remove(node)
                    n += 1
            # A NodeSocketShader has no default_value -- assign to it and Blender
            # raises. Removing the LINK is what clears a volume socket.
            out = nt.nodes.get("Material Output")
            if out is not None and out.inputs["Volume"].is_linked:
                for lk in list(out.inputs["Volume"].links):
                    nt.links.remove(lk)
        p.volumes_on = False
        self.report({"INFO"}, f"removed {n} volume node(s)")
        return {"FINISHED"}


class CAUSTIC_OT_caustics_off(bpy.types.Operator):
    """Toggle Cycles' own caustics on/off"""
    bl_idname = "caustic.cycles_toggle"
    bl_label = "Toggle Cycles caustics"

    def execute(self, context):
        c = context.scene.cycles
        c.caustics_refractive = not c.caustics_refractive
        return {"FINISHED"}


class CAUSTIC_OT_bake_mesh(bpy.types.Operator):
    """Bake the wave-corrected caustic for any closed mesh (in-addon tracer)"""
    bl_idname = "caustic.bake_mesh"
    bl_label = "Bake mesh caustic"

    def execute(self, context):
        import traceback
        try:
            return self._execute(context)
        except Exception as e:  # noqa: BLE001 — a button must never crash Blender
            traceback.print_exc()
            try:
                context.scene.caustic.status = f"error: {e}"
            except Exception:
                pass
            self.report({"ERROR"}, f"error: {e}")
            return {"CANCELLED"}

class CAUSTIC_OT_bake_mesh(bpy.types.Operator):
    """Bake the wave-corrected caustic for any closed mesh (in-addon tracer)"""
    bl_idname = "caustic.bake_mesh"
    bl_label = "Bake mesh caustic"

    def execute(self, context):
        import traceback
        try:
            return self._execute(context)
        except Exception as e:  # noqa: BLE001 — a button must never crash Blender
            traceback.print_exc()
            try:
                context.scene.caustic.status = f"error: {e}"
            except Exception:
                pass
            self.report({"ERROR"}, f"error: {e}")
            return {"CANCELLED"}

    def _execute(self, context):
        import numpy as np
        p = context.scene.caustic
        obj = p.mesh_object or (context.active_object
                               if context.active_object and context.active_object.type == "MESH"
                               else None)
        if obj is None or obj.type != "MESH":
            p.status = "no mesh object: set Mesh object"
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        sys.path.insert(0, os.path.join(_ROOT, "tools"))
        from mesh_caustic import trace as MT
        from mesh_caustic import band as MB
        dg = context.evaluated_depsgraph_get()
        verts, faces, tri_normals = _mesh_tris(obj, dg)
        tris_n = len(faces)
        est = MT.estimate_seconds(tris_n, p.mesh_resolution
                                  * max(int(p.mesh_ray_mult), 1), nchan=3,
                                  accel=p.mesh_accel.lower())
        try:
            MT.check_closed(faces)
            recv = _resolve_target(p.target)
            mat = _resolve_material(obj)
            lights = _collect_lights(context.scene.objects, tuple(p.sun_dir))
            absorb = mat["absorb"] if mat["absorb"] is not None else tuple(p.glass_absorb)
            eta = (float(mat["ior"]) if p.mesh_achromatic
                   else MT.ior_rgb(mat["ior"]))
            phys = {}
            if p.mesh_physical_exposure:
                sun_e = next((float(L["energy"]) for L in lights
                              if L.get("type") == "sun"
                              and L.get("energy")), 0.0)
                if sun_e <= 0.0:
                    raise ValueError(
                        "physical exposure needs a SUN lamp with energy")
                phys = dict(physical=True, sun_irradiance=sun_e,
                            albedo=_target_albedo(p.target))
            fld, res, rect = _bake_field(MT, MB, verts, faces, lights, recv,
                                         p.mesh_resolution, p.mesh_airy,
                                         absorb, eta,
                                         ray_mult=p.mesh_ray_mult,
                                         frame=p.mesh_frame,
                                         frame_margin=p.mesh_frame_margin,
                                         accel=p.mesh_accel.lower(),
                                         tri_normals=tri_normals, **phys)
            frame_uv = ((0.0, 0.0, 1.0, 1.0) if rect is None
                        else _uv_rect_for_world_rect(p.target, rect))
        except ValueError as e:
            p.status = str(e)
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        if rect is None:
            p.frame_uv = (0.0, 0.0, 1.0, 1.0)
            p.frame_rect = (0.0, 0.0, 0.0)
        else:
            p.frame_uv = frame_uv
            p.frame_rect = tuple(rect)
        os.makedirs(TMP_DIR, exist_ok=True)
        out = os.path.join(TMP_DIR, "caustic_mesh.png")
        t0 = time.time()
        img = _write_bake_image(fld, out)
        dt = time.time() - t0
        p.image_path = out
        p.last_ms = dt * 1000.0
        frame_txt = ""
        if rect is not None:
            mpp = 2.0 * rect[2] / p.mesh_resolution
            frame_txt = (f" frame {2 * rect[2]:.2f}m texel "
                         f"{mpp * 1000:.1f}mm")
        blur_txt = ""
        if res.get("sun_blur_m", 0.0) > 0.0:
            blur_txt = f" sunblur {res['sun_blur_m'] * 1000:.1f}mm"
        airy_txt = ""
        if not res.get("airy_resolved", True):
            airy_txt = " airy sub-texel (geometric)"
        p.status = (f"[mesh] {tris_n} tris res {p.mesh_resolution} "
                    f"est {est:.0f}s took {dt:.0f}s peak 1.00 "
                    f"hits {len(res['hits'])}{frame_txt}{blur_txt}{airy_txt}")
        print("   ", p.status)
        self.report({"INFO"}, f"mesh baked in {dt:.0f} s (est {est:.0f} s)")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# mesh bake shared core (single + sequence operators)
# ---------------------------------------------------------------------------
def _mesh_tris(obj, dg):
    """Evaluated-mesh triangles as (verts, faces, corner_normals).

    verts: (N,3) float64; faces: (M,3) int64 fan-triangulated from polygons;
    corner_normals: (M,3,3) the evaluated mesh's shading normals per triangle
    corner, so the tracer refracts off the smooth surface rather than each
    facet. Normals are object-space, matching the local verts (callers use a
    mesh at the scene origin; see the addon's bake contract)."""
    import numpy as np
    ev = obj.evaluated_get(dg).to_mesh()
    try:
        verts = np.empty(len(ev.vertices) * 3)
        ev.vertices.foreach_get("co", verts)
        verts = verts.reshape(-1, 3)
        tris = []
        norms = []
        corner = ev.corner_normals
        for poly in ev.polygons:
            vs = tuple(poly.vertices)
            ls = poly.loop_start
            for i in range(1, len(vs) - 1):
                tris.append((vs[0], vs[i], vs[i + 1]))
                norms.append((tuple(corner[ls].vector),
                              tuple(corner[ls + i].vector),
                              tuple(corner[ls + i + 1].vector)))
        return verts, np.asarray(tris, dtype=np.int64), np.asarray(norms, dtype=float)
    finally:
        obj.evaluated_get(dg).to_mesh_clear()


def _resolve_target(tgt):
    """Receiver contract. Returns dict(cx, cy, half, rz) or raises ValueError
    with the named refusal."""
    if tgt is None or tgt.type != "MESH" or not tgt.data.uv_layers:
        raise ValueError("no usable UVs: target needs a UV map spanning 0-1")
    alluv = [(l.uv[0], l.uv[1]) for l in tgt.data.uv_layers[0].data]
    minu = min(u for u, v in alluv)
    maxu = max(u for u, v in alluv)
    minv = min(v for u, v in alluv)
    maxv = max(v for u, v in alluv)
    if not (minu <= 0.05 and maxu >= 0.95 and minv <= 0.05 and maxv >= 0.95):
        raise ValueError("no usable UVs: target UVs must span 0-1")
    ws = [tgt.matrix_world @ v.co for v in tgt.data.vertices]
    xs = [v.x for v in ws]
    ys = [v.y for v in ws]
    zs = [v.z for v in ws]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    return {"cx": cx, "cy": cy, "half": half, "z": sum(zs) / len(zs)}


def _target_albedo(tgt):
    """Per-channel diffuse albedo of the receiver, for physical exposure."""
    for mat in (tgt.data.materials if tgt else []):
        if not mat or not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED" and "Base Color" in n.inputs:
                return tuple(float(v) for v in n.inputs["Base Color"].default_value[:3])
            if n.type == "BSDF_DIFFUSE" and "Color" in n.inputs:
                return tuple(float(v) for v in n.inputs["Color"].default_value[:3])
    return (0.8, 0.8, 0.8)


def _uv_rect_for_world_rect(tgt, rect):
    """UV sub-rect (u0, v0, du, dv) covered by a world xy rect, from the
    target's OWN loop-vertex world->UV affine fit.

    Never assumes UVs stretch 0-1 over the world extent: the fit is what the
    inject maps the framed bake through, so a square patch over a non-square
    plane is placed by measurement, not by assumption. Raises ValueError when
    the target's UVs are not an affine map of world xy (rotated/unwrapped
    targets cannot host a framed bake)."""
    import numpy as np
    uv = tgt.data.uv_layers[0]
    P, U = [], []
    for i, loop in enumerate(uv.data):
        v = tgt.data.vertices[tgt.data.loops[i].vertex_index]
        w = tgt.matrix_world @ v.co
        P.append((w.x, w.y))
        U.append((loop.uv[0], loop.uv[1]))
    P = np.asarray(P, dtype=float)
    U = np.asarray(U, dtype=float)
    A = np.column_stack([P[:, 0], P[:, 1], np.ones(len(P))])
    cu, *_ = np.linalg.lstsq(A, U[:, 0], rcond=None)
    cv, *_ = np.linalg.lstsq(A, U[:, 1], rcond=None)
    resid = float(np.abs(A @ cu - U[:, 0]).max()
                  + np.abs(A @ cv - U[:, 1]).max())
    if resid > 1e-3:
        raise ValueError(f"target UVs are not an affine map of world xy "
                         f"(residual {resid:.4f}); cannot place a framed bake")
    cx, cy, half = rect
    corners = [(cx - half, cy - half), (cx + half, cy - half),
               (cx + half, cy + half), (cx - half, cy + half)]
    us = [cu[0] * x + cu[1] * y + cu[2] for x, y in corners]
    vs = [cv[0] * x + cv[1] * y + cv[2] for x, y in corners]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs), max(vs)
    if not (1e-6 < u1 - u0 and 1e-6 < v1 - v0):
        raise ValueError("framed patch degenerate in UV space")
    return (float(u0), float(v0), float(u1 - u0), float(v1 - v0))


def _collect_lights(objects, sun_dir):
    """Scene lamps as tracer dicts; the fallback sun when the scene has none."""
    from mathutils import Vector
    import math
    lights = []
    for o in objects:
        if o.type != "LIGHT":
            continue
        d = o.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        lt = o.data.type
        if lt == "SUN":
            lights.append({"type": "sun", "direction": tuple(d),
                           "angle_deg": math.degrees(float(o.data.angle)),
                           "energy": float(o.data.energy)})
        elif lt == "POINT":
            lights.append({"type": "point", "position": tuple(o.matrix_world.translation)})
        elif lt == "SPOT":
            lights.append({"type": "spot", "position": tuple(o.matrix_world.translation),
                           "direction": tuple(d),
                           "angle_deg": math.degrees(o.data.spot_size)})
        elif lt == "AREA":
            lights.append({"type": "area", "position": tuple(o.matrix_world.translation),
                           "normal": tuple(d), "size": float(o.data.size), "samples": 3})
    if not lights:
        lights = [{"type": "sun", "direction": tuple(sun_dir)}]
    return lights


def _resolve_material(obj):
    """Read the renderable glass material: first transmissive slot, else active.

    Returns dict(ior, roughness, absorb_or_None, tint). Volume Absorption on
    the material's Volume socket becomes per-channel Beer-Lambert mu; without
    one the caller supplies panel fallback coefficients. Raises ValueError
    with a named refusal when nothing transmissive exists or roughness kills
    the fold the correction is defined on."""
    mats = [s.material for s in obj.material_slots if s.material and s.material.use_nodes]
    if not mats and obj.active_material and obj.active_material.use_nodes:
        mats = [obj.active_material]
    if not mats:
        raise ValueError("no usable material: mesh needs a node material")
    pick = None
    for m in mats:
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None and "Transmission Weight" in bsdf.inputs:
            try:
                if float(bsdf.inputs["Transmission Weight"].default_value) > 0.01:
                    pick, bsdf_pick = m, bsdf
                    break
            except (TypeError, ValueError):
                continue
    if pick is None:
        raise ValueError("no transmissive material: give the mesh a Principled BSDF with Transmission Weight > 0")
    rough = float(bsdf_pick.inputs["Roughness"].default_value) if "Roughness" in bsdf_pick.inputs else 0.0
    if rough > 0.05:
        raise ValueError(f"rough glass unsupported: roughness {rough:.2f} has no sharp fold to correct (use 0.00-0.05)")
    ior = float(bsdf_pick.inputs["IOR"].default_value) if "IOR" in bsdf_pick.inputs else 1.525
    tint = tuple(float(v) for v in bsdf_pick.inputs["Base Color"].default_value[:3]) if "Base Color" in bsdf_pick.inputs else (1.0, 1.0, 1.0)
    absorb = None
    out = bsdf_pick.id_data.nodes.get("Material Output")
    if out is not None and out.inputs["Volume"].is_linked:
        node = out.inputs["Volume"].links[0].from_node
        seen = set()
        while node is not None and node.name not in seen:
            seen.add(node.name)
            if node.type == "VOLUME_ABSORPTION":
                d = max(float(node.inputs["Density"].default_value), 0.0)
                col = tuple(float(v) for v in node.inputs["Color"].default_value[:3])
                if d > 0.0:
                    absorb = tuple(d * (1.0 - c) for c in col)
                break
            if not node.inputs:
                break
            linked = [l for i in node.inputs for l in i.links]
            node = linked[0].from_node if linked else None
    return {"ior": ior, "roughness": rough, "absorb": absorb, "tint": tint}


def _build_bvh(verts, faces):
    """Build Blender's C++ BVHTree over the evaluated mesh triangles."""
    from mathutils.bvhtree import BVHTree
    return BVHTree.FromPolygons([tuple(v) for v in verts],
                                [tuple(int(i) for i in f) for f in faces])


def _disk_blur(img, radius_px):
    """Soften a field by the sun's angular PSF (Gaussian, sigma = R/2).

    A distant sun of angular diameter theta projects a disk of radius
    distance*tan(theta/2) on the receiver; a uniform disk is well approximated
    by a Gaussian of sigma = R/2. Separable and normalized, so the field's
    total energy is preserved. A delta-sun tracer resolves facet-scale
    structure the real sun blurs away; this is the missing penumbra.
    """
    import math
    import numpy as np
    sigma = max(float(radius_px) / 2.0, 1e-9)
    if sigma < 0.5:
        return img
    rad = int(math.ceil(3.0 * sigma))
    x = np.arange(-rad, rad + 1, dtype=float)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    out = np.apply_along_axis(
        lambda m: np.convolve(m, k, mode="same"), 0, img)
    out = np.apply_along_axis(
        lambda m: np.convolve(m, k, mode="same"), 1, out)
    return out


def _make_bvh_shooter(bvh, recv, geo, tri_normals=None):
    """Return shoot(o, d, eta_c) backed by a Blender BVHTree.

    The per-ray work leaves Python. geo = (A, E1, E2) gives the triangle
    vertices for barycentric shading-normal interpolation, so a smooth-shaded
    mesh refracts continuously instead of per facet (tri_normals, optional).
    """
    import numpy as _np
    from mesh_caustic import trace as _MT

    A, E1, E2 = geo
    rz = float(recv["z"])
    ph = float(recv["half"])
    cx = float(recv["cx"])
    cy = float(recv["cy"])

    def shoot(o, d, eta_c):
        loc, nor, idx, dist = bvh.ray_cast(tuple(o), tuple(d))
        if loc is None:
            return None
        idx = int(idx)
        p = _np.asarray(loc, dtype=float)
        if tri_normals is not None:
            n = _MT._smooth_normal(p, idx, A, E1, E2, tri_normals)
        else:
            n = _np.asarray(nor, dtype=float)
            nn = _np.linalg.norm(n)
            if nn > 0.0:
                n = n / nn
        if float(n @ d) > 0.0:
            n = -n
        t = _MT._refract(d, n, 1.0 / eta_c)
        if t is None:
            return None
        p2 = p + t * 1e-6
        loc2, nor2, idx2, dist2 = bvh.ray_cast(tuple(p2), tuple(t))
        # BVHTree cannot skip the entry triangle by index; nudge past it
        for _ in range(3):
            if loc2 is not None and int(idx2) != idx:
                break
            p2 = p2 + t * 1e-5
            loc2, nor2, idx2, dist2 = bvh.ray_cast(tuple(p2), tuple(t))
        if loc2 is None or int(idx2) == idx:
            return None
        idx2 = int(idx2)
        q0 = _np.asarray(loc2, dtype=float)
        if tri_normals is not None:
            n2 = _MT._smooth_normal(q0, idx2, A, E1, E2, tri_normals)
        else:
            n2 = _np.asarray(nor2, dtype=float)
            nn2 = _np.linalg.norm(n2)
            if nn2 > 0.0:
                n2 = n2 / nn2
        if float(n2 @ t) > 0.0:
            n2 = -n2
        t2 = _MT._refract(t, n2, eta_c)
        if t2 is None or abs(t2[2]) < 1e-9:
            return None
        L = float(_np.linalg.norm(q0 - p))
        s = (rz - q0[2]) / t2[2]
        if s <= 0.0:
            return None
        q = q0 + s * t2
        if abs(q[0] - cx) > ph or abs(q[1] - cy) > ph:
            return None
        return (float(q[0]), float(q[1]), L)

    return shoot


def _bake_field(MT, MB, verts, faces, lights, recv, res, airy, absorb, eta,
                ray_mult=1, frame="FULL", frame_margin=0.15, feather=0.35,
                accel="bvhtree", tri_normals=None, physical=False,
                sun_irradiance=0.0, albedo=(0.8, 0.8, 0.8)):
    """Trace + band-correct. Returns (fld01 RGB peak 1.0 row0=+Y, trace dict,
    frame rect or None for the full receiver).

    ray_mult supersamples rays above grid resolution so shot noise, not texel
    size, stops being the visible structure. frame='AUTO' first runs a cheap
    achromatic probe over the full receiver and re-bins the SAME rays into a
    fan-framed patch: the tracer launches rays over the mesh bounding sphere,
    so a smaller patch buys texel resolution and hits-per-texel for free.
    feather cross-fades the outer edge of the correction band to the raw
    field (display transition; 0 keeps the strictly conserved operator).
    eta is scalar or (R,G,B); absorb is per-channel. Raises ValueError from
    the tracer or the no-hits guard."""
    import numpy as _np
    n = res
    cx, cy, half, rz = recv["cx"], recv["cy"], recv["half"], recv["z"]
    verts = _np.asarray(verts, dtype=float)
    faces = _np.asarray(faces, dtype=_np.int64)
    geo = (verts[faces[:, 0]], verts[faces[:, 1]] - verts[faces[:, 0]],
           verts[faces[:, 2]] - verts[faces[:, 0]])
    bvh = _build_bvh(verts, faces) if accel == "bvhtree" else None
    rect = None
    if frame == "AUTO":
        eta_probe = float(_np.mean(_np.asarray(eta, dtype=float)))
        popts = {"n_side": 128, "eta": eta_probe}
        if bvh is not None:
            popts["shoot"] = _make_bvh_shooter(
                bvh, {"cx": cx, "cy": cy, "half": half, "z": rz}, geo,
                tri_normals)
        rp = MT.trace_mesh(verts, faces, lights,
                           {"z": rz, "patch_half": half, "center": (cx, cy)},
                           popts)
        cx, cy, half = MT.frame_patch(rp["hits"], recv, frame_margin)
        rect = (cx, cy, half)
    opts = {"n_side": n * max(int(ray_mult), 1), "eta": eta,
            "absorb_rgb": tuple(absorb), "tri_normals": tri_normals}
    if bvh is not None:
        opts["shoot"] = _make_bvh_shooter(
            bvh, {"cx": cx, "cy": cy, "half": half, "z": rz}, geo,
            tri_normals)
    r = MT.trace_mesh(verts, faces, lights,
                      {"z": rz, "patch_half": half, "center": (cx, cy)}, opts)
    r["accel"] = accel
    outs = []
    for c in range(3):
        m = (r["chan"] == c) if len(r["hits"]) else None
        hc = r["hits"][m] if m is not None else _np.zeros((0, 2))
        wc = r["weights"][m] if m is not None else None
        gc, _, _ = _np.histogram2d(
            hc[:, 0] if len(hc) else _np.zeros(0),
            hc[:, 1] if len(hc) else _np.zeros(0),
            bins=n, weights=wc,
            range=[[cx - half, cx + half], [cy - half, cy + half]])
        outs.append(gc.T)
    g = sum(outs) / 3.0
    if not (g > 0).any():
        raise ValueError("no receiver hits: mesh throws no light on the target")
    mpp = 2 * half / n
    # A fringe narrower than half a texel cannot be represented; redistributing
    # band flux by it would collapse the band onto the ridge (a spike, not a
    # fringe). In that regime the geometric field is the correct low-pass
    # limit, so the correction is skipped by design, not silently omitted.
    r["airy_resolved"] = bool(airy >= 0.5 * mpp)
    if r["airy_resolved"]:
        dist = MB.ridge_distance(g, mpp)
        band_m = max(0.004, 3 * mpp)
        chans = [MB.correct(gc, dist, band_m, airy, feather=feather)
                 for gc in outs]
    else:
        chans = outs
    # the sun is a disk, not a point: convolve the point-source caustic with
    # its angular projection. Without this the tracer keeps facet-scale
    # structure the real (and Cycles') sun blurs into a soft streak.
    sun_angle = next((float(L["angle_deg"]) for L in lights
                      if L.get("type") == "sun" and L.get("angle_deg")), 0.0)
    sun_blur_m = 0.0
    if sun_angle > 0.0:
        import math as _math
        dist_to_receiver = max(0.05, abs(rz - float(_np.mean(verts[:, 2]))))
        sun_blur_m = _math.tan(_math.radians(sun_angle) / 2.0) * dist_to_receiver
        rpx = sun_blur_m / mpp
        if rpx >= 0.5:
            chans = [_disk_blur(c, rpx) for c in chans]
    r["sun_angle_deg"] = sun_angle
    r["sun_blur_m"] = sun_blur_m
    if physical:
        # every ray carries E_sun * (launch cell area) of flux; the histogram
        # count is the energy per texel, so irradiance = energy / texel area
        # and a Lambertian receiver returns albedo/pi of it. No tuning scalar.
        lo = verts.min(axis=0) - 0.02
        hi = verts.max(axis=0) + 0.02
        launch = 0.5 * float(_np.linalg.norm(hi - lo)) + 0.01
        cell = (2.0 * launch / (n * max(int(ray_mult), 1))) ** 2
        scale = float(sun_irradiance) * cell / (mpp * mpp)
        fld = _np.stack([c * scale * float(albedo[i]) / _np.pi
                         for i, c in enumerate(chans)], axis=-1)
        peak = float(fld.max())
        if peak > 64.0:
            raise ValueError(
                f"physical field peak {peak:.2f} exceeds the 16-bit /16 "
                "storage; lower the sun energy or change the storage")
        return fld[::-1, :, :], r, rect  # row 0 = +Y, the solver dump convention
    peak = max(float(c.max()) for c in chans)
    fld = _np.stack([c / peak for c in chans], axis=-1)  # joint peak 1.0
    return fld[::-1, :, :], r, rect  # row 0 = +Y, the solver dump convention


def _write_bake_image(fld01, out):
    """Write peak-normalized RGB field via the stdlib PNG writer (solver
    convention: stored /64, undone by the x64 inject node), then load it the
    way the legacy solver path does. Never uses the float pixel buffer."""
    import numpy as _np
    from mesh_caustic import png16 as _png
    _png.write_rgb16(out, _np.clip(fld01 / 64.0, 0.0, 1.0))
    old = bpy.data.images.get("CAUSTIC_bake")
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.load(out, check_existing=False)
    img.name = "CAUSTIC_bake"
    try:
        img.colorspace_settings.name = "Non-Color"
    except Exception:
        pass
    return img


class CAUSTIC_OT_bake_seq(bpy.types.Operator):
    """Bake a mesh-caustic image sequence over a frame range"""
    bl_idname = "caustic.bake_seq"
    bl_label = "Bake mesh sequence"

    def execute(self, context):
        import traceback
        try:
            return self._execute(context)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                context.scene.caustic.status = f"error: {e}"
            except Exception:
                pass
            self.report({"ERROR"}, f"error: {e}")
            return {"CANCELLED"}

    def _execute(self, context):
        import glob
        import numpy as np
        p = context.scene.caustic
        obj = p.mesh_object or (context.active_object
                               if context.active_object and context.active_object.type == "MESH"
                               else None)
        if obj is None or obj.type != "MESH":
            p.status = "no mesh object: set Mesh object"
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        sys.path.insert(0, os.path.join(_ROOT, "tools"))
        from mesh_caustic import trace as MT
        from mesh_caustic import band as MB
        try:
            mat = _resolve_material(obj)
            recv = _resolve_target(p.target)
        except ValueError as e:
            p.status = str(e)
            self.report({"ERROR"}, p.status)
            return {"CANCELLED"}
        absorb = mat["absorb"] if mat["absorb"] is not None else tuple(p.glass_absorb)
        eta = (float(mat["ior"]) if p.mesh_achromatic
               else MT.ior_rgb(mat["ior"]))
        seqdir = os.path.join(TMP_DIR, "seq")
        os.makedirs(seqdir, exist_ok=True)
        base_n = None
        frames = []
        for f in range(p.seq_start, p.seq_end + 1):
            context.scene.frame_set(f)
            context.view_layer.update()
            # lights re-read every frame: an animated sun is the motion here
            lights = _collect_lights(context.scene.objects, tuple(p.sun_dir))
            dg = context.evaluated_depsgraph_get()
            verts, faces, tri_normals = _mesh_tris(obj, dg)
            if base_n is None:
                base_n = len(verts)
            elif len(verts) != base_n:
                p.status = (f"topology changed at frame {f}: {base_n} -> "
                            f"{len(verts)} verts (remesh not supported)")
                self.report({"ERROR"}, p.status)
                return {"CANCELLED"}
            try:
                # FULL only: one shared UV placement for every frame, and a
                # per-frame fan bbox would move between frames
                fld, res, _rect = _bake_field(MT, MB, verts, faces, lights,
                                              recv, p.mesh_resolution,
                                              p.mesh_airy, absorb, eta,
                                              frame="FULL",
                                              tri_normals=tri_normals)
            except ValueError as e:
                p.status = str(e)
                self.report({"ERROR"}, p.status)
                return {"CANCELLED"}
            fn = os.path.join(seqdir, f"caustic_{f:04d}.png")
            _write_bake_image(fld, fn)
            frames.append(fn)
        first = frames[0]
        old = bpy.data.images.get("CAUSTIC_bake")
        if old is not None:
            bpy.data.images.remove(old)
        img = bpy.data.images.load(first, check_existing=False)
        img.name = "CAUSTIC_bake"
        img.source = "SEQUENCE"
        try:
            img.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        # Map timeline frames 1:1 onto the baked files: file 0001 <=> seq_start.
        for _attr, _val in (("frame_start", p.seq_start),
                           ("use_auto_refresh", True)):
            try:
                setattr(img, _attr, _val)
            except Exception:
                pass
        p.image_path = seqdir
        p.frame_uv = (0.0, 0.0, 1.0, 1.0)
        p.frame_rect = (0.0, 0.0, 0.0)
        p.status = (f"[mesh-seq] {len(frames)} frames "
                    f"{p.seq_start}-{p.seq_end} in {seqdir}")
        self.report({"INFO"}, f"baked {len(frames)} frames to {seqdir}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------
class CAUSTIC_PT_panel(bpy.types.Panel):
    bl_label = "Wave Caustic Injector"
    bl_idname = "CAUSTIC_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Caustic"

    def draw(self, context):
        p = context.scene.caustic
        col = self.layout.column(align=True)
        col.prop(p, "solver")
        row = col.row(align=True)
        row.prop(p, "resolution")
        row.prop(p, "airy_scale")
        row = col.row(align=True)
        row.prop(p, "wave_amp")
        row.prop(p, "wave_time")
        col.prop(p, "target")
        col.prop(p, "gain")
        col.prop(p, "disable_cycles_caustics")

        self.layout.separator()
        box = self.layout.box()
        box.label(text="Coloured medium (experiment parameters)")
        box.prop(p, "glass_absorb")
        box.prop(p, "water_absorb")
        box.prop(p, "medium_objects")
        row = box.row(align=True)
        row.operator("caustic.tint_medium", icon="MOD_FLUID")
        row.operator("caustic.untint_medium", icon="X")

        self.layout.separator()
        self.layout.prop(p, "inject_mode")
        self.layout.prop(p, "directional")
        self.layout.operator("caustic.bake", icon="RENDER_STILL")
        self.layout.operator("caustic.inject", icon="NODE_MATERIAL")
        self.layout.operator("caustic.remove", icon="TRASH")
        self.layout.operator("caustic.cycles_toggle", icon="LIGHT")

        box = self.layout.box()
        box.label(text="Any-mesh bake (in-addon tracer)")
        box.prop(p, "mesh_object")
        box.prop(p, "mesh_resolution")
        box.prop(p, "mesh_airy")
        box.prop(p, "sun_dir")
        box.operator("caustic.bake_mesh", icon="MESH_DATA")
        row = box.row(align=True)
        row.prop(p, "seq_start")
        row.prop(p, "seq_end")
        box.operator("caustic.bake_seq", icon="RENDER_ANIMATION")

        box = self.layout.box()
        box.label(text=f"last bake: {p.last_ms:.0f} ms")
        if p.status:
            box.label(text=p.status[:60])

        if context.scene.render.engine == "CYCLES":
            c = context.scene.cycles
            self.layout.label(text="Cycles caustics: "
                                   f"{'on' if c.caustics_refractive else 'off'}")


CLASSES = (CausticProps, CAUSTIC_OT_bake, CAUSTIC_OT_bake_mesh, CAUSTIC_OT_bake_seq,
           CAUSTIC_OT_inject, CAUSTIC_OT_remove, CAUSTIC_OT_tint_medium,
           CAUSTIC_OT_untint_medium, CAUSTIC_OT_caustics_off, CAUSTIC_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.caustic = bpy.props.PointerProperty(type=CausticProps)


def unregister():
    del bpy.types.Scene.caustic
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
