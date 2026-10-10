"""physical_predictions.py — the numbers a real photograph has to match.

Everything in this project so far compares simulation to simulation. This prints
the quantities that a physical experiment can actually check, expressed in forms
that do not require knowing the camera: distances as multiples of the glass
radius, angles in degrees, colour separation as a percentage.

These are the falsifiable predictions. If a photograph of the same scene puts the
caustic somewhere else, at a different azimuth, or with the colour separation
running the other way, the simulation is wrong.

Run:  python tools/physical_predictions.py
"""
import os
import struct
import zlib

import numpy as np

OUT = "D:/ValueProjects/caustics/out"
R_GLASS = 0.035
SUN = np.array([0.80, 0.42, -0.43])
SUN = SUN / np.linalg.norm(SUN)
SUN_AZ = np.degrees(np.arctan2(SUN[1], SUN[0]))
SUN_ELEV = np.degrees(np.arcsin(-SUN[2]))


def read_png16(path):
    d = open(path, "rb").read()
    pos, idat, w, h = 8, b"", None, None
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 * 2
    out = np.zeros((h, w, 3), np.uint16)
    p = 0
    for y in range(h):
        p += 1
        out[y] = np.frombuffer(raw[p:p + stride], dtype=">u2").reshape(w, 3)
        p += stride
    return out.astype(np.float32) / 65535.0 * 16.0


def main():
    f = read_png16(f"{OUT}/caustic_wavy.png")      # the actual bake
    H, W, _ = f.shape
    yy, xx = np.mgrid[0:H, 0:W]
    X = (xx / (W - 1) - 0.5) * 320.0               # mm, patch is 320 mm wide
    Y = (0.5 - yy / (H - 1)) * 320.0
    R = np.hypot(X, Y)
    AZ = np.degrees(np.arctan2(Y, X))

    print("=" * 74)
    print("PREDICTIONS for a physical check")
    print("=" * 74)
    print(f"scene: glass outer radius {R_GLASS*1000:.1f} mm, "
          f"water line 59.4 mm, rippled surface")
    print(f"       sun {SUN_ELEV:.1f} deg elevation, azimuth {SUN_AZ:+.1f} deg")
    print()
    print("1. WHERE THE CAUSTIC LANDS  (measure from the glass centre)")
    lum = f.mean(axis=2)
    m = lum >= np.percentile(lum, 99.9)
    print(f"   brightest 0.1% of the patch, centroid:")
    print(f"     radius  {R[m].mean()/1000/R_GLASS:.2f} x glass radius "
          f"({R[m].mean():.1f} mm)")
    print(f"     azimuth {AZ[m].mean():+.1f} deg  "
          f"(sun azimuth {SUN_AZ:+.1f} deg, so "
          f"{AZ[m].mean()-SUN_AZ:+.1f} deg of it)")
    print(f"   the caustic spans {AZ[m].min():+.0f} to {AZ[m].max():+.0f} deg "
          f"and {R[m].min():.0f} to {R[m].max():.0f} mm")
    print()
    print("2. THE FOLD - the sharp bright edge the geometric envelope predicts")
    # the fold is where the field is brightest; report the radius of the peak
    i = np.unravel_index(np.argmax(f), f.shape[:2])
    print(f"   peak at radius {np.hypot(X[i], Y[i])/1000/R_GLASS:.2f} x glass radius, "
          f"azimuth {np.degrees(np.arctan2(Y[i], X[i])):+.1f} deg")
    print("   (a closed-form check of this for a solid cylinder is in")
    print("    tools/analytic_caustic.py: agreement there was 0.1 mm)")
    print()
    print("3. DISPERSION - which colour lands farther out")
    radii = {}
    for c, ch in enumerate("RGB"):
        v = f[:, :, c]
        mm_ = v >= np.percentile(v, 99.9)
        radii[ch] = R[mm_].mean()
    print(f"   red   {radii['R']:.1f} mm   green {radii['G']:.1f} mm   "
          f"blue  {radii['B']:.1f} mm")
    print(f"   separation R-B = {radii['R']-radii['B']:.1f} mm = "
          f"{100*(radii['R']-radii['B'])/radii['B']:.1f}% of the radius")
    print("   ORDER: red must be FARTHER than blue (red has the lower index and")
    print("   therefore refracts less). Reversed order refutes the model.")
    print()
    print("4. WHAT THE PHOTO MUST BE TAKEN WITH TO CHECK ANY OF THIS")
    print("   - the caustic must NOT be clipped: expose for the caustic, or")
    print("     bracket exposures and merge to HDR. A blown caustic still allows")
    print("     checks 1-3 (geometry and colour order) but not intensities.")
    print("   - one length reference in the frame (a ruler, or the glass")
    print("     diameter measured with calipers) fixes the mm mapping")
    print("   - the light direction must be known: sun elevation and azimuth")
    print("     from a timestamp and location, or a lamp at a measured position")
    print()
    print("=" * 74)


if __name__ == "__main__":
    main()
