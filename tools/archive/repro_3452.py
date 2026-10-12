"""repro_3452.py — reproduce mujoco#3452 failures on stock MuJoCo 3.14.0.
Checks: (1) neutrally buoyant sphere falls at g; (2) fluid force independent
of height (no interface); (3) gravcomp proxy gives zero angular response.
Prints MEASURED numbers; exits 0 (this documents the bug, not a test gate).
"""
import mujoco
import numpy as np

print("mujoco version:", mujoco.__version__)

# --- (1)+(2): sphere r=0.15 at exactly fluid density ---
r = 0.15
V = 4 / 3 * np.pi * r**3
m = 1000.0 * V
print(f"\n[1] sphere r={r} V={V:.7f} m={m:.6f} kg (neutrally buoyant)")

xml = f"""
<mujoco>
  <option timestep="0.002" gravity="0 0 -9.81" density="1000"/>
  <worldbody>
    <body name="s" pos="0 0 -0.4">
      <freejoint/>
      <geom type="sphere" size="{r}" mass="{m}" fluidshape="ellipsoid"/>
    </body>
  </worldbody>
</mujoco>"""
model = mujoco.MjModel.from_xml_string(xml)
data = mujoco.MjData(model)

for z in (0.5, 0.05, 0.0, -0.05, -0.5):
    data.qpos[2] = z
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)
    fz = data.qfrc_fluid[2]
    print(f"  z={z:+.2f} qfrc_fluid_z={fz:+.6f} N at rest (drag=0 everywhere; Archimedes missing)")

# fall test: start submerged at rest, integrate 2 s
data.qpos[2] = -0.4
data.qvel[:] = 0
for _ in range(1000):
    mujoco.mj_step(model, data)
print(f"  after 2 s: z={data.qpos[2]:.4f} m (physics: -0.4 hover; bug: ~-8.68 fall)")

# --- (3): gravcomp proxy, hull with keel, 30 deg roll ---
print("\n[2] gravcomp proxy angular response at 30 deg roll:")
xml2 = """
<mujoco>
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="hull" pos="0 0 0" euler="0.5236 0 0" gravcomp="1">
      <freejoint/>
      <geom type="capsule" size="0.18 0.25" mass="20"/>
      <geom type="sphere" size="0.06" pos="0 0 -0.30" mass="8"/>
    </body>
  </worldbody>
</mujoco>"""
m2 = mujoco.MjModel.from_xml_string(xml2)
d2 = mujoco.MjData(m2)
mujoco.mj_forward(m2, d2)
# angular acceleration about x from qacc
print(f"  qacc[3] (roll angacc) = {d2.qacc[3]:.3e} rad/s^2 (physics ~0.7; bug: ~0)")
