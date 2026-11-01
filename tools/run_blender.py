"""run_blender.py -- resolve the Blender executable, then exec Blender.

Lookup order: BLENDER_EXE env, Steam 5.2 default install, `blender` on PATH.
Usage:  python tools/run_blender.py --background --python tools/test_addon.py
Forwards every argument after this script to Blender. Prints the chosen exe
to stderr so logs record which Blender ran.
"""
import os
import shutil
import subprocess
import sys

CANDIDATES = [
    os.environ.get("BLENDER_EXE", ""),
    r"E:\SteamLibrary\steamapps\common\Blender\blender.exe",
]


def resolve():
    for c in CANDIDATES:
        if c and os.path.exists(c):
            return c
    p = shutil.which("blender")
    if p:
        return p
    raise SystemExit("no Blender found: set BLENDER_EXE")


def main():
    exe = resolve()
    print(f"BLENDER_EXE={exe}", file=sys.stderr)
    r = subprocess.run([exe] + sys.argv[1:])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
