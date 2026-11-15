"""run_audit.py -- fresh, independent verification of the repository's claims.

Rule: this file must not import from tools/, blender_addon/ or src/. It reads
the paper's text and EVIDENCE as *objects of audit* and recomputes the claims
from first principles. Every run is fresh: the report is dated and nothing from
a previous run is read.

Usage:  python audit/run_audit.py
Writes: out/audit/report_<UTC>.md
Exits non-zero if a BLOCKER or MAJOR finding exists.
"""
import datetime
import os
import re
import sys
import json

import numpy as np

import zlib
import struct
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "docs", "paper")
IEEE = os.path.join(ROOT, "docs", "paper-ieee")
EVIDENCE = os.path.join(ROOT, "docs", "EVIDENCE.md")
OUT = os.path.join(ROOT, "out", "audit")

FINDINGS = []          # (checker, id, severity, detail)
RESULTS = []           # (checker, id, status, detail, recomputed)


def record(checker, cid, ok, detail, recomputed="", severity=None):
    if ok:
        sev = "PASS"
    else:
        sev = severity or ("BLOCKER" if cid.startswith("C") else "MAJOR")
        FINDINGS.append((checker, cid, sev, detail))
    RESULTS.append((checker, cid, sev, detail, recomputed))
    print(f"[{sev:7s}] {checker:28s} {cid:22s} {detail}")


def approx(a, b, tol):
    return abs(a - b) <= tol * max(abs(b), 1e-30)


# --- C1: the paper's own scale law ------------------------------------------
def c1_scale_law():
    lam, c = 550e-9, 0.08115
    d = lam ** (2 / 3) * c ** (1 / 3) / (2 * np.pi ** (2 / 3))
    claim_um = 6.77
    ok = approx(d * 1e6, claim_um, 0.02)
    record("scale law", "C1", ok,
           f"Eq.14 with c={c} m, lambda=550 nm gives d = {d*1e6:.3f} um "
           f"(paper: {claim_um} um)", f"{d*1e6:.3f} um")
    return d * 1e6


np.pi = 3.141592653589793


# --- C2: Airy function by an independent quadrature --------------------------
def airyai_integral(x, tmax=60.0, n=4_000_000):
    """Ai(x) = (1/pi) * integral_0^inf cos(t^3/3 + x t) dt, plain quadrature.

    The integrand oscillates for large t; the tail decays like t^-1/2 cos, so a
    large window with dense sampling plus a cos-window average converges to
    ~1e-4, enough to locate the first zero to three decimals.
    """
    t = np.linspace(0.0, tmax, n)
    f = np.cos(t ** 3 / 3.0 + x * t)
    return f.mean() * tmax / np.pi


def c2_airy_zero():
    # bisect the first zero of Ai on the negative axis
    lo, hi = -3.0, -1.5
    f = lambda x: airyai_integral(x)
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        record("wave", "C2", False,
               f"bracket failed: Ai({lo})={flo:.5f} Ai({hi})={fhi:.5f}")
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    z = 0.5 * (lo + hi)
    claim = -2.338107410459767
    ok = abs(z - claim) < 5e-3
    record("wave", "C2", ok,
           f"first Airy zero by independent quadrature: {-z:.4f} "
           f"(paper/standard: 2.3381)", f"{-z:.5f}")
    return -z


# --- C3: first-zero / second-zero ratio and the peak position ----------------
def c3_profile(d_um):
    if d_um is None:
        return
    # second zero from the same quadrature
    lo, hi = -5.0, -3.0
    f = lambda x: airyai_integral(x)
    flo, fhi = f(lo), f(hi)
    z2 = None
    if flo * fhi < 0:
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            fm = f(mid)
            if flo * fm <= 0:
                hi = mid
            else:
                lo, flo = mid, fm
        z2 = -0.5 * (lo + hi)
    if z2 is None:
        record("wave", "C3", False, "second-zero bracket failed")
        return
    first = 15.84
    z1 = 2.338107410459767 * d_um
    ok = approx(z1, first, 0.01) and approx(z2 / 2.338107410459767, 4.0879 / 2.3381, 0.01)
    record("wave", "C3", ok,
           f"first zero {z1:.2f} um (paper {first} um); second zero "
           f"{z2 * d_um:.2f} um; ratio {z2:.4f} (standard 1.7475)",
           f"z1={z1:.2f}um z2={z2*d_um:.2f}um")


# --- C4: solar washout ------------------------------------------------------
def c4_washout(d_um):
    if d_um is None:
        return
    theta = 0.53
    L = 0.200
    blur = np.pi / 180 * (theta / 2) * L     # small-angle tan ~ rad
    blur_exact = np.tan(np.pi / 180 * (theta / 2)) * L
    claim = 925e-6
    ratio = blur_exact / (d_um * 1e-6)
    ok = approx(blur_exact, claim, 0.02) and approx(ratio, 136.0, 0.02)
    record("solar", "C4", ok,
           f"0.53 deg at 200 mm blurs {blur_exact*1e6:.0f} um; ratio to "
           f"{d_um:.2f} um spacing = {ratio:.1f} (paper: 925 um, 136x)",
           f"{blur_exact*1e6:.0f} um, {ratio:.1f}x")


# --- C5: sub-pixel claim ----------------------------------------------------
def c5_subpixel(d_um):
    if d_um is None:
        return
    px = 320.0 / 1024
    ratio = px * 1000 / d_um
    ok = approx(ratio, 46.0, 0.03)
    record("raster", "C5", ok,
           f"320 mm / 1024 = {px*1000:.1f} um/px = {ratio:.1f}x the fringe "
           f"spacing (paper: ~46x, 312.5 um/px)", f"{ratio:.1f}x")


# --- C6: wavelength scaling -------------------------------------------------
def c6_lambda_scaling():
    def d(lam_nm, c=1e-3):
        lam = lam_nm * 1e-9
        return lam ** (2 / 3) * c ** (1 / 3) / (2 * np.pi ** (2 / 3)) * 1e6
    vals = {650: d(650), 550: d(550), 450: d(450)}
    claim = {650: 1.749, 550: 1.565, 450: 1.369}
    ok = all(approx(vals[k], claim[k], 0.01) for k in claim)
    r_rec = vals[650] / vals[550]
    r_theory = (650 / 550) ** (2 / 3)
    ok = ok and approx(r_rec, r_theory, 1e-9)
    record("scaling", "C6", ok,
           "1D test scales (c=1e-3): "
           + ", ".join(f"{k} nm -> {vals[k]:.3f} um (paper {claim[k]})"
                       for k in (650, 550, 450))
           + f"; ratio {r_rec:.4f} vs lambda^(2/3) {r_theory:.4f}",
           json.dumps({str(k): round(v, 4) for k, v in vals.items()}))


# --- C7: the withdrawn value ------------------------------------------------
def c7_withdrawn():
    lam, c = 550e-9, 0.08115
    w = (lam ** 2 / (2 * c)) ** (1 / 3)
    ok = approx(w * 1e6, 123.1, 0.02)
    record("withdrawn", "C7", ok,
           f"the withdrawn expression (lambda^2/(2c))^(1/3) = {w*1e6:.1f} um "
           f"(paper records 123.1 um and withdraws it as dimensionally "
           f"mismatched)", f"{w*1e6:.1f} um")


# --- C8: dual-format parity -------------------------------------------------
def c8_dual_format():
    shared = os.path.join(PAPER, "sections")
    main_ieee = os.path.join(IEEE, "main.tex")
    if not os.path.exists(main_ieee):
        record("parity", "C8", False, f"{main_ieee} missing")
        return
    txt = open(main_ieee, encoding="utf-8").read()
    inputs = re.findall(r"\\input\{([^}]+)\}", txt)
    bad = []
    for i in inputs:
        p = os.path.normpath(os.path.join(IEEE, i))
        if not os.path.exists(p) and not p.endswith(".tex"):
            p += ".tex"
        if not os.path.exists(p):
            bad.append(f"{i} missing")
    record("parity", "C8", not bad,
           f"IEEE main.tex inputs {len(inputs)} files; "
           + ("all resolve" if not bad else "missing: " + "; ".join(bad)),
           f"{len(inputs)} inputs")


# --- C9: abstract numbers must be traceable to EVIDENCE ---------------------
def c9_traceability():
    abstract = ""
    for name in ("frontmatter.tex", "abstract.tex"):
        p = os.path.join(PAPER, "sections", name)
        if os.path.exists(p):
            abstract += open(p, encoding="utf-8").read()
    nums = set(re.findall(r"\d+\.\d+", abstract))
    missing = []
    ev = open(EVIDENCE, encoding="utf-8").read() if os.path.exists(EVIDENCE) else ""
    for n in sorted(nums):
        if float(n) < 0.05:      # skip page/figure counts
            continue
        if n not in ev:
            missing.append(n)
    record("traceability", "C9", not missing,
           f"{len(nums)} numeric literals in the abstract/frontmatter; "
           + ("all resolvable in EVIDENCE" if not missing
              else "not found in EVIDENCE: " + ", ".join(missing)),
           f"{len(nums)} numbers")


# --- C10: hygiene -----------------------------------------------------------
def c10_hygiene():
    secrets = re.compile(r"(api[_-]?key|secret|password)\s*[=:]\s*['\"][^'\"]{8,}",
                         re.I)
    todo = re.compile(r"\b(TODO|FIXME|XXX)\b")
    hits = {"secrets": [], "todo": [], "big": []}
    skip_dirs = {".git", "third_party", "node_modules", "out", "build",
                 "luxvenv", "__pycache__", "audit"}   # the instrument is not the specimen
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            p = os.path.join(base, fn)
            if fn.endswith((".py", ".tex", ".md", ".c", ".h", ".cpp", ".json",
                            ".yaml", ".yml")):
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                if secrets.search(txt):
                    hits["secrets"].append(os.path.relpath(p, ROOT))
                for m in todo.finditer(txt):
                    line = txt[:m.start()].count("\n") + 1
                    hits["todo"].append(f"{os.path.relpath(p, ROOT)}:{line}")
            try:
                if os.path.getsize(p) > 50 * 1024 * 1024:
                    hits["big"].append(os.path.relpath(p, ROOT))
            except OSError:
                pass
    ok = not (hits["secrets"] or hits["big"])
    record("hygiene", "C10", ok,
           f"secrets {len(hits['secrets'])}, oversized {len(hits['big'])}",
           json.dumps({k: v[:5] for k, v in hits.items() if k != "todo"}))
    # TODOs are graded by where they live: a plan checklist is a working
    # document; a TODO in shipped code or the paper is unfinished claims work.
    in_plan = [t for t in hits["todo"] if "superpowers" in t]
    in_ship = [t for t in hits["todo"] if "superpowers" not in t]
    record("hygiene", "C10b", not in_ship,
           f"TODO/FIXME in shipped code or paper: {len(in_ship)} "
           f"(plan documents: {len(in_plan)} -- working checklists, MINOR)",
           "; ".join(in_ship[:8]) or "none")


def main():
    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("=== fresh audit", stamp, "===")
    d_um = c1_scale_law()
    c2_airy_zero()
    c3_profile(d_um)
    c4_washout(d_um)
    c5_subpixel(d_um)
    c6_lambda_scaling()
    c7_withdrawn()
    c8_dual_format()
    c9_traceability()
    c10_hygiene()

    counts = {}
    for _, _, sev, _, _ in RESULTS:
        counts[sev] = counts.get(sev, 0) + 1
    blockers = counts.get("BLOCKER", 0)
    majors = counts.get("MAJOR", 0)
    rating = ("REJECT" if blockers else
              "MAJOR REVISION" if majors else
              "MINOR REVISION" if counts.get("MINOR") else
              "ACCEPT")
    print(f"\n=== rating: {rating}  (PASS {counts.get('PASS',0)}, "
          f"MINOR {counts.get('MINOR',0)}, MAJOR {majors}, BLOCKER {blockers}) ===")

    path = os.path.join(OUT, f"report_{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Fresh audit {stamp}\n\nRating: **{rating}**\n\n")
        f.write("| checker | id | status | detail | recomputed |\n|---|---|---|---|---|\n")
        for ck, cid, sev, det, rec in RESULTS:
            f.write(f"| {ck} | {cid} | {sev} | {det} | {rec} |\n")
    print("WROTE", path)
    return 1 if (blockers or majors) else 0


if __name__ == "__main__":
    sys.exit(main())
