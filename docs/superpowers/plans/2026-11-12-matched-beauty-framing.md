# Matched-Beauty Framing Correction Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute inline with TDD.

**Goal:** Make the four-engine dragon beauty comparison genuinely matched (same eye, target, 39.6 deg horizontal FOV, 16:9, one 2.4 deg sun), re-render, re-measure, rebuild the figure, record and commit.

**Spec:** this plan; authority for numbers is `docs/EVIDENCE.md` sections 26-29 and the camera dump below.

## Verified facts

- `CAM_beauty`: 50 mm, sensor 36, fit AUTO, 16:9 -> 39.6 deg horizontal, 22.9 deg vertical; camera up = world +Z.
- Shared OBJ is Z-up (bbox z 0.994 > y 0.703 > x 0.444).
- PBRT `fov` is measured on the narrower film axis (pbrt-v4 `cameras.cpp` L495-527), so `fov 39.6` at 16:9 is ~65 deg horizontal.
- PBRT's `LookAt` builds a left-handed frame; a two-sphere probe (world +X image-left in PBRT, image-right in Mitsuba) and the pbrt-v2 release notes / pbrt-v4 issue #444 confirm it. `Scale -1 1 1` restores the handedness.
- Mitsuba `fov` at 640x640 is 40 deg on both axes; the figure squashes the square to 16:9.
- Mitsuba sphere sun at 5.9 m has inverse-square falloff; Cycles SUN does not.
- CAM_beauty's actual optical axis is 1.36 deg (6% of the frame) off the nominal (0,0,0.1), and its eye is 4 mm off the nominal; the reference must be read from the blend dump.

## Global constraints

- One change per commit; EVIDENCE before summaries.
- No paper edits (dragon is not in `docs/paper`).
- A miss is recorded, not tuned to pass.
- CSV is append-only; superseded rows stay.

## Tasks

### Task 1: Revert the up-vector experiment
Files: `tools/dragon_suite.py` (`run_mitsuba`, `_mitsu_scene`).
Test: `python tools/dragon_suite.py --check` -> `DRAGON_SUITE_CHECK_OK`; `grep "up=\[0, 1, 0\]"` empty.
Commit: folded into the final commit.

### Task 2: FOV helpers
Files: `tools/dragon_suite.py`.
Test: `pbrt_fov_from_hfov(39.6, 16/9) == 22.91`, round-trip returns 39.6.

### Task 3: Correct PBRT beauty FOV
Files: `tools/dragon_suite.py` (`run_pbrt_beauty`).
Test: generated `.pbrt` contains fov 22.91, reconstructs 39.6 horizontal, and starts with `Scale -1 1 1`.

### Task 4: Correct Mitsuba film, FOV, sun, ground height
Files: `tools/dragon_suite.py` (`_mitsu_scene`, `run_mitsuba_beauty`, CLI lambda).
Test: generated script has `fov 39.6`, `fov_axis 'x'`, 1600x900; sun centre/radius scaled by 100.

### Task 5: Calibration gate and notes
Files: `tools/dragon_suite.py`.
Test: a forced 50% calibration error raises `SystemExit`.

### Task 6: Camera dump and framing check
Files: `tools/dragon_export.py` (new `--dump-camera`, writes eye/axis for the suite), new `tools/check_dragon_framing.py`.
Test: `python tools/check_dragon_framing.py --self-test` -> `FRAMING_SELF_TEST_OK`; `python tools/check_dragon_framing.py` -> `FRAMING_OK`; a square Mitsuba scene or the old fov -> exit 1.

### Task 7: Re-render PBRT and Mitsuba, append CSV rows
Files: `docs/data/dragon_suite.csv`, `out/`.
Test: new rows present; framing check passes; fan verdicts re-read.

### Task 8: Rebuild the figure without distortion
Files: `tools/make_dragon_beauty_figure.py`.
Test: aspect assertion raises on a square input; figure regenerated.

### Task 9: Record EVIDENCE section 30 and supersede pointers
Files: `docs/EVIDENCE.md`.
Test: `python tools/check_paper.py` exits 0.

### Task 10: Commit
Message: `Correct PBRT and Mitsuba framing in the matched beauty rig`.

## Revisions (2026-11-12, during execution)

- The review found the shared OBJ was exported with Blender's default Y-up
  conversion, so `dragon.obj` was 90 deg about X away from the Cycles object.
  Every PBRT and Mitsuba render to date showed a lying dragon, and the Camera
  framing check passed because it projected the same wrong OBJ for all engines.
  `tools/dragon_export.py` now writes `up_axis='Z'` (world coordinates), and
  `cam_beauty.json` records the dragon world bbox; `check_dragon_framing.py`
  fails if the OBJ pose differs by more than 1 mm. Re-ran the referee and the
  ortho score on the corrected mesh (see EVIDENCE section 30).
- The beauty re-render uses reduced budgets by decision: PBRT 128spp at
  2560x1440, Mitsuba 512spp at 1200x675. Both are recorded in the CSV and the
  figure titles; the fan/no-fan verdicts do not depend on the extra samples.
- The calibration target now uses the lower half of the Cycles frame (the
  ground), and the final EXR's ground is gated against it; the previous
  `np.sort(lin)[:n//2]` took the upper half (background).
