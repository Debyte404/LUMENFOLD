"""control_corpus.py -- measure the same stylometry on known-human academic prose.

The manuscript's stylometry means nothing on its own. Reporting "burstiness -0.28"
invites a made-up reference band, which is how a fake threshold ends up in a report.
Instead compare against text that is certainly human-written and certainly the same
genre: the ABSTRACTS of the very papers this manuscript cites.

Source: Crossref (api.crossref.org), free, no key, and it returns the publisher's own
abstract where the publisher deposits one. Fetched via DOI, so the corpus is exactly
the works the paper cites rather than a convenient sample.

Writes docs/data/control_corpus.json so the numbers in the write-up are reproducible
without re-hitting the network.
"""
import glob
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from paper_forensics import sentences, words_of        # noqa: E402

BIB = os.path.join(ROOT, "docs", "paper", "refs.bib")
OUT = os.path.join(ROOT, "docs", "data", "control_corpus.json")


def dois():
    t = io.open(BIB, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"doi\s*=\s*[{\"]+([^}\"]+)", t):
        d = m.group(1).strip()
        if d and d not in out:
            out.append(d)
    return out


def strip_jats(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#x2013;", "-").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", s).strip()


def fetch(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={
        "User-Agent": "paper-forensics/1.0 (mailto:noreply@example.com)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.load(r)
    m = j.get("message", {})
    abstract = strip_jats(m.get("abstract", ""))
    title = (m.get("title") or [""])[0]
    return title, abstract


def openalex_batch(terms="global illumination rendering caustics", want=150,
                   per_page=200, before=2020):
    """Pull a same-field control corpus from OpenAlex.

    The cited-paper abstracts are the ideal control -- same works, same genre -- but only
    six publishers deposit an abstract in Crossref, giving ~60 sentences, which is too
    few to characterise a sentence-length distribution. arXiv rate-limited (429) and then
    timed out, so OpenAlex is the source.

    Restricted to work published BEFORE 2020: a control corpus of "human-written
    academic prose" is weakened if a chunk of it is itself LLM-assisted, and the
    post-2022 literature is exactly the part where that cannot be ruled out.
    """
    out = []
    for term in terms.split():
        if len(out) >= want:
            break
        url = ("https://api.openalex.org/works?filter=title_and_abstract.search:%s,"
               "publication_year:%d-%d,has_abstract:true&per-page=%d&mailto=forensics@example.com"
               % (urllib.parse.quote(term), 1970, before, per_page))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "paper-forensics/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                j = json.load(r)
        except Exception as e:
            print("    OpenAlex '%s' failed: %s" % (term, str(e)[:50]))
            continue
        for w in j.get("results", []):
            inv = w.get("abstract_inverted_index")
            if not inv:
                continue
            pos = {}
            for word, idxs in inv.items():
                for i in idxs:
                    pos[i] = word
            text = re.sub(r"\s+", " ", " ".join(pos[i] for i in sorted(pos))).strip()
            if len(words_of(text)) >= 60:
                out.append({"id": w.get("id", ""), "title": w.get("title") or "",
                            "year": w.get("publication_year"), "abstract": text})
        print("    OpenAlex '%s': %d abstracts so far" % (term, len(out)))
        time.sleep(0.5)
    return out[:want]


def main():
    ds = dois()
    print("  %d DOIs in refs.bib" % len(ds))
    got = []
    for d in ds:
        try:
            title, ab = fetch(d)
        except Exception as e:
            print("    %-34s FAILED (%s)" % (d, str(e)[:44]))
            continue
        # a Crossref abstract is often the JATS 'graphical abstract' stub; require prose
        if len(words_of(ab)) < 60:
            print("    %-34s no usable abstract (%d words)" % (d, len(words_of(ab))))
            continue
        got.append({"doi": d, "title": title, "abstract": ab})
        print("    %-34s %4d words  %s" % (d, len(words_of(ab)), title[:44]))
        time.sleep(0.4)

    print()
    print("  %d cited-paper abstracts retrieved" % len(got))

    print()
    print("  fetching same-field control from OpenAlex...")
    try:
        arx = openalex_batch()
    except Exception as e:
        print("    arXiv fetch failed: %s" % str(e)[:80])
        arx = []
    print("  %d OpenAlex abstracts" % len(arx))

    corpus = ([{"src": "cited:" + g["doi"], "title": g["title"], "abstract": g["abstract"]}
               for g in got]
              + [{"src": "arxiv:" + a["id"], "title": a["title"], "abstract": a["abstract"]}
                 for a in arx])
    if not corpus:
        print("  nothing retrieved -- cannot build a control corpus")
        return 1

    rows = []
    for g in corpus:
        ss = sentences(g["abstract"])
        w = words_of(g["abstract"])
        lens = [len(words_of(s)) for s in ss]
        if len(lens) < 3:
            continue
        mean = sum(lens) / len(lens)
        sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
        rows.append(dict(src=g["src"], title=g["title"], words=len(w),
                         sents=len(ss), mean=mean, sd=sd,
                         cv=sd / mean if mean else 0.0,
                         ttr=len(set(w)) / len(w),
                         semi=g["abstract"].count(";"),
                         dash=g["abstract"].count("-") ))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"n": len(rows), "rows": rows,
                   "abstracts": [{"src": g["src"], "title": g["title"],
                                  "abstract": g["abstract"]} for g in corpus]},
                  fh, indent=1)
    print("  wrote %s  (%d abstracts)" % (os.path.relpath(OUT, ROOT), len(rows)))
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
