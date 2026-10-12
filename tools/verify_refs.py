"""verify_refs.py -- check every reference this paper cites against Crossref.

The earlier draft of this work carried a note saying its citation identifiers
had never been verified (the survey IP got HTTP 429). A paper cannot ship that
way, so this queries the Crossref REST API (no key required) for each intended
reference and reports what actually came back, so the bibliography is built
from returned metadata rather than from memory.
"""
import json
import time
import urllib.parse
import urllib.request


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

QUERIES = [
    ("airy1838",        "On the intensity of light in the neighbourhood of a caustic Airy"),
    ("berry1980",       "Catastrophe optics morphologies of caustics and their diffraction patterns"),
    ("whitney1955",     "On singularities of mappings of Euclidean spaces Whitney"),
    ("daimon2007",      "Measurement of the refractive index of distilled water near-infrared ultraviolet Daimon"),
    ("rubin1985",       "Optical properties of soda lime silica glasses Rubin"),
    ("jensen1996",      "Global illumination using photon maps Jensen"),
    ("hachisuka2008",   "Progressive photon mapping Hachisuka Ogaki Jensen"),
    ("veach1997",       "Robust Monte Carlo methods for light transport simulation Veach"),
    ("hanika2015",      "Manifold next event estimation Hanika Droske Fascione"),
    ("zeltner2020",     "Specular manifold sampling for rendering highly glossy and caustic scenes"),
    ("yan2018",         "Rendering specular microgeometry with wave optics Yan"),
    ("muller2017",      "Practical path guiding for efficient light transport simulation"),
    ("kouyoumjian1974", "A uniform geometrical theory of diffraction for an edge in a perfectly conducting surface"),
    ("musbach2013",     "Full wave modeling of light propagation and reflection Musbach"),
    ("cuypers2012",     "Reflectance model for diffraction Cuypers"),
    ("jakob2010",       "Mitsuba renderer Jakob"),
    ("pharr2023",       "Physically Based Rendering from theory to implementation Pharr Jakob Humphreys"),
    ("bittner2020",     "Vertex connection and merging Muller"),
    ("arvo1994",        "The irradiance Jacobian for partially occluded polyhedral sources Arvo"),
    ("mitchell1987",    "ray tracing caustics Mitchell"),
]


def q(title, rows=3):
    u = ("https://api.crossref.org/works?rows=%d&select=title,author,issued,"
         "container-title,DOI,volume,page,type&query.bibliographic=%s"
         % (rows, urllib.parse.quote(title)))
    r = urllib.request.Request(u, headers={"User-Agent": "caustics-paper-refcheck/1.0 (mailto:research@example.org)"})
    with urllib.request.urlopen(r, timeout=40) as f:
        return json.load(f)["message"]["items"]


def main():
    out = {}
    for key, title in QUERIES:
        try:
            items = q(title)
            if not items:
                print(f"[{key}] NO RESULT")
                continue
            it = items[0]
            t = (it.get("title") or ["?"])[0]
            ct = (it.get("container-title") or ["?"])[0]
            yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            au = it.get("author", [])
            first = f"{au[0].get('family','?')}" if au else "?"
            out[key] = {
                "title": t, "container": ct, "year": yr, "first_author": first,
                "doi": it.get("DOI"), "volume": it.get("volume"),
                "page": it.get("page"), "type": it.get("type"),
                "n_authors": len(au),
                "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in au],
            }
            print(f"[{key}] {yr} {first} | {t[:66]}")
            print(f"        {ct[:60]} | vol {it.get('volume')} p {it.get('page')} | {it.get('DOI')}")
        except Exception as e:
            print(f"[{key}] ERROR {type(e).__name__}: {e}")
        time.sleep(0.7)

    p = _ROOT + "/out/research/refs_verified.json"
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1)
    print(f"\n{len(out)}/{len(QUERIES)} resolved -> {p}")


if __name__ == "__main__":
    main()
