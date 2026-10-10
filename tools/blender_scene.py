"""blender_scene.py — photoreal glass-of-water-on-table render in Blender Cycles,
with OUR wave-corrected caustic injected as light.

Why this exists: a hand-written mini renderer cannot reach Cycles-grade realism
(no GI, no MIS, no AgX, no real BSDFs). So the base image is a genuine Blender
render, and the caustic - the one thing Cycles does badly and expensively - is
supplied by our solver as a 16-bit texture on the receiver. Cycles' own caustics
are switched off, so every bright ribbon in the output is our model's.

Geometry and sun direction are identical to src/app/showcase_main.cpp, so the
injected field lines up with Cycles' own shadow.

    blender --background --factory-startup --python tools/blender_scene.py -- \
        --caustic out/caustic.png --out out/blender_render.png \
        --samples 512 --w 1280 --h 800 [--blend out/scene.blend]
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

# ---- must match showcase_main.cpp -----------------------------------------
GLASS_R = 0.035
GLASS_H = 0.090
WALL = 0.0035
FILL = 0.66
WATER_TOP = 0.0594                      # absolute water line, = solver kWaterLevel
SUN_DIR = Vector((0.80, 0.42, -0.43))  # direction light travels
SUN_ANGLE = 0.042                      # radians (our solver uses 1.2 deg radius)
EXT = 0.16                             # caustic patch half-size
SUN_E = 19.0                           # perpendicular irradiance, W/m^2


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--caustic", default="out/caustic.png")
    ap.add_argument("--out", default="out/blender_render.png")
    ap.add_argument("--samples", type=int, default=512)
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--h", type=int, default=800)
    ap.add_argument("--gain", type=float, default=1.0, help="caustic emission gain")
    ap.add_argument("--blend", default="", help="optional path to save the .blend")
    ap.add_argument("--sun", type=float, default=None, help="sun irradiance W/m^2")
    ap.add_argument("--world", type=float, default=None, help="world strength")
    ap.add_argument("--world-color", default="", help="r,g,b")
    ap.add_argument("--sun-color", default="", help="r,g,b")
    ap.add_argument("--dist", type=float, default=0.42)
    ap.add_argument("--elev", type=float, default=21.0)
    ap.add_argument("--az", type=float, default=38.0)
    ap.add_argument("--lens", type=float, default=60.0)
    ap.add_argument("--exposure", type=float, default=0.0)
    ap.add_argument("--ortho", action="store_true",
                    help="orthographic top-down camera over exactly the baked patch")
    ap.add_argument("--hide-glass", action="store_true",
                    help="hide everything but the table: the reference for a "
                         "differential render that isolates the caustic")
    ap.add_argument("--no-denoise", action="store_true",
                    help="raw path tracing: keeps the Monte-Carlo noise "
                         "that the denoiser would hide")
    ap.add_argument("--sun-angle", type=float, default=2.4,
                    help="angular diameter of the sun in degrees; "
                         "small = hard caustics")
    ap.add_argument("--wave-t", type=float, default=0.0,
                    help="water ripple phase; must match the solver's "
                         "--wave-t so geometry and bake agree")
    ap.add_argument("--studio", action="store_true",
                    help="key/fill/rim rig, gradient environment, "
                         "procedural normal maps")
    ap.add_argument("--flat-water", action="store_true",
                    help="flat water surface instead of the rippled one")
    ap.add_argument("--keep-filter-glossy", action="store_true",
                    help="keep Blender's 1.0 rad Filter Glossy, which blurs "
                         "the refraction that makes a caustic")
    ap.add_argument("--clamp-indirect", type=float, default=None,
                    help="indirect sample clamp; 0 disables it so caustic "
                         "samples are not suppressed (Blender default 10)")
    ap.add_argument("--no-adaptive", action="store_true",
                    help="disable adaptive sampling, which can stop before a "
                         "thin caustic is found")
    ap.add_argument("--dump-settings", action="store_true",
                    help="print the Cycles settings that decide caustic "
                         "quality, then exit")
    ap.add_argument("--no-caustic", action="store_true")
    ap.add_argument("--cycles-caustics", action="store_true",
                    help="let Cycles find caustics by path tracing "
                         "instead of injecting ours (for the A/B)")
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
              bpy.data.cameras, bpy.data.images, bpy.data.objects):
        for item in list(c):
            c.remove(item)


def _studio():
    import sys as _s
    _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import studio
    return studio


def make_table(gain, caustic_path, use_caustic, detail=False):
    """0.32 x 0.32 m plane at z=0 with explicit UVs: +X = u, +Y = v."""
    mesh = bpy.data.meshes.new("table")
    verts = [(-EXT, -EXT, 0.0), (EXT, -EXT, 0.0), (EXT, EXT, 0.0), (-EXT, EXT, 0.0)]
    faces = [(0, 1, 2, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    # v=1 at +Y, matching the exported caustic (row 0 = +Y)
    coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for i, (u, v) in enumerate(coords):
        uv.data[i].uv = (u, v)
    obj = bpy.data.objects.new("table", mesh)
    bpy.context.collection.objects.link(obj)

    mat = bpy.data.materials.new("table_surface")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)

    # matte seamless surface, like the reference product shot
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    bsdf.inputs["Base Color"].default_value = (0.82, 0.82, 0.82, 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.52
    if "Specular IOR Level" in bsdf.inputs:
        # a matte surface: the reference is diffuse, and a glossy table reflects
        # the sun's disk (radiance ~E/Omega ~ 5000) which blew 9.4% of the frame
        # before this was lowered from 0.35
        bsdf.inputs["Specular IOR Level"].default_value = 0.05

    # real surfaces are not perfectly uniform: a fine roughness variation keeps
    # the sheen from reading as a flat procedural plate
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 260.0
    noise.inputs["Detail"].default_value = 8.0
    noise.location = (-260, 170)
    rmap = nodes.new("ShaderNodeMapRange")
    rmap.inputs["From Min"].default_value = 0.35
    rmap.inputs["From Max"].default_value = 0.65
    rmap.inputs["To Min"].default_value = 0.44
    rmap.inputs["To Max"].default_value = 0.62
    rmap.location = (0, 170)
    links.new(noise.outputs["Fac"], rmap.inputs["Value"])
    links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    if detail:
        # procedural normal map: broad grain + fine tooth (see tools/studio.py)
        _studio().table_detail(bsdf, nodes, links)

    if use_caustic and caustic_path and os.path.exists(caustic_path):
        img = bpy.data.images.load(caustic_path)
        img.colorspace_settings.name = "Non-Color"
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        tex.location = (-600, -260)
        # Undo the /16 export scale and apply the gain as COLOUR multiplications.
        # A ShaderNodeMath fed from a colour socket silently collapses to a single
        # channel: the caustic was being injected as greyscale, throwing away the
        # per-channel dispersion the bake carries (its |R-B| is 31% of the field
        # mean). ShaderNodeMix in RGBA mode keeps all three channels.
        def mul_rgb(sock, value, loc):
            try:
                n = nodes.new("ShaderNodeMix")       # Blender 3.4+
                n.data_type = "RGBA"
                n.blend_type = "MULTIPLY"
                n.inputs[0].default_value = 1.0
                links.new(sock, n.inputs[6])
                n.inputs[7].default_value = (value, value, value, 1.0)
                out_sock = n.outputs[2]
            except Exception:
                n = nodes.new("ShaderNodeMixRGB")
                n.blend_type = "MULTIPLY"
                n.inputs["Fac"].default_value = 1.0
                links.new(sock, n.inputs["Color1"])
                n.inputs["Color2"].default_value = (value, value, value, 1.0)
                out_sock = n.outputs["Color"]
            n.location = loc
            return out_sock

        scaled = mul_rgb(tex.outputs["Color"], 16.0, (-360, -260))
        gained = mul_rgb(scaled, gain, (-160, -260))
        emit = nodes.new("ShaderNodeEmission")
        emit.location = (60, -300)
        emit.inputs["Strength"].default_value = 1.0
        links.new(gained, emit.inputs["Color"])
        add = nodes.new("ShaderNodeAddShader")
        add.location = (400, 0)
        links.new(bsdf.outputs[0], add.inputs[0])
        links.new(emit.outputs[0], add.inputs[1])
        links.new(add.outputs[0], out.inputs["Surface"])
    else:
        links.new(bsdf.outputs[0], out.inputs["Surface"])
    obj.data.materials.append(mat)
    return obj


def make_glass():
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=GLASS_R, depth=GLASS_H,
                                        location=(0, 0, GLASS_H / 2))
    obj = bpy.context.object
    obj.name = "glass"
    bpy.ops.object.mode_set(mode="OBJECT")
    sol = obj.modifiers.new("wall", "SOLIDIFY")
    sol.thickness = WALL
    sol.offset = -1.0
    bpy.ops.object.modifier_apply(modifier=sol.name)
    # a real tumbler has a rounded rim and base edge, not a razor edge
    bev = obj.modifiers.new("rim", "BEVEL")
    bev.width = 0.0006
    bev.segments = 3
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(40)
    bpy.ops.object.modifier_apply(modifier=bev.name)
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new("glass")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.52
    b.inputs["Transmission Weight"].default_value = 1.0
    obj.data.materials.append(mat)
    return obj


def wave_h(x, y, t=0.0):
    """Water-surface height, matching the solver's WaveParams exactly.

    src/app/showcase_main.cpp uses
        h = sum_i amp_i * sin(k_i * (ux*x + uy*y) + t * (1 + i))
    with the same amplitudes, wavelengths, directions and t = 0. Keeping the two
    in step is what makes the render and the bake the same physical scene.
    """
    amp = (0.00065, 0.00040, 0.00025, 0.00015)
    lam = (0.042, 0.027, 0.017, 0.011)
    dx = (1.0, 0.35, -0.75, 0.6)
    dy = (0.25, 1.0, 0.55, -0.9)
    h = 0.0
    for i in range(4):
        n = math.hypot(dx[i], dy[i])
        ux, uy = dx[i] / n, dy[i] / n
        k = 2.0 * math.pi / lam[i]
        h += amp[i] * math.sin(k * (ux * x + uy * y) + t * (1.0 + i))
    return h


def make_water(waves=True, wave_t=0.0):
    """Water inside the glass, with a genuinely rippled surface.

    A flat disc cannot produce the turbulent caustic of the reference
    photograph, and it is not the same object our solver traced. This builds a
    real surface: a radial grid displaced by the same wave field, plus the side
    wall and floor so the volume is closed.
    """
    r = GLASS_R - WALL
    z_bot = WALL
    z_top = WATER_TOP                  # absolute, matches the solver's water line
    NR, NS = 40, 128
    verts, faces = [], []
    if waves:
        verts.append((0.0, 0.0, z_top + wave_h(0.0, 0.0, wave_t)))       # centre
        for i in range(1, NR + 1):
            rr = r * i / NR
            for j in range(NS):
                a = 2 * math.pi * j / NS
                x, y = rr * math.cos(a), rr * math.sin(a)
                verts.append((x, y, z_top + wave_h(x, y, wave_t)))
        ring = lambda i, j: 1 + (i - 1) * NS + (j % NS) if i > 0 else 0
        for j in range(NS):                                      # centre fan
            faces.append((0, ring(0, j), ring(0, j + 1)))
        for i in range(1, NR):
            for j in range(NS):
                a, b = ring(i, j), ring(i, j + 1)
                c, d = ring(i + 1, j + 1), ring(i + 1, j)
                faces.append((a, b, c, d))
    else:
        verts.append((0.0, 0.0, z_top))
        for i in range(1, NR + 1):
            rr = r * i / NR
            for j in range(NS):
                a = 2 * math.pi * j / NS
                verts.append((rr * math.cos(a), rr * math.sin(a), z_top))
        ring = lambda i, j: 1 + (i - 1) * NS + (j % NS) if i > 0 else 0
        for j in range(NS):
            faces.append((0, ring(0, j), ring(0, j + 1)))
        for i in range(1, NR):
            for j in range(NS):
                faces.append((ring(i, j), ring(i, j + 1),
                              ring(i + 1, j + 1), ring(i + 1, j)))
    # side wall from the rim down, and the floor: closed volume
    rim0 = len(verts)
    for j in range(NS):
        a = 2 * math.pi * j / NS
        verts.append((r * math.cos(a), r * math.sin(a), z_bot))
    for j in range(NS):
        top_a = ring(NR, j)
        top_b = ring(NR, j + 1)
        bot_a = rim0 + j
        bot_b = rim0 + (j + 1) % NS
        faces.append((top_a, bot_a, bot_b, top_b))
    verts.append((0.0, 0.0, z_bot))
    cbot = len(verts) - 1
    for j in range(NS):
        faces.append((cbot, rim0 + (j + 1) % NS, rim0 + j))

    mesh = bpy.data.meshes.new("water")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("water", mesh)
    bpy.context.collection.objects.link(obj)
    mat = bpy.data.materials.new("water")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.333
    b.inputs["Transmission Weight"].default_value = 1.0
    obj.data.materials.append(mat)
    return obj


def make_sun(energy=None, color=None, angle=None):
    d = bpy.data.lights.new("sun", type="SUN")
    d.energy = SUN_E if energy is None else energy
    d.angle = SUN_ANGLE if angle is None else angle
    d.color = (1.0, 0.95, 0.88) if color is None else color
    obj = bpy.data.objects.new("sun", d)
    bpy.context.collection.objects.link(obj)
    # the light travels along SUN_DIR, i.e. its -Z axis points that way
    obj.rotation_euler = SUN_DIR.to_track_quat("-Z", "Y").to_euler()
    return obj


def make_world(strength=None, color=None):
    w = bpy.data.worlds.new("world")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.64, 0.68, 1.0) if color is None else color
    bg.inputs["Strength"].default_value = 0.45 if strength is None else strength
    return w


def make_camera(args):
    if getattr(args, "ortho", False):
        # straight down over exactly the patch the solver bakes, so the render
        # and our field are the same image
        cam = bpy.data.cameras.new("cam")
        cam.type = "ORTHO"
        cam.ortho_scale = 2 * EXT
        obj = bpy.data.objects.new("cam", cam)
        bpy.context.collection.objects.link(obj)
        obj.location = (0.0, 0.0, 1.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        bpy.context.scene.camera = obj
        return obj
    # look at the glass + the fan: aim between them, from an elevation
    fan = Vector((SUN_DIR.x, SUN_DIR.y, 0.0)).normalized()
    target = Vector((fan.x * 0.055, fan.y * 0.055, GLASS_H * 0.30))
    az = math.radians(args.az)
    elev = math.radians(args.elev)
    dist = args.dist
    view = Vector((math.cos(elev) * math.cos(az), math.cos(elev) * math.sin(az), math.sin(elev)))
    eye = target + view * dist
    cam = bpy.data.cameras.new("cam")
    cam.lens = args.lens
    obj = bpy.data.objects.new("cam", cam)
    bpy.context.collection.objects.link(obj)
    obj.location = eye
    obj.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


def configure_render(args):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = args.samples
    sc.cycles.use_denoising = not getattr(args, "no_denoise", False)
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    # the caustic is OURS: switch Cycles' own off so nothing here is a
    # path-traced caustic sneaking in and being credited to our model
    if not getattr(args, "cycles_caustics", False):
        sc.cycles.caustics_reflective = False
        sc.cycles.caustics_refractive = False
    # --- caustic-friendly light paths -------------------------------------
    # Filter Glossy blurs glossy/refraction paths. Blender's own factory default
    # is 1.0 rad, which SMEARS THE VERY REFRACTION THAT FORMS A CAUSTIC: any
    # comparison of caustic quality against a path tracer must turn it off, or
    # the path tracer is being measured through a blur filter. Set to 0 unless
    # explicitly asked to keep the blur.
    sc.cycles.blur_glossy = 1.0 if getattr(args, "keep_filter_glossy", False) else 0.0
    # 8 was cutting the path short; the default is 12 and this scene needs the
    # transmission chain plus GI.
    sc.cycles.max_bounces = 12
    # Indirect clamping suppresses the rare bright samples that ARE a caustic.
    # Blender defaults it to 10.0; allow it to be disabled to give the path
    # tracer its best possible shot before any claim is made about its quality.
    if getattr(args, "clamp_indirect", None) is not None:
        sc.cycles.sample_clamp_indirect = args.clamp_indirect
    if getattr(args, "no_adaptive", False):
        sc.cycles.use_adaptive_sampling = False
    sc.cycles.diffuse_bounces = 4
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 12
    sc.cycles.transparent_max_bounces = 12
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        for want in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = want
                for d in prefs.devices:
                    d.use = (d.type == want)
                break
            except Exception:
                continue
        sc.cycles.device = "GPU"
        print("CYCLES_DEVICE", prefs.compute_device_type)
    except Exception as e:  # noqa: BLE001
        print("GPU_SETUP_FAILED", e)
    sc.render.resolution_x = args.w
    sc.render.resolution_y = args.h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    try:
        sc.render.image_settings.color_depth = "16"
    except Exception:
        pass
    sc.view_settings.exposure = args.exposure
    sc.render.filepath = args.out
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception as e:  # noqa: BLE001
        print("VIEW_TRANSFORM_FALLBACK", e)
    return sc


def main():
    args = parse_args()
    clear_scene()
    make_table(args.gain, args.caustic,
               not args.no_caustic and not args.cycles_caustics,
               detail=getattr(args, "studio", False))
    make_glass()
    make_water(not getattr(args, "flat_water", False),
               getattr(args, "wave_t", 0.0))
    if getattr(args, "hide_glass", False):
        # differential reference: table only, so (with_glass - without_glass)
        # isolates what the glass actually did to the light
        for ob in bpy.data.objects:
            if ob.type == "MESH" and "table" not in ob.name.lower():
                ob.hide_render = True
    # light colour takes 3 components, world Background takes 4
    sc_col = tuple(float(v) for v in args.sun_color.split(",")) if args.sun_color else None
    w_col = (tuple(float(v) for v in args.world_color.split(",")) + (1.0,)) if args.world_color else None
    make_sun(args.sun, sc_col,
             math.radians(args.sun_angle) if args.sun_angle else None)
    make_world(args.world, w_col)
    if getattr(args, "studio", False):
        # a real rig instead of one sun over a flat ambient
        st = _studio()
        st.gradient_world(float(args.world))
        st.add_studio_lights(float(args.sun) if args.sun else 8.0, SUN_DIR)
    make_camera(args)
    sc = configure_render(args)
    if getattr(args, "dump_settings", False):
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from audit_cycles_settings import report
        report()
        _sys.exit(0)
    print(f"RENDER_START samples={args.samples} {args.w}x{args.h} "
          f"caustic={'cycles-native' if args.cycles_caustics else ('off' if args.no_caustic else args.caustic)} gain={args.gain}")
    sys.stdout.flush()
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.blend)
        print("SAVED_BLEND", args.blend)
    bpy.ops.render.render(write_still=True)
    print("RENDER_DONE", args.out)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
