"""production_renders.py — the deliverable renders.

Three passes, all with the calibrated studio rig (key sun + fill + rim, gradient
environment, procedural normal map on the table):

  stills/     six angles at 2048x1280, 1024 spp, denoised
  turntable/  96 frames orbiting the glass, 960x540
  ripple/     72 frames of the water surface and its caustic animating together:
              the caustic is RE-BAKED every frame with the matching wave phase,
              which is the thing a path tracer cannot do cheaply - a
              deterministic caustic that changes with the geometry

Videos are encoded with ffmpeg at the end. Every frame's bake and render time is
written to a log so the cost of the animation is on the record rather than
implied.

Run:  python tools/production_renders.py [--skip-stills] [--skip-videos]
"""
import argparse
import os
import subprocess
import time

ROOT = "D:/ValueProjects/caustics"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
FFMPEG = "ffmpeg"
SCENE = f"{ROOT}/tools/blender_scene.py"
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
OUT = f"{ROOT}/out"
FRAMES = f"{OUT}/frames"

# the calibrated studio look (see EVIDENCE 13): real solar size, cool gradient
# environment, key/fill/rim
STUDIO = ["--studio", "--sun", "6.5", "--world", "0.55", "--gain", "0.25",
          "--sun-angle", "0.53", "--clamp-indirect", "0"]

ANGLES = [
    (28, 20, 0.34), (75, 16, 0.32), (120, 26, 0.36),
    (200, 18, 0.34), (265, 24, 0.33), (320, 14, 0.35),
]


def bake(phase, path, res=1024):
    cmd = [EXE, "--res", str(res), "--n", "400", "--ssaa", "1",
           "--wave-t", f"{phase:.6f}",
           "--out", f"{OUT}/_throw.png", "--dump-caustic", path]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if not os.path.exists(path):
        raise RuntimeError(f"bake failed: {p.stderr[-300:]}")
    return time.time() - t0


def render(caustic, path, samples, w, h, extra):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", caustic, "--out", path, "--samples", str(samples),
           "--w", str(w), "--h", str(h)] + extra + STUDIO
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if not os.path.exists(path):
        raise RuntimeError(f"render failed: {p.stderr[-400:]}")
    return time.time() - t0


def encode(pattern, out, fps=24, crf=18):
    cmd = [FFMPEG, "-y", "-framerate", str(fps), "-i", pattern,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
           "-movflags", "+faststart", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    ok = os.path.exists(out)
    print(f"  ffmpeg -> {out} {'OK' if ok else 'FAILED'}")
    if not ok:
        print(p.stderr[-500:])
    return ok


def stills():
    os.makedirs(f"{OUT}/stills", exist_ok=True)
    caustic = f"{OUT}/caustic_wavy.png"
    for i, (az, elev, dist) in enumerate(ANGLES):
        path = f"{OUT}/stills/angle{i}_az{az}.png"
        dt = render(caustic, path, 1024, 2048, 1280,
                    ["--az", str(az), "--elev", str(elev), "--dist", str(dist)])
        print(f"  still {i} az={az:>3} elev={elev:>2}  {dt:6.1f}s -> {path}")


def video(name, n, w, h, samples, animate_waves, cam_fn):
    d = f"{FRAMES}/{name}"
    os.makedirs(d, exist_ok=True)
    log = []
    for f in range(n):
        phase = (2 * 3.141592653589793 * f / n) if animate_waves else 0.0
        cb = f"{OUT}/caustic_f{f:04d}.png"
        tb = bake(phase, cb, res=768) if animate_waves else 0.0
        if not animate_waves:
            cb = f"{OUT}/caustic_wavy.png"
        extra = cam_fn(f, n) + ["--wave-t", f"{phase:.6f}"]
        tr = render(cb, f"{d}/f{f:04d}.png", samples, w, h, extra)
        log.append((f, tb, tr))
        if f % 12 == 0 or f == n - 1:
            print(f"    [{name}] frame {f+1}/{n}  bake {tb:4.2f}s  render {tr:5.1f}s")
        if animate_waves and os.path.exists(cb):
            os.remove(cb)
    mp4 = f"{OUT}/{name}.mp4"
    encode(f"{d}/f%04d.png", mp4)
    tb = sum(l[1] for l in log)
    tr = sum(l[2] for l in log)
    print(f"  {name}: {n} frames  bake {tb:.1f}s  render {tr:.1f}s  total {tb+tr:.1f}s")
    return mp4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-stills", action="store_true")
    ap.add_argument("--skip-videos", action="store_true")
    args = ap.parse_args()
    os.makedirs(FRAMES, exist_ok=True)

    if not args.skip_stills:
        print("=== stills: six angles, 2048x1280, 1024 spp ===")
        stills()

    if not args.skip_videos:
        print("=== turntable: 96 frames, 960x540, 384 spp ===")
        video("turntable", 96, 960, 540, 384, False,
              lambda f, n: ["--az", f"{360.0*f/n:.2f}", "--elev", "22",
                            "--dist", "0.34"])
        print("=== ripple animation: caustic re-baked per frame ===")
        video("ripple", 72, 960, 540, 384, True,
              lambda f, n: ["--az", "35", "--elev", "19", "--dist", "0.32"])


if __name__ == "__main__":
    main()
