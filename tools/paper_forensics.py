"""paper_forensics.py -- measure the manuscript for AI tells and for copied text.

Three questions, each answered from the text rather than from an opinion:

1. DOES IT READ AS MACHINE-WRITTEN? Two independent lines of evidence:
   * the pattern scan (humanizer's 34 tells), and
   * STYLOMETRY. What detectors actually key on is uniformity: models pick the most
     probable continuation, so their sentence lengths cluster and their vocabulary
     repeats. Humans are bursty. So measure the sentence-length distribution, its
     standard deviation relative to the mean, the type-token ratio, paragraph variance
     and punctuation mix.

2. IS ANYTHING COPIED FROM ELSEWHERE? Real plagiarism detection needs a corpus we do
   not have, so this does the part that IS answerable: verbatim overlap against the
   paper's OWN other documents, which is self-plagiarism, and repeated passages inside
   the manuscript itself.

3. ARE THE QUOTED NUMBERS AND ATTRIBUTIONS CONSISTENT? Numbers that disagree between
   the abstract, the body and a table are the defect a reviewer finds first.

Usage:  python tools/paper_forensics.py [--self-sources ...] [--min-ngram 8]
"""
import argparse
import glob
import io
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from scan_ai_tells import prose, PATTERNS          # noqa: E402

SECTIONS = sorted(glob.glob(os.path.join(ROOT, "docs", "paper", "sections", "*.tex")))

# other documents this manuscript must not be recycling verbatim
DEFAULT_SELF = [
    "README.md", "docs/EVIDENCE.md", "docs/README.md", "tools/README.md",
    "docs/BLENDER_PLUGIN.md", "docs/PHYSICAL_TEST.md", "docs/CRITIQUE.md",
    "docs/archive/PAPER.md", "docs/archive/PAPER_PLAN.md",
]


def sentences(text):
    """Split prose into sentences, dropping tokens that are really markup."""
    t = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", t)
    out = []
    for p in parts:
        p = p.strip()
        # a sentence must have real words, not just identifiers/numbers
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", p)]
        if len(words) >= 4:
            out.append(p)
    return out


def words_of(text):
    return re.findall(r"[A-Za-z][A-Za-z'\-]+", text.lower())


def stylometry(text, label):
    ss = sentences(text)
    w = words_of(text)
    lens = [len(words_of(s)) for s in ss]
    if not lens:
        return None
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    sd = var ** 0.5
    # burstiness: +1 = wildly uneven, 0 = Poisson-like, -1 = perfectly uniform.
    # Language models sit low; human prose sits high.
    burst = (sd - mean) / (sd + mean) if (sd + mean) else 0.0
    ttr = len(set(w)) / len(w) if w else 0.0
    paras = [p for p in re.split(r"\n\s*\n", text) if len(words_of(p)) > 20]
    plens = [len(words_of(p)) for p in paras]
    pmean = sum(plens) / len(plens) if plens else 0
    pvar = (sum((x - pmean) ** 2 for x in plens) / len(plens)) ** 0.5 if plens else 0
    punct = Counter(ch for ch in text if ch in ",;:()?!")
    return dict(label=label, words=len(w), sents=len(ss),
                mean=mean, sd=sd, burst=burst, ttr=ttr,
                shortest=min(lens), longest=max(lens),
                para_mean=pmean, para_sd=pvar,
                semicolon=punct[";"], colon=punct[":"], qmark=punct["?"],
                dash=text.count("---") + text.count("\u2014"))


def shingles(text, n):
    w = words_of(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def windowed_ttr(text, win=100):
    """Type-token ratio on fixed-size windows, or None if the text is too short.

    TTR falls as a text gets longer, so a whole-paper TTR is not comparable with an
    abstract's. Average over windows of a common size instead, which is what makes the
    control corpus a control.

    Returning None (rather than 0.0) for a text shorter than one window matters: a 0.0
    would enter the control distribution as a real observation and drag its low
    percentiles to zero, making every comparison against it meaningless.
    """
    w = words_of(text)
    if len(w) < win:
        return None
    out, i = [], 0
    while i + win <= len(w):
        seg = w[i:i + win]
        out.append(len(set(seg)) / win)
        i += win
    return sum(out) / len(out) if out else None


def load_control():
    p = os.path.join(ROOT, "docs", "data", "control_corpus.json")
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as fh:
        j = json.load(fh)
    rows = []
    for a in j.get("abstracts", []):
        t = a["abstract"]
        ss = sentences(t)
        lens = [len(words_of(s)) for s in ss]
        if len(lens) < 4:
            continue
        mean = sum(lens) / len(lens)
        sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
        rows.append(dict(mean=mean, cv=sd / mean if mean else 0.0,
                         ttr=windowed_ttr(t),
                         semi=t.count(";") / max(len(words_of(t)), 1) * 1000))
    return rows


def pct(value, dist):
    """Where `value` sits in a distribution, as a percentile."""
    if not dist:
        return None
    return sum(1 for d in dist if d <= value) / len(dist) * 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-ngram", type=int, default=8)
    ap.add_argument("--self-sources", nargs="*", default=None)
    a = ap.parse_args()

    body = "\n\n".join(prose(p) for p in SECTIONS)
    per_file = {os.path.basename(p): prose(p) for p in SECTIONS}

    # ---------------------------------------------------------------- 1a. tells
    print("=" * 78)
    print("1. AI-TELL PATTERN SCAN")
    print("=" * 78)
    total_w = len(words_of(body))
    print("  %-26s %6s %10s" % ("tell", "hits", "per 10k"))
    flagged_total = 0
    for name, pat in PATTERNS:
        n = len(re.findall(pat, body, re.I))
        flagged_total += n
        print("  %-26s %6d %10.1f%s"
              % (name, n, n / max(total_w, 1) * 10000, "" if n == 0 else "  <--"))
    print("  %-26s %6d %10.1f" % ("TOTAL", flagged_total,
                                  flagged_total / max(total_w, 1) * 10000))
    print("  prose words: %d" % total_w)

    # ---------------------------------------------------------------- 1b. stylometry
    print()
    print("=" * 78)
    print("2. STYLOMETRY  (detectors key on uniformity; humans are bursty)")
    print("=" * 78)
    rows = [stylometry(t, n) for n, t in per_file.items()]
    rows = [r for r in rows if r]
    allr = stylometry(body, "WHOLE PAPER")
    allr["ttr_win"] = windowed_ttr(body, 100)
    allr["cv"] = allr["sd"] / allr["mean"]
    print("  %-24s %6s %6s %7s %7s %7s %6s"
          % ("section", "words", "sents", "mean/sd", "CV", "TTR150", "semi"))
    for r in rows:
        r["ttr_win"] = windowed_ttr(per_file[r["label"]], 100)
        r["cv"] = r["sd"] / r["mean"]
        print("  %-24s %6d %6d %4.1f/%-4.1f %7.3f %7.3f %6d"
              % (r["label"][:24], r["words"], r["sents"], r["mean"], r["sd"],
                 r["cv"], r["ttr_win"], r["semicolon"]))
    print("  " + "-" * 66)
    print("  %-24s %6d %6d %4.1f/%-4.1f %7.3f %7.3f %6d"
          % ("WHOLE PAPER", allr["words"], allr["sents"], allr["mean"], allr["sd"],
             allr["cv"], allr["ttr_win"], allr["semicolon"]))

    # ---- compared against a real control, not an invented band ------------------
    ctrl = load_control()
    print()
    if not ctrl:
        print("  NO CONTROL CORPUS -- run tools/control_corpus.py first.")
        print("  Without it these numbers cannot be interpreted: an absolute CV means")
        print("  nothing on its own, and inventing a threshold is how a fake result")
        print("  gets published.")
    else:
        means = sorted(c["mean"] for c in ctrl)
        cvs = sorted(c["cv"] for c in ctrl)
        ttrs = sorted(c["ttr"] for c in ctrl if c["ttr"] is not None)
        semis = sorted(c["semi"] for c in ctrl)
        print("  CONTROL CORPUS: %d abstracts, pre-2020 graphics literature" % len(ctrl))
        print("  (the works this paper cites + OpenAlex same-field, all pre-2020)")
        print()
        print("  %-22s %8s %10s %10s %10s" % ("metric", "paper", "control med", "control p10",
                                               "paper pct"))
        for label, val, dist in (("mean sentence len", allr["mean"], means),
                                 ("sentence-length CV", allr["cv"], cvs),
                                 ("TTR (100-word win)", allr["ttr_win"], ttrs),
                                 ("semicolons / 1k words",
                                  allr["semicolon"] / allr["words"] * 1000, semis)):
            med = dist[len(dist) // 2]
            p10 = dist[max(0, int(len(dist) * 0.10))]
            p90 = dist[min(len(dist) - 1, int(len(dist) * 0.90))]
            where = pct(val, dist)
            mark = ""
            if where is not None and (where < 5 or where > 95):
                mark = "  OUTSIDE the central 90%"
            print("  %-22s %8.3f %10.3f %10.3f %9.0f%%%s"
                  % (label, val, med, p10, where, mark))
        print()
        print("  A manuscript inside the control's central 90% on sentence length,")
        print("  variance and vocabulary looks like the control. Being OUTSIDE on")
        print("  sentence-length CV towards UNIFORM is the machine signature; towards")
        print("  VARIED is the human one.")

    # ---------------------------------------------------------------- 1c. em dashes
    print()
    print("=" * 78)
    print("3. EM DASHES IN CONTEXT  (the one tell that fired)")
    print("=" * 78)
    n = 0
    for name, t in per_file.items():
        for m in re.finditer(r"[^.\n]*---[^.\n]*", t):
            n += 1
            if n <= 14:
                s = re.sub(r"\s+", " ", m.group(0)).strip()
                print("  %-18s %s" % (name[:18], s[:96]))
    print("  ... %d total" % n)

    # ---------------------------------------------------------------- 2. duplication
    ng = a.min_ngram
    paper_sh = shingles(body, ng)
    print()
    print("=" * 78)
    print("4. INTERNAL DUPLICATION  (repeated %d-word passages inside the paper)" % ng)
    print("=" * 78)

    # Count raw shingles per SOURCE FILE so a repeat can be attributed, then merge
    # overlapping shingles into distinct passages. Counting raw shingles overstates the
    # problem badly: one repeated sentence produces ng overlapping hits, so "108
    # repeated 8-grams" was really a handful of passages.
    where = {}
    seen = Counter()
    for name, t in per_file.items():
        w = words_of(t)
        for i in range(len(w) - ng + 1):
            k = tuple(w[i:i + ng])
            seen[k] += 1
            where.setdefault(k, set()).add(name)

    reps = {k: v for k, v in seen.items() if v > 1}
    # group shingles that overlap into one passage
    groups, used = [], set()
    for k in sorted(reps):
        if k in used:
            continue
        grp = [k]
        used.add(k)
        # extend while the next shingle overlaps this one
        cur = k
        while True:
            nxt = None
            for k2 in reps:
                if k2 in used:
                    continue
                # shares ng-1 words at the tail/head
                if k2[1:] == cur[:-1] or cur[1:] == k2[:-1]:
                    nxt = k2
                    break
            if nxt is None:
                break
            grp.append(nxt)
            used.add(nxt)
            cur = nxt
        groups.append(grp)

    print("  %d shingles repeat, merging to %d distinct passage(s)"
          % (len(reps), len(groups)))
    for grp in groups[:8]:
        words_ = " ".join(grp[0])
        places = sorted(set().union(*[where[k] for k in grp]))
        tag = "abstract/body (normal)" if any("frontmatter" in p for p in places) \
            else "SAME CONTEXT -- check" if len(places) == 1 else "cross-section"
        print("    x%d  %-26s %s" % (seen[grp[0]], tag, words_[:62]))
        print("        in: %s" % ", ".join(places))

    # ---------------------------------------------------------------- 3. self-plagiarism
    # ---------------------------------------------------------------- 3b. external copy
    print()
    print("=" * 78)
    print("6. VERBATIM OVERLAP WITH THE FETCHED LITERATURE")
    print("=" * 78)
    ctrl_p = os.path.join(ROOT, "docs", "data", "control_corpus.json")
    if not os.path.exists(ctrl_p):
        print("  no control corpus -- run tools/control_corpus.py first")
    else:
        with io.open(ctrl_p, encoding="utf-8") as fh:
            corpus = json.load(fh).get("abstracts", [])
        # a LONGER n-gram than the self-check: 12 words of verbatim agreement with a
        # published paper is not a coincidence, whereas 8 is common technical phrasing
        ext_n = 12
        paper_ext = shingles(body, ext_n)
        worst_run, worst_src, hits = 0, None, 0
        for entry in corpus:
            theirs = shingles(entry["abstract"], ext_n)
            shared = paper_ext & theirs
            if shared:
                hits += 1
                print("  %-52s %d shared %d-grams"
                      % (entry["title"][:52], len(shared), ext_n))
                for k in list(shared)[:1]:
                    print("      %s" % " ".join(k))
        print()
        print("  %d of %d fetched abstracts share any %d-word run with the paper"
              % (hits, len(corpus), ext_n))
        print("  (shared runs here are expected to be technical terms and cited names;")
        print("   a run of a full sentence in a row would not be)")

    print()
    print("=" * 78)
    print("5. SELF-PLAGIARISM  (verbatim overlap with this project's own documents)")
    print("=" * 78)
    sources = a.self_sources if a.self_sources is not None else DEFAULT_SELF
    worst = 0
    for rel in sources:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            other = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if rel.endswith(".md"):
            # strip fenced blocks, tables and long code so we compare PROSE
            other = re.sub(r"(?s)```.*?```", " ", other)
            other = "\n".join(l for l in other.splitlines()
                              if not l.lstrip().startswith(("|", "#", "-", "*", "  ")))
        theirs = shingles(other, ng)
        shared = paper_sh & theirs
        frac = len(shared) / max(len(paper_sh), 1) * 100
        worst = max(worst, frac)
        if shared:
            print("  %-34s %5d shared %d-grams  (%.2f%% of the paper)"
                  % (rel, len(shared), ng, frac))
            for k in list(shared)[:2]:
                print("      e.g. %s" % " ".join(k)[:88])
        else:
            print("  %-34s clean" % rel)
    print()
    print("  worst overlap with any own document: %.2f%% (verbatim %d-word runs)"
          % (worst, ng))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
