#!/usr/bin/env bash
# fetch_third_party.sh -- download the OPTIONAL prebuilt dependencies.
#
# THIS IS NOT NEEDED TO REPRODUCE THE PAPER.
#
# The solver and every number in the paper build and run with nothing but a C++
# compiler and CMake. The paper's timing target (bench), the cross-language parity
# check (parity), the field dump (dump) and every Python analysis tool link only
# the in-repo `caustic` and `two_medium` libraries. src/physics guards its MuJoCo
# include behind an if(EXISTS) test, so the physics target still builds without it.
#
# What this script fetches is only:
#
#   MuJoCo + Filament   the interactive/offscreen 3D viewer (viewer_interactive,
#                       viewer_offscreen). Without them those two targets are
#                       skipped and everything else builds.
#
# The reference renderers used for the comparison (PBRT-v4 for SPPM, Mitsuba 3,
# Blender + Cycles) are NOT fetched here: they are large external projects with
# their own build systems and licences, and are expected on PATH. See
# docs/EVIDENCE.md for the exact invocation used for every comparison render.
#
# Usage:  tools/fetch_third_party.sh [target-dir]     (default: ./third_party)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/third_party}"

MUJOCO_VER=3.14.0
FILAMENT_VER=1.77.2

MUJOCO_URL="https://github.com/google-deepmind/mujoco/releases/download/${MUJOCO_VER}/mujoco-${MUJOCO_VER}-windows-x86_64.zip"
FILAMENT_URL="https://github.com/google/filament/releases/download/v${FILAMENT_VER}/filament-v${FILAMENT_VER}-windows.tgz"

mkdir -p "$DEST"

say() { printf '  %s\n' "$*"; }

fetch() {
  local url="$1" out="$2"
  if [ -f "$out" ]; then
    say "already present: $(basename "$out")"
    return 0
  fi
  say "downloading $(basename "$out")"
  # -L follows the release redirect; --fail makes an HTML error page non-zero
  # rather than a quietly corrupt archive.
  curl -L --fail --retry 3 -o "$out.part" "$url"
  mv "$out.part" "$out"
}

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1" >&2; exit 1; }; }
need_cmd curl
need_cmd tar

echo "Fetching optional prebuilts into $DEST"
echo "(not required for the paper -- see the header of this script)"
echo

# ---- MuJoCo ---------------------------------------------------------------
fetch "$MUJOCO_URL" "$DEST/mujoco-${MUJOCO_VER}-windows.zip"
if [ ! -d "$DEST/mujoco-${MUJOCO_VER}" ]; then
  say "extracting MuJoCo"
  tmp="$(mktemp -d)"
  unzip -q "$DEST/mujoco-${MUJOCO_VER}-windows.zip" -d "$tmp"
  inner="$(find "$tmp" -maxdepth 1 -mindepth 1 -type d | head -n 1)"
  mv "$inner" "$DEST/mujoco-${MUJOCO_VER}"
  rm -rf "$tmp"
fi
say "MuJoCo  -> $DEST/mujoco-${MUJOCO_VER}"

# ---- Filament -------------------------------------------------------------
fetch "$FILAMENT_URL" "$DEST/filament-${FILAMENT_VER}-windows.tgz"
if [ ! -d "$DEST/filament-${FILAMENT_VER}" ]; then
  say "extracting Filament (about 5 GB uncompressed)"
  mkdir -p "$DEST/filament-${FILAMENT_VER}"
  tar -xzf "$DEST/filament-${FILAMENT_VER}-windows.tgz" -C "$DEST/filament-${FILAMENT_VER}"
fi
say "Filament -> $DEST/filament-${FILAMENT_VER}"

echo
echo "Done. Configure with:"
echo "  cmake -S . -B build"
echo "  cmake --build build --config Release"
