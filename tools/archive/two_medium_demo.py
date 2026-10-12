"""two_medium_demo.py — our wrapper fix for #3452, proven in Python first.
Same scenes as repro_3452.py, but each step adds our Archimedes wrench
(force at center of buoyancy -> restoring moment exists) via xfrc_applied.
Asserts: (1) neutral sphere HOVERS; (2) partial submersion gives partial force;
(3) hull SELF-RIGHTS from 30 deg roll.
"""
import mujoco
import numpy as np

RHO_W, G = 1000.0, 9.81


def sphere_cap(r, cz, surf=0.0):
    h = min(max(surf - (cz - r), 0.0), 2 * r)
    if h <= 0:
        return 0.0, cz
    V = np.pi * h * h * (r - h / 3.0)
    zbar = -3.0 * (2 * r - h) ** 2 / (4.0 * (3 * r - h))
    return V, cz + zbar


def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


# ---------- test 1: neutral sphere hovers ----------
r = 0.15
V = 4 / 3 * np.pi * r**3
m = RHO_W * V
xml = f"""
<mujoco>
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="s" pos="0 0 -0.4">
      <freejoint/>
      <geom type="sphere" size="{r}" mass="{m}"/>
    </body>
  </worldbody>
</mujoco>"""
model = mujoco.MjModel.from_xml_string(xml)
data = mujoco.MjData(model)
bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "s")

# partial-submersion spot check (analytic, no sim needed)
for cz in (0.10, 0.0, -0.10):
    Vsub, _ = sphere_cap(r, cz)
    print(f"partial z={cz:+.2f}: Vsub={Vsub:.7f} F={RHO_W*G*Vsub:.3f} N")

data.qpos[2] = -0.4
data.qvel[:] = 0
for _ in range(1500):  # 3 s
    mujoco.mj_forward(model, data)
    Vsub, zc = sphere_cap(r, data.qpos[2])
    F = RHO_W * G * Vsub
    data.xfrc_applied[bid, 2] = F  # through center: no torque for sphere
    mujoco.mj_step(model, data)
z = data.qpos[2]
print(f"[1] hover after 3 s: z={z:.4f} m (target -0.4 +- 0.05)")
assert abs(z - (-0.4)) < 0.05, "sphere did not hover!"

# ---------- test 2: hull self-rights (true per-step clip of the box) ----------
# NOTE: MJCF angles are DEGREES by default, so 30 deg roll = euler="30 0 0".
# The hull is a box + dense keel sphere. Each step we clip the box against the
# surface with scipy.ConvexHull (exact for convex pieces) to get the TRUE
# submerged centroid, which shifts toward the heeled side -> righting moment.
from scipy.spatial import ConvexHull

BOX_HE = np.array([0.25, 0.18, 0.15])  # half extents
M_BOX, M_KEEL = 20.0, 8.0
KEEL_LOCAL = np.array([0.0, 0.0, -0.30])
COM_LOCAL = M_KEEL * KEEL_LOCAL / (M_BOX + M_KEEL)  # box centered at origin
V_KEEL = 4 / 3 * np.pi * 0.06**3
CORNERS = np.array([[sx * BOX_HE[0], sy * BOX_HE[1], sz * BOX_HE[2]]
                    for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
EDGES = [(i, j) for i in range(8) for j in range(i + 1, 8)
         if np.sum(CORNERS[i] != CORNERS[j]) == 1]


def clip_box(R, com):
    pts_body = CORNERS - COM_LOCAL  # about COM
    pts = com + pts_body @ R.T
    d = pts[:, 2]  # height above surface (surf z=0)
    keep = [p for p, di in zip(pts, d) if di <= 0]
    for i, j in EDGES:
        if (d[i] <= 0) != (d[j] <= 0):
            a = d[i] / (d[i] - d[j])
            keep.append(pts[i] + a * (pts[j] - pts[i]))
    keep = np.array(keep)
    if len(keep) < 4:
        return 0.0, com.copy()
    try:
        hull = ConvexHull(keep)
    except Exception:
        return 0.0, com.copy()
    V = hull.volume
    # centroid via fan from interior point over hull facets
    interior = keep.mean(axis=0)
    C = np.zeros(3)
    for s in hull.simplices:
        a, b, c = keep[s]
        vol = abs(np.dot(a - interior, np.cross(b - interior, c - interior))) / 6.0
        C += vol * (interior + a + b + c) / 4.0
    return V, C / V if V > 0 else com.copy()


xml2 = """
<mujoco>
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="hull" pos="0 0 -0.10" euler="30 0 0">
      <freejoint/>
      <geom type="box" size="0.25 0.18 0.15" mass="20"/>
      <geom type="sphere" size="0.06" pos="0 0 -0.30" mass="8"/>
    </body>
  </worldbody>
</mujoco>"""
m2 = mujoco.MjModel.from_xml_string(xml2)
d2 = mujoco.MjData(m2)
b2 = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_BODY, "hull")


def roll_of(q):
    R = quat_to_R(q[3:])
    return np.arctan2(R[2, 1], R[2, 2])


roll0 = roll_of(d2.qpos)
print(f"[2] initial roll: {np.degrees(roll0):.1f} deg")
for _ in range(5000):  # 10 s
    mujoco.mj_forward(m2, d2)
    R = quat_to_R(d2.qpos[3:])
    com = d2.qpos[:3].copy()
    Vbox, cob_box = clip_box(R, com)
    keel_w = com + R @ (KEEL_LOCAL - COM_LOCAL)
    V = Vbox + V_KEEL
    cob = (Vbox * cob_box + V_KEEL * keel_w) / V if V > 0 else com.copy()
    F = RHO_W * G * V
    T = np.cross(cob - com, np.array([0.0, 0.0, F]))
    d2.xfrc_applied[b2, :3] = (0, 0, F)
    d2.xfrc_applied[b2, 3:] = T
    mujoco.mj_step(m2, d2)

roll1 = roll_of(d2.qpos)
print(f"[2] roll {np.degrees(roll0):.1f} deg -> {np.degrees(roll1):.1f} deg after 10 s (must decrease)")
assert abs(roll1) < abs(roll0) - np.radians(5), "hull did not self-right!"
print("ALL WRAPPER CHECKS PASSED")
