# Repository Audit Protocol (adversarial, fresh-harness, iterative)

**Purpose.** Act as our own worst reviewer. Every claim in the repository is
re-derived by an *independent* implementation that shares no code with the thing
it audits. Each session is fresh: no cached results, no reuse of the previous
review's outputs, no reuse of `tools/` or `blender_addon/` for verification.

**Scope of the audit.** Paper (CGF + IEEE editions), EVIDENCE, all `tools/`,
`blender_addon/`, `src/`, figures, README/docs, and the claim ledger that links
them.

## Rules

1. **Independence.** `audit/` may not import from `tools/`, `blender_addon/` or
   `src/`. It may read their *outputs* and the paper's *text* as objects of
   audit. Any checker that calls project code is invalid and must be rewritten.
2. **Freshness.** Each run writes a new dated report and must not read a
   previous one. A checker may not be "fixed" to pass; either the claim or the
   code changes, or the checker is shown to be wrong by an independent argument.
3. **Claims are the unit.** Every quantitative claim gets an id, a value, a unit,
   the EVIDENCE section that grounds it, the tool that produced it, and the
   independent recomputation that verifies it.
4. **Adversarial framing.** For every claim, try to break it: wrong exponent,
   unit mismatch, silent unit conversion, circular verification (tool checks
   itself), cherry-picked configuration, missing negative result, overstated
   generality.
5. **Severity.**
   - `BLOCKER` — a claim is false, unreproducible, or contradicts the evidence.
   - `MAJOR` — a claim is true but the support is missing/circular, or a figure
     caption claims something the body does not.
   - `MINOR` — imprecision, ambiguous wording, stale number, missing units.
   - `NIT` — style.
6. **Pass bar.** Zero `BLOCKER`, zero `MAJOR`, and every `MINOR` either fixed or
   recorded as an accepted, dated deferral in EVIDENCE.
7. **Fresh re-review.** After fixes, a *new* session re-runs the whole protocol
   from scratch. Reviewing a diff is not a review.

## Checker set (v1)

Each checker is standalone: given the repo path, it recomputes from first
principles and prints `PASS/FAIL <id> <detail>`.

| id | claim | independent method |
|---|---|---|
| C1 | fringe scale 6.77 µm | evaluate the paper's own Eq. 14 `d = λ^{2/3} c^{1/3} / (2π^{2/3})` with λ=550 nm, c=0.08115 m |
| C2 | first Airy zero 15.84 µm | own quadrature of `Ai(x) = (1/π)∫cos(t³/3+xt)dt`; locate the first zero to 1e-6 |
| C3 | `|Ai|²` first maximum/zero ratio and peak | own quadrature + golden-section maximisation |
| C4 | solar washout 136× | 925 µm blur ÷ d, both recomputed |
| C5 | 46× sub-pixel at 1024² | 320 mm / 1024 ÷ d |
| C6 | λ^{2/3} scaling (1.749/1.565/1.369 µm) | recompute the three channel scales from Eq. 14 at c=1e-3 |
| C7 | withdrawal of 123.1 µm | evaluate the withdrawn `(λ²/(2c))^{1/3}` and confirm it differs and is dimensionally wrong |
| C8 | dual-format parity | shared body sections byte-identical; frontmatter claim sets equal |
| C9 | claim traceability | every number in the abstract resolvable in EVIDENCE |
| C10 | hygiene | secrets, TODO/FIXME stubs, files over 50 MB, licence present |

Checkers that require rendering (addon end-to-end, figure regeneration,
reproducibility of the cost table) are **not** in v1: they are listed as open
items and must be added before the protocol can pass a release review, because
a paper whose numbers cannot be re-run is not auditable.

## Iteration loop

```
for session in 1..N:
    run audit/run_audit.py            # fresh, no state
    if no BLOCKER and no MAJOR: stop
    fix the repository (not the checker)
    log the change in EVIDENCE with the date
```

## Reporting

`out/audit/report_<date>.md` holds the table of checkers, severities, the
status rating, and the open items. The rating is:

- `REJECT` — any BLOCKER.
- `MAJOR REVISION` — any MAJOR.
- `MINOR REVISION` — only MINOR/NIT.
- `ACCEPT` — clean on a fresh run.

## Known open items at v1 (must be closed before a release review)

1. Rendering-level checks: re-render the shipped panels from the recorded
   commands and compare against the shipped numbers.
2. Cost table reproducibility on a second machine.
3. Figure regeneration: `make_all_figures.py` hashes vs the committed PDFs.
4. The addon user flow executed by a fresh script (not `tools/test_addon_mesh.py`).
5. Independent reimplementation of the fold/Airy band solver in a different
   language or library, compared on the same scene.
