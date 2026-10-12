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
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
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
    image_path: bpy.props.StringProperty(default="")
    status: bpy.props.StringProperty(default="idle")
    last_ms: bpy.props.FloatProperty(default=0.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run_hidden(cmd, timeout=600):
    """Run the solver without flashing a console window on Windows."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


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


def _emit_into_material(mat, image, gain):
    """Image (Non-Color) -> x16 -> x gain -> Emission -> Add Shader."""
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
    tex.interpolation = "Linear"
    tex.extension = "EXTEND"
    if image is not None:
        # the baked field is linear, not sRGB: 16-bit PNG scaled by 1/16
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    tex.location = (-900, -300)

    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.name = "CAUSTIC_uv"
    uv.location = (-1100, -300)
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])

    scale, s_out = _mix_multiply(nt, tex.outputs["Color"], (16.0,) * 3 + (1.0,),
                                 "CAUSTIC_x16")
    scale.name = "CAUSTIC_x16"
    scale.location = (-650, -300)
    gm, g_out = _mix_multiply(nt, s_out, (gain,) * 3 + (1.0,), "CAUSTIC_gain")
    gm.name = "CAUSTIC_gain"
    gm.location = (-450, -300)

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
        if not obj.data.materials:
            obj.data.materials.append(bpy.data.materials.new("caustic_receiver"))
        ok = 0
        for mat in obj.data.materials:
            if _emit_into_material(mat, img, p.gain):
                ok += 1
        if p.disable_cycles_caustics and context.scene.render.engine == "CYCLES":
            context.scene.cycles.caustics_refractive = False
            context.scene.cycles.caustics_reflective = False
        self.report({"INFO"}, f"injected into {ok} material slot(s)")
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
        self.report({"INFO"}, f"removed {n} injection node(s)")
        return {"FINISHED"}


class CAUSTIC_OT_caustics_off(bpy.types.Operator):
    """Toggle Cycles' own caustics on/off"""
    bl_idname = "caustic.cycles_toggle"
    bl_label = "Toggle Cycles caustics"

    def execute(self, context):
        c = context.scene.cycles
        c.caustics_refractive = not c.caustics_refractive
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
        self.layout.operator("caustic.bake", icon="RENDER_STILL")
        self.layout.operator("caustic.inject", icon="NODE_MATERIAL")
        self.layout.operator("caustic.remove", icon="TRASH")
        self.layout.operator("caustic.cycles_toggle", icon="LIGHT")

        box = self.layout.box()
        box.label(text=f"last bake: {p.last_ms:.0f} ms")
        if p.status:
            box.label(text=p.status[:60])

        if context.scene.render.engine == "CYCLES":
            c = context.scene.cycles
            self.layout.label(text="Cycles caustics: "
                                   f"{'on' if c.caustics_refractive else 'off'}")


CLASSES = (CausticProps, CAUSTIC_OT_bake, CAUSTIC_OT_inject, CAUSTIC_OT_remove,
           CAUSTIC_OT_caustics_off, CAUSTIC_PT_panel)


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
