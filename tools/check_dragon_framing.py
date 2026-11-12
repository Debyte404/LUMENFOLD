"""check_dragon_framing.py -- prove the beauty cameras share one view.

Reads the Cycles camera dump, the generated PBRT scene and the generated
Mitsuba scene, reconstructs each camera, projects the dragon's bounding-box
corners and prints a table. Exits 1 unless every engine lands within 0.1 deg
of the Cycles horizontal field of view and within 1% of the frame.

Usage:
  python tools/check_dragon_framing.py --self-test
  python tools/check_dragon_framing.py
"""
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
TOL_FOV = 0.1   # degrees
TOL_BBOX = 0.01  # fraction of the frame


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return [v / n for v in a]


def _dir(origin, target):
    return _norm([t - o for o, t in zip(origin, target)])


def camera_from_cycles(cam):
    m = cam["matrix"]
    w, h = cam["resolution"]
    if cam["sensor_fit"] == "HORIZONTAL" or (
            cam["sensor_fit"] == "AUTO" and w >= h):
        sensor = cam["sensor_width"]
    else:
        sensor = cam["sensor_height"]
    hfov = math.degrees(2 * math.atan(sensor / 2 / cam["lens"]))
    return {"eye": [m[0][3], m[1][3], m[2][3]],
            "right": _norm([m[0][0], m[1][0], m[2][0]]),
            "up": _norm([m[0][1], m[1][1], m[2][1]]),
            "fwd": _norm([-m[0][2], -m[1][2], -m[2][2]]),
            "hfov": hfov, "aspect": w / h, "mirror": False}


def camera_from_pbrt(text):
    look = re.search(r"LookAt\s+([^\n]+)", text)
    if look is None:
        raise SystemExit("no LookAt in the PBRT scene")
    v = [float(x) for x in look.group(1).split()]
    if len(v) != 9:
        raise SystemExit(f"LookAt needs 9 numbers, got {len(v)}")
    eye, target, up = v[0:3], v[3:6], v[6:9]
    fov = float(re.search(r'"float fov"\s*\[([-\d.eE+]+)\]', text).group(1))
    w = int(re.search(r'"integer xresolution"\s*\[(\d+)\]', text).group(1))
    h = int(re.search(r'"integer yresolution"\s*\[(\d+)\]', text).group(1))
    frame = re.search(r'"float frameaspectratio"\s*\[([-\d.eE+]+)\]', text)
    aspect = float(frame.group(1)) if frame else w / h
    try:
        vfov = fov
        hfov = math.degrees(2 * math.atan(
            math.tan(math.radians(vfov) / 2) * aspect))
    except ValueError:
        raise SystemExit("bad PBRT fov")
    d = _dir(eye, target)
    right = _norm(_cross(up, d))
    newup = _norm(_cross(d, right))
    return {"eye": eye, "right": right, "up": newup, "fwd": d,
            "hfov": hfov, "aspect": aspect,
            "mirror": "Scale -1 1 1" in text}


def camera_from_mitsuba(text):
    fov = float(re.search(r"'fov':\s*([-\d.eE+]+)", text).group(1))
    axis = re.search(r"'fov_axis':\s*'(\w+)'", text)
    axis = axis.group(1) if axis else "x"
    w = int(re.search(r"'width':\s*(\d+)", text).group(1))
    h = int(re.search(r"'height':\s*(\d+)", text).group(1))
    origin = [float(x) for x in re.search(
        r"look_at\(origin=\[([-\d., ]+)\]", text).group(1).split(",")]
    target = [float(x) for x in re.search(
        r"target=\[([-\d., ]+)\]", text).group(1).split(",")]
    up = [float(x) for x in re.search(
        r"up=\[([-\d., ]+)\]", text).group(1).split(",")]
    aspect = w / h
    if axis == "x":
        hfov = fov
    elif axis == "y":
        hfov = math.degrees(2 * math.atan(
            math.tan(math.radians(fov) / 2) * aspect))
    else:
        raise SystemExit(f"unsupported Mitsuba fov_axis {axis!r}")
    d = _dir(origin, target)
    right = _norm(_cross(d, up))
    newup = _norm(_cross(right, d))
    return {"eye": origin, "right": right, "up": newup, "fwd": d,
            "hfov": hfov, "aspect": aspect, "mirror": False}


def project_bbox(cam, points):
    tx = math.tan(math.radians(cam["hfov"]) / 2)
    ty = tx / cam["aspect"]
    xs, ys = [], []
    for p in points:
        d = [p[i] - cam["eye"][i] for i in range(3)]
        z = _dot(d, cam["fwd"])
        if z <= 0:
            raise SystemExit("dragon bounding box reaches behind the camera")
        x = _dot(d, cam["right"])
        y = _dot(d, cam["up"])
        if cam["mirror"]:
            x = -x
        xs.append(0.5 * (1 + (x / z) / tx))
        ys.append(0.5 * (1 - (y / z) / ty))
    return min(xs), max(xs), min(ys), max(ys)


def obj_bbox(path):
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    with open(path) as f:
        for line in f:
            if not line.startswith("v "):
                continue
            v = [float(x) for x in line.split()[1:4]]
            for i in range(3):
                lo[i] = min(lo[i], v[i])
                hi[i] = max(hi[i], v[i])
    if lo[0] == float("inf"):
        raise SystemExit(f"no vertices in {path}")
    return lo, hi


def obj_corners(path):
    lo, hi = obj_bbox(path)
    return [[lo[0] if i & 1 else hi[0],
             lo[1] if i & 2 else hi[1],
             lo[2] if i & 4 else hi[2]] for i in range(8)]


def bbox_error(got, expected):
    """Largest absolute difference between two (lo, hi) boxes, in metres."""
    return max(abs(got[k][i] - expected[k][i])
               for k in range(2) for i in range(3))


def _self_test():
    cam = {"eye": [0, 0, 5], "right": [1, 0, 0], "up": [0, 1, 0],
           "fwd": [0, 0, -1], "hfov": 90.0, "aspect": 1.0, "mirror": False}
    lo, hi, bot, top = project_bbox(cam, [[0, 0, 0]])
    assert abs(lo - 0.5) < 1e-12 and abs(top - 0.5) < 1e-12, \
        "the look-at point must project to the frame centre"
    lo, hi, bot, top = project_bbox(cam, [[5, 0, 0]])
    assert abs(hi - 1.0) < 1e-9, "tan(45) at the focal plane must map to x=1"
    lo, hi, bot, top = project_bbox(cam, [[-5, 0, 0]])
    assert abs(lo - 0.0) < 1e-9, "the mirrored side must map to x=0"

    old = ('LookAt 0 0 5   0 0 0   0 1 0\n'
           'Camera "perspective" "float fov" [39.6]\n'
           '       "float frameaspectratio" [1.777778]\n'
           '     "integer xresolution" [2560] "integer yresolution" [1440]\n')
    c = camera_from_pbrt(old)
    assert abs(c["hfov"] - 65.3) < 0.3, \
        "the old narrow-axis fov must reconstruct as 65 deg"
    fixed = old.replace("[39.6]", "[22.91]").replace(
        "LookAt", "Scale -1 1 1\nLookAt")
    c = camera_from_pbrt(fixed)
    assert abs(c["hfov"] - 39.6) < 0.1, "the corrected fov must reconstruct"
    assert c["mirror"] is True, "Scale -1 1 1 must be honoured"

    ms = ("scene = mi.load_dict({\n"
          "    'sensor': {'type': 'perspective', 'fov': 39.6, 'fov_axis': 'x',\n"
          "               'to_world': T.look_at(origin=[1.47, 2.03, 1.29], "
          "target=[0, 0, 0.1], up=[0, 0, 1]),\n"
          "               'film': {'type': 'hdrfilm', 'width': 1600, "
          "'height': 900}}},\n")
    c = camera_from_mitsuba(ms)
    assert abs(c["hfov"] - 39.6) < 0.1 and abs(c["aspect"] - 1600 / 900) < 1e-9
    assert abs(_dot(c["right"], c["up"])) < 1e-12

    box = ([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    assert bbox_error(box, box) < 1e-12
    assert bbox_error(box, ([0.0, 0.0, 0.05], [1.0, 1.0, 1.0])) > 0.001, \
        "a 5 cm pose error must fail the gate"
    print("FRAMING_SELF_TEST_OK")


def main():
    cam_path = OUT / "dragon_geo" / "cam_beauty.json"
    if not cam_path.exists():
        raise SystemExit(
            "missing out/dragon_geo/cam_beauty.json; run "
            "`blender --background --python tools/dragon_export.py -- "
            "--dump-camera` first")
    cam = json.loads(cam_path.read_text())
    cycles = camera_from_cycles(cam)
    pbrt = camera_from_pbrt(
        (OUT / "dragon_pbrt" / "dragon_beauty.pbrt").read_text())
    mitsu = camera_from_mitsuba(
        (OUT / "dragon_suite" / "mitsu_dragon.py").read_text())
    obj = OUT / "dragon_geo" / "dragon.obj"
    pose = bbox_error(obj_bbox(obj), cam["dragon_bbox"])
    print(f"obj pose vs CAM_beauty world bbox: {pose * 1000:.3f} mm")
    corners = obj_corners(obj)
    cams = [("cycles", cycles), ("pbrt", pbrt), ("mitsuba", mitsu)]
    boxes = {name: project_bbox(cam, corners) for name, cam in cams}
    print(f"{'engine':8s} {'hfov':>7s} {'aspect':>7s} "
          f"{'x0':>7s} {'x1':>7s} {'y0':>7s} {'y1':>7s}")
    for name, cam in cams:
        b = boxes[name]
        print(f"{name:8s} {cam['hfov']:7.3f} {cam['aspect']:7.4f} "
              f"{b[0]:7.4f} {b[1]:7.4f} {b[2]:7.4f} {b[3]:7.4f}")
    bad = []
    if pose > 0.001:
        bad.append(f"obj pose {pose * 1000:.1f} mm")
    for name, cam in cams[1:]:
        if abs(cam["hfov"] - cycles["hfov"]) > TOL_FOV:
            bad.append(f"{name} hfov {cam['hfov']:.3f}")
        if abs(cam["aspect"] - cycles["aspect"]) > 1e-3:
            bad.append(f"{name} aspect {cam['aspect']:.4f}")
        for k in range(4):
            if abs(boxes[name][k] - boxes["cycles"][k]) > TOL_BBOX:
                bad.append(f"{name} bbox[{k}] {boxes[name][k]:.4f}")
    if bad:
        print("FRAMING_FAIL " + "; ".join(bad))
        return 1
    print("FRAMING_OK")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        raise SystemExit(main())
