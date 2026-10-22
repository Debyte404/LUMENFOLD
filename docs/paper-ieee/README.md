# IEEEtran edition

This is the IEEE two-column, numbered-citation edition of
**Wave-Corrected Caustics over Photon Splatting**. It is not a second paper:
the body, appendix, figures, bibliography, and every quantitative claim are the
same as the CGF edition in `../paper/`.

* `main.tex` - IEEEtran preamble and the shared-body input list.
* `sections/frontmatter.tex` - IEEE title/author/abstract/keywords only.

Build from the repository root:

```bat
python tools/build_paper_ieee.py
python tools/check_dual_format.py
```

The build must exit 0 with 0 overfull boxes. The parity check must print
`DUAL-FORMAT OK`. If you change a claim, change it in `../paper/sections/` (shared)
or, for frontmatter, in both frontmatters in the same commit.
