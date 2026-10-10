"""studio.py — a real product-shot lighting rig and surface detail for the
Blender scene, kept separate so the validated default pipeline is untouched.

What a single sun plus a flat ambient misses:

* **fill** — a large soft source opposite the key, so the shadow side is lit by
  something with a shape instead of a constant. This is what makes the shadow
  read as a gradient rather than a flat grey hole.
* **rim/back light** — separates the glass from the background at the edges.
* **gradient environment** — real rooms are brighter overhead and darker toward
  the floor. A constant ambient cannot produce the vertical falloff that reads as
  "this object is standing on a surface in a room".
* **procedural normal map on the table** — a Bump node driven by a wave + noise
  pair, so the surface catches the light along micro-detail instead of being an
  optically perfect plane.

All of these are additive and only run under --studio.
"""
import bpy


def add_studio_lights(key_energy, sun_dir, radius=0.35):
    """A key/fill/rim rig around a 0.32 m subject."""
    lights = []

    # FILL: large, soft, opposite the key and slightly below it
    d = bpy.data.lights.new("fill", type="AREA")
    d.shape = "RECTANGLE"
    d.size = 0.9
    d.size_y = 0.6
    # ~15% of the key's irradiance at 0.35 m: a fill, not a second sun
    d.energy = 0.15 * key_energy
    d.color = (0.86, 0.90, 1.0)          # cool fill, like skylight
    ob = bpy.data.objects.new("fill", d)
    bpy.context.collection.objects.link(ob)
    ob.location = (radius * 0.6, radius * 0.75, radius * 0.45)
    look = (0.0, 0.0, 0.02)
    import mathutils
    v = mathutils.Vector(look) - ob.location
    ob.rotation_euler = v.to_track_quat("-Z", "Y").to_euler()
    lights.append(ob)

    # RIM: small and bright, behind and to the side, to edge the glass
    d = bpy.data.lights.new("rim", type="AREA")
    d.shape = "RECTANGLE"
    d.size = 0.35
    d.size_y = 0.12
    # ~45% of the key, concentrated into a small strip
    d.energy = 0.45 * key_energy
    d.color = (1.0, 0.97, 0.92)
    ob = bpy.data.objects.new("rim", d)
    bpy.context.collection.objects.link(ob)
    ob.location = (-radius * 0.55, radius * 0.30, radius * 0.38)
    v = mathutils.Vector((0.0, 0.0, 0.035)) - ob.location
    ob.rotation_euler = v.to_track_quat("-Z", "Y").to_euler()
    lights.append(ob)
    return lights


def gradient_world(strength=0.45, sky=(0.36, 0.48, 0.78), ground=(0.38, 0.42, 0.54)):
    """Vertical gradient environment: bright overhead, dark underfoot."""
    w = bpy.data.worlds.new("studio_world")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tex.outputs["Generated"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (*ground, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (*sky, 1.0)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


def table_detail(bsdf, nodes, links, strength=0.35):
    """Procedural normal map on the table: broad grain plus fine tooth.

    A normal map changes the shading normal without changing geometry, which is
    how a real surface keeps its silhouette while catching light along grain.
    """
    grain = nodes.new("ShaderNodeTexWave")
    grain.wave_type = "BANDS"
    grain.bands_direction = "Y"
    grain.inputs["Scale"].default_value = 42.0
    grain.inputs["Distortion"].default_value = 6.0
    grain.inputs["Detail"].default_value = 4.0
    grain.location = (-900, 420)

    tooth = nodes.new("ShaderNodeTexNoise")
    tooth.inputs["Scale"].default_value = 900.0
    tooth.inputs["Detail"].default_value = 6.0
    tooth.location = (-900, 180)

    mix = nodes.new("ShaderNodeMix")
    try:
        mix.data_type = "FLOAT"
        links.new(grain.outputs["Fac"], mix.inputs[2])
        links.new(tooth.outputs["Fac"], mix.inputs[3])
        mix.inputs[0].default_value = 0.25
        mix_out = mix.outputs[0]
    except Exception:
        links.new(grain.outputs["Fac"], mix.inputs[0])
        mix_out = mix.outputs[0]
    mix.location = (-640, 300)

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.0015
    bump.location = (-340, 300)
    links.new(mix_out, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return bump
