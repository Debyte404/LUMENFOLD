"""verify_refs2.py -- second pass: fix the mismatches and beat the 429s.

Pass 1 found that several references in the earlier draft resolve to a
DIFFERENT paper than intended (Veach's thesis -> a fission-matrix textbook,
Zeltner 2020 -> a different caustics paper, "bittner2020" -> a 2025 Russian
journal article), and Crossref rate-limited the rest. This pass re-queries with
corrected titles, longer sleeps, and retry-on-429 backoff, so the bibliography
is built from what Crossref actually returns.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

QUERIES = [
    ("airy1838",        "On the intensity of light in the neighbourhood of a caustic"),
    ("berry1980",       "Catastrophe optics morphologies of caustics and their diffraction patterns"),
    ("rubin1985",       "Optical properties of soda lime silica glasses"),
    ("hachisuka2008",   "Progressive photon mapping"),
    ("hanika2015",      "Manifold next event estimation"),
    ("arvo1994",        "The irradiance Jacobian for partially occluded polyhedral sources"),
    ("zeltner2020",     "Specular manifold sampling for rendering high-frequency caustics and glints"),
    ("mitchell1992",    "Illumination from curved reflectors Mitchell Hanrahan"),
    ("georgiev2012",    "Vertex connection and merging unifying photon mapping and path tracing"),
    ("jakob_mitsuba3",  "Mitsuba 3 renderer"),
    ("pbrt4",           "Physically based rendering from theory to implementation fourth edition"),
    ("veach1997",       "Robust Monte Carlo methods for light transport simulation"),
    ("whitney1955orig", "On singularities of mappings of Euclidean spaces I mappings of the plane into the plane"),
    ("lakshminarayanan2008", "Catastrophe optics caustics Airy diffraction"),
]

BASE = ("https://api.crossref.org/works?rows=4&select=title,author,issued,"
        "container-title,DOI,volume,page,type,publisher&query.bibliographic=")


def get(title, tries=5):
    for i in range(tries):
        try:
            r = urllib.request.Request(
                BASE + urllib.parse.quote(title),
                headers={"User-Agent": "caustics-refcheck/1.0 (mailto:research@example.org)"})
            with urllib.request.urlopen(r, timeout=45) as f:
                return json.load(f)["message"]["items"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 * (i + 1))
                continue
            raise
        except Exception:
            time.sleep(3)
    return []


def main():
    out = {}
    for key, title in QUERIES:
        items = get(title)
        print(f"=== {key} ===")
        if not items:
            print("   NO RESULT (rate-limited or absent)")
            continue
        best = None
        for it in items[:3]:
            t = (it.get("title") or ["?"])[0]
            ct = (it.get("container-title") or ["-"])[0]
            yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            au = it.get("author", [])
            first = au[0].get("family", "?") if au else "?"
            print(f"   {yr} {first:<14} | {t[:64]}")
            print(f"        {ct[:56]} v{it.get('volume')} p{it.get('page')} {it.get('DOI')}")
        it = items[0]
        au = it.get("author", [])
        out[key] = {
            "title": (it.get("title") or ["?"])[0],
            "container": (it.get("container-title") or ["-"])[0],
            "year": it.get("issued", {}).get("date-parts", [[None]])[0][0],
            "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in au],
            "doi": it.get("DOI"), "volume": it.get("volume"), "page": it.get("page"),
            "type": it.get("type"), "publisher": it.get("publisher"),
        }
        time.sleep(3)

    p = _ROOT + "/out/research/refs_verified2.json"
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1)
    print(f"\n{len(out)}/{len(QUERIES)} resolved -> {p}")


if __name__ == "__main__":
    main()
