"""cam_projection_check.py -- do the Blender and PBRT cameras agree?

The brightness-percentile mask used by ripple_gifs --validate is not comparable
across renderers (each has a different lighting distribution), so it cannot
decide this. Instead project KNOWN world points through both camera models and
compare the pixel coordinates they predict.

Blender (tools/blender_scene.py):
    fan    = normalize(SUN.x, SUN.y)
    target = (fan.x*0.055, fan.y*0.055, GLASS_H*0.30)
    view   = (cos e cos a, cos e sin a, sin e)
    eye    = target + view*dist
    50 mm lens on a 36 mm sensor, sensor_fit AUTO -> horizontal fov fits width
    right  = cross(dir, up)  (right-handed)

PBRT-v4 (LookAt eye look up):
    dir   = normalize(look - eye)
    right = normalize(cross(up, dir))   <-- opposite handedness, image mirrored in X
    up'   = cross(dir, right)
    fov   is along the NARROWER image axis
"""
import math

SUN = (0.80, 0.42, -0.43)
GLASS_H = 0.090
W, H = 960, 540
AZ, ELEV, DIST, LENS = 110.0, 38.0, 0.62, 50.0
SENSOR = 36.0


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def norm(v):
    n = math.sqrt(sum(c*c for c in v))
    return tuple(c/n for c in v)


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cam_basis_blender():
    fan = norm((SUN[0], SUN[1], 0.0))
    target = (fan[0]*0.055, fan[1]*0.055, GLASS_H*0.30)
    a, e = math.radians(AZ), math.radians(ELEV)
    view = (math.cos(e)*math.cos(a), math.cos(e)*math.sin(a), math.sin(e))
    eye = tuple(t + v*DIST for t, v in zip(target, view))
    d = norm(sub(target, eye))
    r = norm(cross(d, (0.0, 0.0, 1.0)))        # right-handed
    u = cross(r, d)
    return eye, d, r, u, target


def cam_basis_pbrt():
    """Same eye/target, but PBRT's LookAt handedness."""
    eye, _, _, _, target = cam_basis_blender()
    d = norm(sub(target, eye))
    r = norm(cross((0.0, 0.0, 1.0), d))        # PBRT: cross(up, dir)
    u = cross(d, r)
    return eye, d, r, u, target


def project(P, eye, d, r, u, up_is_pbrt, w=W, h=H):
    v = sub(P, eye)
    xc, yc, zc = dot(v, r), dot(v, u), dot(v, d)
    # Blender: sensor fits the LARGER dim -> horizontal fov from lens
    if not up_is_pbrt:
        hfov = 2*math.atan((SENSOR/2)/LENS)
        vfov = 2*math.atan((SENSOR*h/w/2)/LENS)
    else:
        # PBRT fov is along the narrower axis (height here); width derived
        vfov = 2*math.atan((SENSOR*h/w/2)/LENS)
        hfov = 2*math.atan(math.tan(vfov/2)*w/h)
    nx = xc/(zc*math.tan(hfov/2))
    ny = yc/(zc*math.tan(vfov/2))
    return (nx+1)/2*w, (1-ny)/2*h, hfov, vfov


def main():
    eB, dB, rB, uB, tB = cam_basis_blender()
    eP, dP, rP, uP, tP = cam_basis_pbrt()
    print(f"eye (blender) {tuple(round(c,4) for c in eB)}")
    print(f"eye (pbrt)    {tuple(round(c,4) for c in eP)}")
    print(f"target        {tuple(round(c,4) for c in tB)}")
    print()

    pts = {
        "glass axis top  (0,0,0.090)": (0.0, 0.0, 0.090),
        "glass axis base (0,0,0)":     (0.0, 0.0, 0.0),
        "table corner (-.16,-.16)":    (-0.16, -0.16, 0.0),
        "table corner (+.16,-.16)":    (0.16, -0.16, 0.0),
        "table corner (+.16,+.16)":    (0.16, 0.16, 0.0),
        "table corner (-.16,+.16)":    (-0.16, 0.16, 0.0),
        "fan centre     (0.049,0.026)": (0.0487, 0.0256, 0.0),
    }
    print(f"{'world point':<30} {'blender px':>18} {'pbrt px (640x360)':>20}  match")
    print("-"*84)
    worst = 0.0
    for name, P in pts.items():
        bx, by, hf, vf = project(P, eB, dB, rB, uB, False)
        px, py, hf2, vf2 = project(P, eP, dP, rP, uP, True, 640, 360)
        # compare as fractions; PBRT's X is mirrored (see EVIDENCE 19.2)
        fbx, fby = bx/W, by/H
        fpx, fpy = px/640, py/360
        d = math.hypot(fbx - (1 - fpx), fby - fpy)
        worst = max(worst, d)
        print(f"{name:<30} {fbx:8.3f},{fby:7.3f}     "
              f"{1-fpx:8.3f},{fpy:7.3f}      "
              f"{'ok' if d < 0.01 else f'OFF {d:.3f}'}")
    print()
    print(f"fov: blender h {math.degrees(cam_basis_blender() and project(pts['glass axis base (0,0,0)'], eB,dB,rB,uB,False)[2]):.2f} deg"
          f" / v {math.degrees(project(pts['glass axis base (0,0,0)'], eB,dB,rB,uB,False)[3]):.2f} deg")
    print(f"worst fractional disagreement: {worst:.4f}")
    print("(PBRT fractions are shown X-mirrored, which is the documented 19.2 fix)")


if __name__ == "__main__":
    main()
