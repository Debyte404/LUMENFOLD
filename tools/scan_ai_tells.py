"""scan_ai_tells.py -- find AI-writing tells in the paper sources.

A first version of this counted 655 em dashes and was wrong: it was counting the
`%--------` comment rules LaTeX sources are full of, not prose. That is the same
class of estimator error the paper itself is about (a statistic measuring the
file rather than the thing it is supposed to measure), so this version strips
comments, verbatim blocks and table/algorithm bodies before scanning, and
reports the prose word count alongside every rate so the rates are checkable.
"""
import glob
import io
import re

SECTIONS = "D:/ValueProjects/caustics/docs/paper/sections"


def prose(path):
    s = io.open(path, encoding="utf-8").read()
    # drop environments whose contents are data, not prose
    s = re.sub(r"(?s)\\begin\{(verbatim|tabular|tabularx|algorithmic|equation|align)\}"
               r".*?\\end\{\1\}", " ", s)
    # drop comment lines (this is what inflated the em-dash count)
    s = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("%"))
    # drop inline commands but keep their braced text
    s = re.sub(r"\\[a-zA-Z@]+\*?", " ", s)
    s = re.sub(r"[{}~$]", " ", s)
    return s


PATTERNS = [
    ("em dash",              r"---|\u2014"),
    ("significance inflation", r"\b(testament|pivotal|crucial|vital|underscoring|"
                               r"evolving landscape|indelible|deeply rooted)\b"),
    ("superficial -ing",     r"\b(highlighting|underscoring|emphasizing|showcasing|"
                             r"reflecting|contributing to|ensuring|fostering)\b"),
    ("promotional",          r"\b(boasts?|vibrant|profound|groundbreaking|renowned|"
                             r"breathtaking|stunning|seamless|state of the art)\b"),
    ("vague attribution",    r"\b(experts? (argue|believe)|observers? (have )?noted|"
                             r"it is widely (believed|accepted))\b"),
    ("AI vocabulary",        r"\b(delve|intricate|interplay|tapestry|realm|myriad|"
                             r"multifaceted|leverage|utilize)\b"),
    ("copula avoidance",     r"\b(serves? as|stands? as|functions? as)\b"),
    ("negative parallelism", r"\b(not (just|only|merely) [^.]{1,60}\bbut\b)\b"),
    ("persuasive authority", r"\b(the real question|at its core|what really matters|"
                             r"the deeper issue|the heart of)\b"),
    ("signposting",          r"\b(let'?s (dive|explore|look|break)|here'?s what you need|"
                             r"without further ado)\b"),
    ("filler",               r"\b(in order to|due to the fact that|it is important to note|"
                             r"it should be noted)\b"),
    ("excessive hedging",    r"\b(could potentially|might possibly|it could be argued)\b"),
    ("generic conclusion",   r"\b(the future (looks|is) bright|exciting times|"
                             r"toward excellence)\b"),
    ("adverb opener",        r"(?m)^(Notably|Importantly|Crucially|Interestingly|"
                             r"Essentially|Ultimately|Significantly),"),
    ("tailing negation",     r",\s*no \w+\.\s*$"),
]


def main():
    files = sorted(glob.glob(f"{SECTIONS}/*.tex"))
    texts = {f.split("/")[-1]: prose(f) for f in files}
    total_words = sum(len(t.split()) for t in texts.values())

    print(f"{'tell':<26} {'hits':>5}  {'per 10k words':>13}")
    print("-" * 50)
    grand = 0
    for label, pat in PATTERNS:
        hits = []
        for name, t in texts.items():
            hits += [(name, m.group(0)) for m in re.finditer(pat, t, re.I)]
        grand += len(hits)
        rate = 10000 * len(hits) / max(total_words, 1)
        print(f"{label:<26} {len(hits):>5}  {rate:>13.1f}")
        if 0 < len(hits) <= 12:
            for n, h in hits[:12]:
                print(f"      {n:<18} {h[:60]!r}")
    print("-" * 50)
    print(f"prose words: {total_words}")
    print(f"total flagged: {grand}")

    # the drumbeat-fragment check needs real prose sentences
    frag = 0
    for name, t in texts.items():
        for m in re.finditer(r"(?m)^([A-Z][^.]{6,55}\.)\s*$", t):
            frag += 1
            if frag <= 10:
                print(f"  fragment {name:<18} {m.group(1)[:66]!r}")
    print(f"short standalone prose sentences: {frag}")


if __name__ == "__main__":
    main()
