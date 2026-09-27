#!/usr/bin/env python3
"""saas.py — SaaS and AI-SaaS metrics as filings disclose them versus as companies define them.

Part of the siglia-saas-metrics skill (its SKILL.md is one folder up). The reference is data/saas.json: each metric's kind
(GAAP, company-defined or a heuristic), its us-gaap elements by taxonomy year, what it means, what it must never be
computed from or read as, the rules that bind it and what the held set can ground, every row with its source. Which code
reads an element is never copied into the data: `metric NAME --grep DIR` searches a code folder live.

  saas.py metric NAME [--grep DIR]   one metric, by id, name, alias or us-gaap element; --grep lists the lines of the code
                                     files under DIR that name each of its elements
  saas.py list                       every metric, rule and check, one line each
  saas.py check-claim TEXT           C1 a company KPI computed from GAAP lines, in a clause the company's own definition does
                                     not carry, or by the writer ("we derived"); C2 a company KPI stated without its
                                     definition; C3 a low or falling RPO read as demand without an exemption statement (a
                                     bare "usage" is not one; 50-14A(b) covers a wholly unsatisfied obligation or series
                                     promise only); C4 a loss said to improve or worsen (it narrowed or widened);
                                     C5 a direction word with one period's figure and no comparison (a change or the other
                                     period's figure; a bare level 'to 72%' is not one), or one that disagrees with its own
                                     'from' and 'to' figures or sits on equal ones ('unchanged')
  saas.py sources                    every source item resolves:
                                     - a named file (a Research note, re-read log or rubric file, an agent primer) is found
                                       by its file name among the checkout's tracked files, a Corpus pack by its file name
                                       in Corpus's folder; its `anchors` are in it (in the keyed row or pack when a key is
                                       named: "(file.json, KEY)");
                                     - a fin-concepts register row is in the sibling siglia-fin-concepts skill, with its
                                       anchors in that row;
                                       order; each single-quoted string in a rule's `says` is in a cited section (or is an
                                       anchor of that row), and each `absent` phrase is in none;
                                     - a FASB taxonomy year is read with siglia-xbrl-element, offline: an element row's
                                       element exists, its label and period equal the row's, and its `asc` references are its
                                       references in that year (a legacy one marked); every year's label is compared by some
                                       taxonomy item of the row. Anchors name an element that exists (`X`), is absent (`!X`),
                                       carries a reference (`X ASC p`), is documented in those words (`X: words`), or a label
                                       search's whole result (`search WORDS = X, Y`);
                                     - a FASB ASU cited by reference ("FASB ASU 2016-20 (..., sha256 HEX, ...)") is never read
                                       or quoted here: it takes no anchors, and a named file the same row cites (the re-read
                                       record) must hold both its number and its sha256
Exit: 0 found / clean / all resolve · 1 unknown name / a flag / a dangling source · 2 the data file is unreadable, or
`sources` could not check: no checkout, no Corpus folder, no fin-concepts register, no cached eCFR, or a taxonomy year
not in the offline cache
Read-only, stdlib only (python 3.9+). No network, no host.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("SAAS_DATA") or os.path.join(HERE, "..", "data", "saas.json")
XBRL = os.path.join(HERE, "..", "..", "siglia-xbrl-element", "scripts", "xbrl_element.py")
KB = os.path.join(HERE, "..", "..", "siglia-kb", "scripts", "kb.py")
REGISTER = os.environ.get("SAAS_REGISTER_DIR") or os.path.join(HERE, "..", "..", "siglia-fin-concepts", "data")
YEARS = ("2024", "2025", "2026")
KINDS = ("GAAP", "company-defined", "heuristic")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".sql", ".java", ".go", ".rb", ".cs", ".kt", ".scala")


class DataError(Exception):
    pass


class Unchecked(Exception):
    """`sources` cannot check here (a cache or a folder is missing): exit 2, never 'dangling' and never 'resolves'."""


def load() -> dict:
    try:
        d = json.load(open(DATA))
        for key in ("metrics", "rules", "checks", "fasb_notice"):
            d[key]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise DataError(f"{DATA}: {e!r}")
    return d


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def collapse(s: str) -> str:
    return " ".join(s.split())


# ── code readers: a live read of a folder the caller names, never a copied list ────────────────────────────────────────
def code_readers(folder: str, names: list) -> dict:
    """"""
    out = {n: [] for n in names}
    if not names:
        return out
    rx = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")(?![A-Za-z0-9_])")
    for dp, dns, fns in os.walk(folder):
        dns[:] = sorted(x for x in dns if not x.startswith(".") and x not in ("node_modules", "__pycache__"))
        for fn in sorted(fns):
            if not fn.endswith(CODE_EXT):
                continue
            p = os.path.join(dp, fn)
            try:
                lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for m in rx.finditer(line):
                    at = f"{os.path.relpath(p, folder)}:{i}"
                    if at not in out[m.group(1)]:
                        out[m.group(1)].append(at)
    return out


# ── metric ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def find(d: dict, name: str) -> list:
    k = norm(name[8:] if name.lower().startswith("us-gaap:") else name)
    hits = []
    for m in d["metrics"]:
        keys = {norm(m["id"]), norm(m["name"])} | {norm(a) for a in m.get("aka", [])}
        els = {norm(e["element"]) for e in m.get("elements", [])}
        if k in keys or k in els:
            hits.append(m)
    return hits


def labels_by_year(labels: dict) -> list:
    """[('2024-2025', label), ('2026', label)]: consecutive years with the same label collapsed into one run."""
    runs = []
    for y in YEARS:
        if y not in labels:
            continue
        if runs and runs[-1][2] == labels[y] and int(y) == int(runs[-1][1]) + 1:
            runs[-1][1] = y
        else:
            runs.append([y, y, labels[y]])
    return [(a if a == b else f"{a}-{b}", lab) for a, b, lab in runs]


def show(m: dict, d: dict, grep_dir: str | None) -> str:
    els = m.get("elements", [])
    out = [d["fasb_notice"], ""] if any(e.get("labels") for e in els) else []
    out += [f"{m['id']}: {m['name']}  [{m['kind']}]", f"  means: {m['means']}", f"  source: {m['source']}"]
    if not els:
        ne = m.get("no_element") or {"text": "none", "source": m["source"]}
        out.append(f"  us-gaap elements: none. {ne['text']}  [{ne['source']}]")
    else:
        out.append("  us-gaap elements, by taxonomy year:")
        for e in els:
            asc = e.get("asc")
            out.append(f"    us-gaap:{e['element']}  {e['period']}" + (f" · {asc}" if isinstance(asc, str) else ""))
            for yrs, lab in labels_by_year(e.get("labels", {})):
                out.append(f"      {yrs}: {lab}")
            if isinstance(asc, dict):
                for yrs, refs in labels_by_year(asc):
                    out.append(f"      refs {yrs}: {refs}")
            if e.get("note"):
                out.append(f"      note: {e['note']}")
            out.append(f"      source: {e['source']}")
    for key, title in (("never", "never computed from, or read as"), ("reading", "read it this way"),
                       ("held", "what the held set can ground")):
        if m.get(key):
            out.append(f"  {title}:")
            out += [f"    - {r['text']}  [{r['source']}]" for r in m[key]]
    names = [e["element"] for e in els]
    if not names:
        out.append("  code reads (live): nothing to look for (no us-gaap element)")
    elif grep_dir is None:
        out.append("  code reads (live): not searched (add --grep DIR to search a code folder)")
    else:
        rd = code_readers(grep_dir, names)
        out.append(f"  code reads (live grep of {grep_dir}):")
        for n in names:
            h = rd[n]
            out.append(f"    {n}: " + ((", ".join(h[:4]) + (f" (+{len(h) - 4} more)" if len(h) > 4 else "")) if h else "none"))
    if m.get("rules"):
        rules = {r["id"]: r for r in d["rules"]}
        out.append("  rules:")
        out += [f"    {rules[i]['cite']}: {rules[i]['says']}  [{rules[i]['source']}]" for i in m["rules"]]
    return "\n".join(out)


# ── check-claim ────────────────────────────────────────────────────────────────────────────────────────────────────────
def term_rx(terms: list, patterns: list = ()) -> re.Pattern | None:
    alts = [re.escape(t).replace(r"\ ", " ").replace(" ", r"\s+") for t in sorted(set(terms), key=len, reverse=True)]
    alts += list(patterns)
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(alts) + r")(?![A-Za-z0-9])", re.I) if alts else None


# a computation: x 4, x 12, =, or a verb of arithmetic (research rule 4: billings are never computed; the primer: never ARR/NRR)
COMPUTE = re.compile(r"(?<![A-Za-z])[x×*]\s*(?:4|12)(?![0-9])|(?<![0-9.,])(?:4|12)\s*[x×](?![A-Za-z0-9])|=|\b(?:times|multipl\w*|annuali[sz]\w*|comput\w*|calculat\w*|"
                     r"deriv\w*|estimat\w*|impl(?:y|ies|ied)|prox(?:y|ied)|back(?:ed)?\s+out|divid\w*|ratio\s+of|equals?|"
                     r"plus|minus|sum\s+of)\b", re.I)
# the computation is the company's own: it defines it, or computes or measures it that way, or it is its definition
ATTRIB = re.compile(r"\bdefines\b|\bdefined\s+by\b|\bas\s+defined\b|\b(?:company|management)[- ]defined\b"
                    r"|\b(?:company|management|issuer|registrant|filer|it|they)\s+(?:calculates|computes|measures|derives)\b"
                    r"|\b(?:company|management|issuer|registrant|filer)(?:'s|’s)\s+(?:own\s+)?(?:definition|calculation|method)\b"
                    r"|\b(?:its|their)\s+(?:own\s+)?(?:definition|calculation|method)\b", re.I)
# the writer computing it ("which we derived", "our estimate"): never the company's own, whatever else the clause says
FIRST = re.compile(r"\b(?:we|our|us)\b[^.;]{0,40}?\b(?:deriv|comput|calculat|estimat|annuali[sz]|multipl|impl|infer|"
                   r"back(?:ed)?\s+out|buil[dt])\w*", re.I)
# the clauses a computation and its attribution must share: sentences, and parts split by ; or a dash
CLAUSE = re.compile(r"(?<=[.!?])(?<![Vv]s\.)\s+|;|\s[-–—]{1,2}\s|—")
DEFIN = re.compile(r"\bdefin(?:e|es|ed|ing|ition|itions)\b", re.I)
VALUE = re.compile(r"\d|\b(?:grew|grow\w*|rose|ris(?:e|es|ing)|fell|fall\w*|declin\w*|increas\w*|decreas\w*|up|down|above|below|"
                   r"higher|lower|improv\w*|expand\w*|slow\w*|accelerat\w*|decelerat\w*|strong\w*|weak\w*)\b", re.I)
WEAK = re.compile(r"\b(?:low|lower|fell|fall\w*|declin\w*|drop\w*|shrink\w*|shrank|decreas\w*|down|weak\w*|soft\w*|small\w*)\b", re.I)
DEMAND = re.compile(r"\b(?:demand|pipeline|momentum|slowdown|slowing|softening|traction|appetite)\b", re.I)
# an exemption statement: the paragraphs (50-14, 50-14A, 50-15), exempt*, an expedient, right to invoice, or a verb of leaving
# out tied to what the exemptions cover. A bare "usage" or "consumption" is NOT one: "RPO fell as usage demand weakened."
_OUT = r"(?:exclud\w*|omit\w*|leav(?:e|es|ing)\s+(?:\w+\s+)?out|left\s+(?:\w+\s+)?out|(?:does|do|did)\s+not\s+include|not\s+included|stay\w*\s+out|kept\s+out)"
_COVERED = r"(?:usage|consumption|variable\s+consideration|one\s+year\s+or\s+less|short(?:er)?[- ](?:term\s+)?contracts?)"
EXEMPT = re.compile(r"\b50-1[45]|\bexempt\w*|\bexpedient\w*|right[- ]to[- ]invoice"
                    rf"|\b{_OUT}[^.;,]{{0,60}}?\b{_COVERED}|\b{_COVERED}\b[^.;,]{{0,60}}?\b{_OUT}", re.I)
# C4 (Research, rubric row X2): a loss narrowed or widened; it never "improved" or "worsened"
LOSS = re.compile(r"\bloss(?:es)?\b", re.I)
BETTER = re.compile(r"\b(?:improv\w*|better|worsen\w*|worse|deteriorat\w*)\b", re.I)
# C5 (X2): a direction word needs both periods. One figure reached ("rose to $50M") with no comparison beside it is flagged,
# and so is a direction word that disagrees with its own 'from' and 'to' figures, or sits on equal ones ('unchanged')
_DIR = (r"increas\w*|decreas\w*|rose|ris(?:e|es|ing)|fell|fall(?:s|ing)?|grew|grow(?:s|ing)?|declin\w*|improv\w*|narrow\w*|"
        r"widen\w*|expand\w*|contract(?:ed|ing)|dropp?(?:ed|ing|s)?|jump\w*|climb\w*|shr[iau]nk\w*")
DIRECTION = re.compile(rf"\b(?:{_DIR})\b", re.I)
_ADV = r"(?:(?:about|roughly|approximately|nearly|almost|some|over|under|more\s+than|less\s+than)\s+)?"
_FIG = r"\(?[-−]?\$?\s?\(?[-−]?\d"                        # where a figure starts: $50M, -$3.0m, $(3.1)m, 41.2%
_UNIT = r"(?:%|percent(?:age\s+points?)?|basis\s+points?|bps|pp|points?|[kKmMbB]n?(?![A-Za-z])|thousand|million|billion)"
_CHG = r"(?:increase|decrease|rise|fall|decline|drop|gain|growth|jump|higher|lower|more|less|up|down|improvement|expansion|contraction)"
REACHED = re.compile(rf"\bto\s+{_ADV}{_FIG}", re.I)
# a comparison carries the other period's figure or the change itself: a 'from' figure; a change ('by 5%', 'up 5%', 'down $2m',
# 'rose 19%', 'a 5% increase', '$8M more'); a figure after 'compared with', 'versus', 'against' or 'than', or a figure then 'a
# year earlier'. A bare level ('to 72%') is not one, and neither is a period named without its figure ('year over year')
COMPARED = re.compile(rf"\bfrom\s+{_ADV}{_FIG}"
                      rf"|\b(?:by|up|down)\s+(?!(?:fiscal\s+)?(?:19|20)\d\d(?![\d%]|[.,]\d))(?:{_ADV}){_FIG}"
                      rf"|\b(?:{_DIR})\s+(?:by\s+)?{_ADV}{_FIG}"
                      rf"|\d[\d,.]*\s*{_UNIT}?\s+{_CHG}\b"
                      rf"|\b(?:compared\s+(?:with|to)|versus|vs\.?|against|than)\s+[^.;]{{0,30}}?\d"
                      rf"|\d[\d,.]*\s*{_UNIT}?\s+(?:a\s+year\s+(?:earlier|ago|before)|in\s+the\s+(?:prior|previous|preceding)[- ]"
                      r"(?:year|period|quarter)|last\s+year)\b", re.I)
# the figures a direction word is read against: 'to X' (never 'compared to X') and 'from Y', each with its sign and scale
_NUM = (r"(?P<pre>[\s($\-−]*)(?P<n>\d[\d,]*(?:\.\d+)?)\)?\s?(?:(?P<w>%|percent(?:age\s+points?)?|basis\s+points?|bps|thousand|"
        r"million|billion|trillion)|(?P<l>[kKmMbB]n?)(?![A-Za-z]))?")
TO_FIG = re.compile(rf"(?<!compared )\bto\s+{_ADV}{_NUM}", re.I)
FROM_FIG = re.compile(rf"\bfrom\s+{_ADV}{_NUM}", re.I)
SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mn": 1e6, "billion": 1e9, "b": 1e9, "bn": 1e9, "trillion": 1e12}


def figure(m: re.Match):
    """(kind, value, scale) of a TO_FIG or FROM_FIG match, or None for a bare four-digit year. kind: pct, pp, bps, or None
    for an amount or a count (scale None when none is printed)."""
    n, w, l, pre = m.group("n"), (m.group("w") or "").lower(), (m.group("l") or "").lower(), m.group("pre")
    if not (w or l or "$" in pre) and re.fullmatch(r"(?:19|20)\d\d", n):
        return None
    neg = any(ch in pre for ch in "-−(")
    v = float(n.replace(",", "")) * (-1 if neg else 1)
    if w in ("%", "percent"):
        return ("pct", v, None)
    if w.startswith("percent"):
        return ("pp", v, None)
    if w in ("bps",) or w.startswith("basis"):
        return ("bps", v, None)
    return (None, v, SCALE.get(w or l))


def sense(word: str):
    """(up, signed) for a direction word, or None for 'improved' (for a cost it can mean lower). A loss 'narrowed' or
    'widened' compares sizes, so those two are unsigned."""
    w = word.lower()
    if w.startswith("improv"):
        return None
    if w.startswith("widen"):
        return (True, False)
    if w.startswith("narrow"):
        return (False, False)
    return (w.startswith(("increas", "ris", "rose", "grew", "grow", "expand", "jump", "climb")), True)


def segments(clause: str) -> list:
    """[(direction word, its text)]: a clause with one direction word is one segment; with more, each runs from its word to
    the next, so 'Revenue rose to $50M from $42M, and gross margin fell to 41.2%' is read as two."""
    ds = list(DIRECTION.finditer(clause))
    if len(ds) == 1:
        return [(ds[0].group(0), clause)]
    return [(d.group(0), clause[d.start():(ds[i + 1].start() if i + 1 < len(ds) else len(clause))]) for i, d in enumerate(ds)]


def against(word: str, seg: str) -> str | None:
    """Why a direction word disagrees with its own 'from' and 'to' figures, or sits on equal ones; None when it agrees or the
    two cannot be compared (different kinds, a year, a figure missing)."""
    t, f = TO_FIG.search(seg), FROM_FIG.search(seg)
    if not (t and f):
        return None
    a, b = figure(f), figure(t)
    if a is None or b is None or (a[0] and b[0] and a[0] != b[0]):
        return None
    sa, sb = a[2] or b[2] or 1, b[2] or a[2] or 1
    x, y = a[1] * sa, b[1] * sb
    shown = lambda m: re.sub(r"^(?:to|from)\s+", "", m.group(0), flags=re.I).strip()
    if x == y:
        return (f"a direction word ('{word}') on equal figures ({shown(f)} to {shown(t)}); equal values read 'unchanged'")
    s = sense(word)
    if s is None:
        return None
    up, signed = s
    if not signed:
        x, y = abs(x), abs(y)
    if x != y and (y > x) != up:
        return (f"'{word}' disagrees with its own figures: {shown(f)} to {shown(t)} is "
                f"{'an increase' if y > x else 'a decrease'}" + ("" if signed else " in size"))
    return None


def check_claim(d: dict, text: str) -> list:
    """[(check id, message)]: C1-C5 as data/saas.json's checks say."""
    kpis = [(m, term_rx(m.get("aka", []), m.get("patterns", []))) for m in d["metrics"] if m["kind"] == "company-defined"]
    gaap = term_rx([a for m in d["metrics"] if m["kind"] == "GAAP" for a in m.get("aka", [])]
                   + [e["element"] for m in d["metrics"] for e in m.get("elements", [])])
    rpo = term_rx(next((m.get("aka", []) for m in d["metrics"] if m["id"] == "rpo"), []))
    flags = []
    named = [m["id"] for m, rx in kpis if rx and rx.search(text)]
    if named:
        masked = text
        for m, rx in kpis: masked = rx.sub(" KPI ", masked) if rx else masked
        g = gaap.search(masked) if gaap else None
        # the attribution counts only in the clause that holds the computation, and never when the writer computes it
        own = [c for c in CLAUSE.split(masked) if COMPUTE.search(c) and (FIRST.search(c) or not ATTRIB.search(c))]
        if g and own:
            flags.append(("C1", f"computes {', '.join(named)} from a GAAP line ('{g.group(0)}'); a company KPI is quoted with the "
                                "company's own definition, never computed"))
        if VALUE.search(masked) and not DEFIN.search(text):
            flags.append(("C2", f"states {', '.join(named)} without the company's definition; quote it, or say none is printed "
                                "(85 FR 10568: definition, calculation, use)"))
    if rpo and rpo.search(text) and WEAK.search(text) and DEMAND.search(text) and not EXEMPT.search(text):
        flags.append(("C3", "reads a low or falling RPO as demand without the 50-15 statement of the exemptions applied "
                            "(usage fees for a wholly unsatisfied obligation or series promise may stay out of RPO under "
                            "606-10-50-14A(b), and those estimated for a partially satisfied one are disclosed; a bare 'usage' "
                            "is not that statement)"))
    clauses = [c for c in CLAUSE.split(text) if c.strip()]
    worded = [BETTER.search(c).group(0) for c in clauses if LOSS.search(c) and BETTER.search(c)]
    if worded:
        flags.append(("C4", f"says a loss '{worded[0]}'; a loss narrowed or widened, never improved or worsened (and equal "
                            "values read 'unchanged')"))
    segs = [s for c in clauses for s in segments(c)]
    one = [w for w, s in segs if REACHED.search(s) and not COMPARED.search(s)]
    if one:
        flags.append(("C5", f"a direction word ('{one[0]}') with one period's figure; give the comparison period's figure "
                            "too, or the change"))
    off = [why for why in (against(w, s) for w, s in segs) if why]
    if off:
        flags.append(("C5", off[0]))
    return flags


# ── sources ────────────────────────────────────────────────────────────────────────────────────────────────────────────
CFR_ITEM = re.compile(r"^(\d+) CFR (\d+)\.(\d+[a-z]?)((?:\([A-Za-z0-9]+\))*)(?=\s|$)")
FASB_ITEM = re.compile(r"^FASB US GAAP taxonomy (\d{4}(?:(?:, | and )\d{4})*)(?!\d)")
REG_ITEM = re.compile(r"^siglia-fin-concepts ((?:SE|PG|QF|CF|LS|RF|SH|VA)-\d{2})(?![0-9])(.*)$")
FILE_ITEM = re.compile(r"^(?P<label>[A-Za-z][A-Za-z -]*?)\s+\(?(?P<file>[\w.-]+\.(?:md|jsonl?))(?:,\s*(?P<key>[\w.-]+))?\)?"
                       r"(?P<rest>(?:\s.*)?)$")
# a FASB ASU cited by reference: 'FASB ASU 2016-20 (storage.fasb.org, sha256 <hex>, read 2026-09-26, by reference)'. Its text
# is never read or quoted here; it resolves when a named file the same row cites (a re-read record) holds its number and hash
ASU_ITEM = re.compile(r"^FASB ASU (?P<num>\d{4}-\d{2})(?: Section [A-Z])? \((?P<meta>[^()]*)\)(?:\s.*)?$")
SHA256 = re.compile(r"\bsha256 ([0-9a-f]{16,64})\b")
TICKS = re.compile(r"`([^`]+)`")
QUOTED = re.compile(r"(?<![A-Za-z0-9])'(.+?)'(?![A-Za-z0-9])")
PARA = re.compile(r"\d{3}-\d{2,3}(?:-S?\d{2}-\d+[A-Z]?)?(?:\([A-Za-z0-9]+\))*")
TAX_REF = re.compile(r"^ASC (\S+?)(?:\(([A-Z]{2,4} .*)\))? \[(\w+)\]$")
ANCHOR_EL = re.compile(r"(!?)([A-Z][A-Za-z0-9]+)(?:: (.+)| (ASC .+))?")


def qnorm(s: str) -> str:
    """For quote matching: case, whitespace, curly quotes and dashes ignored (as siglia-def-check does)."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(re.sub(r"[‐-―]", "-", s).split()).casefold()


def sourced(d: dict) -> list:
    """[(where, source, row)] for every object in the data that carries a source: the factual rows."""
    out = []

    def walk(o, where):
        if isinstance(o, dict):
            if "source" in o:
                out.append((where, o["source"], o))
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v, f"{where}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{v.get('id', v.get('element', i)) if isinstance(v, dict) else i}]")
    for key in ("metrics", "rules", "checks"):
        walk(d[key], key)
    return out


_KB = {}


def kb_module():
    """"""
    if "m" not in _KB:
        if not os.path.isfile(KB):
            raise Unchecked(f"no siglia-kb at {KB}, so no cached eCFR or Corpus folder to read")
        spec = importlib.util.spec_from_file_location("siglia_kb_for_saas", KB)
        kb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kb)
        _KB["m"] = kb
    return _KB["m"]


class Cfr:
    """"""

    def __init__(self):
        self.dir, self.meta, self.parts = None, None, {}

    def where(self) -> str:
        if self.dir is None:
            d = os.environ.get("SAAS_CFR_DIR")
            if not d:
                kb = kb_module()
                d = kb.cfr_dir(kb.main_root())
            if not os.path.isfile(os.path.join(d, "ecfr.json")):
                raise Unchecked(f"no cached eCFR in {d} (run siglia-kb's kb.py fetch-cfr)")
            self.dir, self.meta = d, json.load(open(os.path.join(d, "ecfr.json")))
        return self.dir

    def section(self, title: str, part: str, sec: str) -> str | None:
        key = f"{title}-{part}"
        if key not in self.parts:
            f = os.path.join(self.where(), f"t{title}-p{part}.xml")
            secs = {}
            if os.path.isfile(f):
                try:
                    for s in ET.parse(f).iter("DIV8"):
                        if (s.get("N") or "").strip():
                            secs[s.get("N").strip()] = " ".join(" ".join(s.itertext()).split())
                except ET.ParseError as e:
                    raise Unchecked(f"cannot parse the cached {f}: {e}")
            self.parts[key] = secs
        return self.parts[key].get(f"{part}.{sec}")

    def as_of(self) -> str:
        return ", ".join(sorted(set(self.meta.values()))) if self.meta else "not read"


class Tax:
    """FASB's taxonomy years through siglia-xbrl-element, loaded in this process with offline=True: its own index of each
    year (its cache: SAAS_XBRL_CACHE, else its default $TMPDIR/siglia-xbrl-cache), read once per year, and its own search.
    Never fetched here: a year not in the cache is Unchecked (exit 2)."""

    def __init__(self):
        self.xe, self.idx, self.searches = None, {}, {}

    def _mod(self):
        if self.xe is None:
            if not os.path.isfile(XBRL):
                raise Unchecked(f"no siglia-xbrl-element at {XBRL}")
            spec = importlib.util.spec_from_file_location("siglia_xbrl_for_saas", XBRL)
            xe = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(xe)
            real = xe.build

            def build(a, _real=real):   # its search calls build too: one index load per year, shared
                if a.year not in self.idx:
                    self.idx[a.year] = _real(a)
                return self.idx[a.year]
            xe.build, self.xe = build, xe
        return self.xe

    def _args(self, y: str, **kw) -> argparse.Namespace:
        return argparse.Namespace(year=int(y), cache=os.environ.get("SAAS_XBRL_CACHE") or None, offline=True, **kw)

    def year(self, y: str) -> dict:
        """{element: its index entry (labels, doc, refs, period, ...)}: FASB's `y` taxonomy, as siglia-xbrl-element reads it."""
        if y not in YEARS:   # never handed on: siglia-xbrl-element makes a cache folder for any year it is asked for
            raise Unchecked(f"taxonomy year {y} is not one this reference reads ({YEARS[0]}-{YEARS[-1]})")
        xe = self._mod()
        try:
            return xe.build(self._args(y))["elements"]
        except (xe.Fail, OSError, ValueError, KeyError) as e:
            raise Unchecked(f"FASB taxonomy {y} not read offline: {e}")

    def search(self, y: str, words: str) -> list:
        """Every element siglia-xbrl-element's label search returns for `words` in year `y`, sorted."""
        if (y, words) not in self.searches:
            self.year(y)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self._mod().cmd_search(self._args(y, words=words.split(), top=100000, doc=False))
            self.searches[(y, words)] = sorted(re.findall(r"^\s+us-gaap:(\w+)\s", buf.getvalue(), re.M))
        return self.searches[(y, words)]

    def read(self) -> str:
        return ", ".join(str(y) for y in sorted(self.idx)) or "not read"


class Files:
    """The named files source items cite, found by file name, never by a path written in the data: a Research note, re-read
    log or rubric file and an agent primer among the checkout's tracked files (SAAS_ROOT, else this script's checkout, else
    the cwd's); a Corpus pack in Corpus's folder; a fin-concepts register row in the
    sibling skill's data (SAAS_REGISTER_DIR overrides). Each is read once per run."""

    def __init__(self):
        self.root, self.tracked, self.corpus, self.cache, self.register = None, None, None, {}, None

    def checkout(self) -> tuple:
        if self.tracked is None:
            root = os.environ.get("SAAS_ROOT")
            cands = [root] if root else [HERE, os.getcwd()]
            for c in cands:
                try:
                    r = subprocess.run(["git", "-C", c, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
                except OSError:
                    continue
                if r.returncode == 0 and r.stdout.strip():
                    root = r.stdout.strip()
                    break
            else:
                raise Unchecked(f"no git checkout at {cands[0]} to find the named files in (set SAAS_ROOT; on a Mac without "
                                "an accepted Xcode licence, export DEVELOPER_DIR=/Library/Developer/CommandLineTools)")
            r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True)
            if r.returncode != 0:
                raise Unchecked(f"git ls-files failed in {root}: {r.stderr.strip()[:200]}")
            by: dict = {}
            for rel in r.stdout.split("\0"):
                if rel:
                    by.setdefault(os.path.basename(rel), []).append(rel)
            self.root, self.tracked = root, by
        return self.root, self.tracked

    def corpus_dir(self) -> str:
        if self.corpus is None:
            d = os.environ.get("SAAS_CORPUS_DIR") or kb_module().corpus_dir()
            if not os.path.isdir(d):
                raise Unchecked(f"no Corpus folder at {d} (set SAAS_CORPUS_DIR)")
            self.corpus = d
        return self.corpus

    def locate(self, label: str, name: str):
        """(absolute path, None) or (None, why it dangles)."""
        if label.split()[0].lower() == "corpus":
            hits = sorted(glob.glob(os.path.join(glob.escape(self.corpus_dir()), "**", name), recursive=True))
            if not hits:
                return None, f"no {name} in the Corpus folder"
            if len(hits) > 1:
                return None, f"{name} is ambiguous in the Corpus folder ({len(hits)} files)"
            return hits[0], None
        root, tracked = self.checkout()
        rels = tracked.get(name, [])
        if not rels:
            return None, f"no tracked file named {name} in the checkout"
        if len(rels) > 1:
            texts = {open(os.path.join(root, r), "rb").read() for r in rels if os.path.isfile(os.path.join(root, r))}
            if len(texts) > 1:
                return None, f"{name} names {len(rels)} tracked files that differ"
        return os.path.join(root, rels[0]), None

    def text(self, path: str, key: str | None):
        """(the file's text, whitespace collapsed, or the keyed row's or pack's JSON) or (None, why it dangles)."""
        if (path, key) not in self.cache:
            try:
                raw = open(path, encoding="utf-8", errors="replace").read()
            except OSError as e:
                self.cache[(path, key)] = (None, f"cannot read {os.path.basename(path)}: {e}")
                return self.cache[(path, key)]
            if key is None:
                self.cache[(path, key)] = (collapse(raw), None)
                return self.cache[(path, key)]
            try:
                d = json.loads(raw)
            except ValueError as e:
                self.cache[(path, key)] = (None, f"{os.path.basename(path)} is not JSON, so it has no row {key}: {e}")
                return self.cache[(path, key)]
            sel = None
            if isinstance(d, dict) and isinstance(d.get("packs"), dict):
                sel = d["packs"].get(key)
            for rows in ((d.get("rows"), d.get("entries")) if isinstance(d, dict) else (d,)):
                if sel is None and isinstance(rows, list):
                    sel = next((r for r in rows if isinstance(r, dict) and key in (r.get("key"), r.get("id"))), None)
            self.cache[(path, key)] = ((collapse(json.dumps(sel, ensure_ascii=False)), None) if sel is not None
                                       else (None, f"no row or pack {key} in {os.path.basename(path)}"))
        return self.cache[(path, key)]

    def register_row(self, rid: str):
        """(the fin-concepts row's JSON, whitespace collapsed) or (None, why it dangles)."""
        if self.register is None:
            if not os.path.isdir(REGISTER):
                raise Unchecked(f"no siglia-fin-concepts register at {REGISTER}")
            rows = {}
            for f in sorted(glob.glob(os.path.join(REGISTER, "*.json"))):
                try:
                    d = json.load(open(f, encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for e in (d.get("entries") or []) if isinstance(d, dict) else []:
                    if isinstance(e, dict) and e.get("id"):
                        rows[e["id"]] = collapse(json.dumps(e, ensure_ascii=False))
            self.register = rows
        return (self.register[rid], None) if rid in self.register else (None, f"no register row {rid} in siglia-fin-concepts")


def split_top(s: str) -> list:
    """s split on the commas outside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return [x for x in out + [cur.strip()] if x]


def asc_items(s: str):
    """[(paragraph, 'SX ...' or None, marks)] from an `asc` string ('none' is []), or why it cannot be read. An item is a
    paragraph (606-10-50-8(a), 235-10-S99-3, 350-40), then optional ' (S-X 210.12-04(a))', ' (legacy)', ' (common practice)'."""
    s = s.strip()
    if s == "none":
        return []
    out = []
    for part in split_top(s):
        p = part[4:] if part.startswith("ASC ") else part
        m = PARA.match(p)
        if not m:
            return f"cannot read '{part}'"
        rest, sx, marks = p[m.end():], None, set()
        while rest:
            if not rest.startswith(" ("):
                return f"cannot read '{part}'"
            depth, j = 0, 1
            while j < len(rest):
                depth += (rest[j] == "(") - (rest[j] == ")")
                if depth == 0:
                    break
                j += 1
            if depth:
                return f"unbalanced parentheses in '{part}'"
            q = rest[2:j]
            if q.startswith(("S-X ", "SX ")):
                sx = "SX " + q.split(" ", 1)[1]
            elif q in ("legacy", "common practice"):
                marks.add(q)
            else:
                return f"unknown qualifier '({q})' in '{part}'"
            rest = rest[j + 1:]
        out.append((m.group(0), sx, marks))
    return out


def tax_refs(e: dict) -> list:
    """[(paragraph, 'SX ...' or None, role)] from siglia-xbrl-element's 'ASC 220-10-S99-2(SX 210.5-03(2)) [legacyRef]'."""
    return [(m.group(1), m.group(2), m.group(3)) for m in (TAX_REF.match(r) for r in e.get("refs", [])) if m]


def ref_hits(para: str, sx: str | None, refs: list) -> list:
    """The element's references a cited paragraph names: the same paragraph or one of its subparagraphs (and the same S-X
    rule when one is cited)."""
    return [t for t in refs if (t[0] == para or t[0].startswith(para + "(")) and (sx is None or t[1] == sx)]


def check_asc(el: str, asc, found: dict) -> list:
    """Why the row's `asc` (one string for every year, or one per year) is not the element's references, per year."""
    bad = []
    for y, e in found.items():
        s = asc if isinstance(asc, str) else (asc or {}).get(y)
        if s is None:
            bad.append(f"asc names no references for {y}")
            continue
        items = asc_items(s)
        if isinstance(items, str):
            bad.append(f"asc {y}: {items}")
            continue
        refs = tax_refs(e)
        if not items and refs:
            bad.append(f"asc says none for {y}, but us-gaap:{el} has {len(refs)} references in {y}")
        for para, sx, marks in items:
            name = f"ASC {para}" + (f" ({sx})" if sx else "")
            hit = ref_hits(para, sx, refs)
            if not hit:
                bad.append(f"{name} is not among us-gaap:{el}'s {y} references")
                continue
            roles = {t[2] for t in hit}
            if roles == {"legacyRef"} and "legacy" not in marks:
                bad.append(f"{name} is a legacy reference in {y}: mark it (legacy)")
            if "legacy" in marks and "legacyRef" not in roles:
                bad.append(f"{name} is marked legacy but is {'/'.join(sorted(roles))} in {y}")
            if "common practice" in marks and "commonPracticeRef" not in roles:
                bad.append(f"{name} is marked common practice but is {'/'.join(sorted(roles))} in {y}")
    return bad


def check_fasb_anchor(a: str, years: list, tax: Tax) -> str | None:
    a = a.strip()
    m = re.fullmatch(r"search (.+?) = (.+)", a)
    if m:
        want = sorted(x.strip() for x in m.group(2).split(","))
        for y in years:
            got = tax.search(y, m.group(1))
            if got != want:
                return f"{y} search '{m.group(1)}' returns {', '.join(got) or 'nothing'}, not {', '.join(want)}"
        return None
    m = ANCHOR_EL.fullmatch(a)
    if not m or (m.group(1) and (m.group(3) or m.group(4))):
        return f"cannot read the anchor `{a}`"
    neg, n, words, ref = m.groups()
    for y in years:
        e = tax.year(y).get(n)
        if neg:
            if e is not None:
                return f"us-gaap:{n} is in the {y} taxonomy, not absent"
            continue
        if e is None:
            return f"us-gaap:{n} is absent from the {y} taxonomy"
        if words and qnorm(words) not in qnorm(e.get("doc", "")):
            return f"us-gaap:{n}'s {y} documentation does not hold: {words}"
        if ref:
            items = asc_items(ref)
            if isinstance(items, str) or not items:
                return f"cannot read the anchor `{a}`"
            for para, sx, marks in items:
                roles = {t[2] for t in ref_hits(para, sx, tax_refs(e))}
                if not roles:
                    return f"ASC {para} is not among us-gaap:{n}'s {y} references"
                for mark, role in (("legacy", "legacyRef"), ("common practice", "commonPracticeRef")):
                    if mark in marks and role not in roles:
                        return f"ASC {para} is marked {mark} but is {'/'.join(sorted(roles))} for us-gaap:{n} in {y}"
    return None


def check_anchors(text: str, rest: str, where: str) -> str | None:
    for a in TICKS.findall(rest):
        if collapse(a) not in text:
            return f"anchor not in {where}: {a}"
    return None


def resolve(where: str, src, row: dict, files: Files, cfr: Cfr, tax: Tax) -> tuple:
    """(items, [(item, why)]) for one sourced row: each item resolved, then the row's quotes and `absent` phrases."""
    items = [i.strip() for i in (src or "").split(" | ") if i.strip()]
    if not items:
        return 0, [("(empty)", "no source")]
    bad, sections, anchors, records, asus = [], [], [], [], []
    for it in items:
        m = ASU_ITEM.match(it)
        if m:
            sha = SHA256.search(m.group("meta"))
            if TICKS.search(it):
                bad.append((it, f"ASU {m.group('num')} is cited by reference: its text is never quoted, so it takes no anchors"))
            elif not sha:
                bad.append((it, f"ASU {m.group('num')} names no sha256 of the copy that was read"))
            else:
                asus.append((it, m.group("num"), sha.group(1)))
            continue
        m = CFR_ITEM.match(it)
        if m:
            title, part, sec, paras = m.groups()
            cite = f"{title} CFR {part}.{sec}"
            text = cfr.section(title, part, sec)
            if text is None:
                bad.append((it, f"no section {cite} in the cached eCFR"))
                continue
            sections.append((cite, qnorm(text)))
            at = 0
            for lab in re.findall(r"\(([A-Za-z0-9]+)\)", paras):
                i = text.find(f"({lab})", at)
                if i < 0:
                    bad.append((it, f"paragraph ({lab}) is not in {cite}"))
                    break
                at = i + len(lab) + 2
            continue
        m = FASB_ITEM.match(it)
        if m:
            years = re.findall(r"\d{4}", m.group(1))
            wrong = [y for y in years if y not in YEARS]
            if wrong:
                bad.append((it, f"taxonomy year {', '.join(wrong)} is not one this reference reads ({YEARS[0]}-{YEARS[-1]})"))
                continue
            ticks = TICKS.findall(it)
            if "element" in row:
                el = row["element"]
                found = {}
                for y in years:
                    e = tax.year(y).get(el)
                    if e is None:
                        bad.append((it, f"us-gaap:{el} is absent from the {y} taxonomy"))
                        continue
                    found[y] = e
                    lab = e.get("labels", {}).get("label", "")
                    if row.get("labels", {}).get(y) != lab:
                        bad.append((it, f"{y} label is '{lab}' in the taxonomy, not '{row.get('labels', {}).get(y)}'"))
                    if e.get("period") != row.get("period"):
                        bad.append((it, f"{y} period is {e.get('period')} in the taxonomy, not {row.get('period')}"))
                if row.get("asc"):
                    bad += [(it, why) for why in check_asc(el, row["asc"], found)]
            elif not ticks:
                bad.append((it, "a FASB item on a row with no element must name what it checks in `anchors`"))
            for a in ticks:
                why = check_fasb_anchor(a, years, tax)
                if why:
                    bad.append((it, why))
            continue
        m = REG_ITEM.match(it)
        if m:
            anchors += TICKS.findall(m.group(2))
            text, why = files.register_row(m.group(1))
            why = why or check_anchors(text, m.group(2), f"register row {m.group(1)}")
            if why:
                bad.append((it, why))
            continue
        m = FILE_ITEM.match(it)
        if m:
            anchors += TICKS.findall(m.group("rest"))
            path, why = files.locate(m.group("label"), m.group("file"))
            if path:
                text, why = files.text(path, m.group("key"))
                name = m.group("file") + (f" row {m.group('key')}" if m.group("key") else "")
                why = why or check_anchors(text, m.group("rest"), name)
                if text:
                    records.append(text)
            if why:
                bad.append((it, why))
            continue
        bad.append((it, "not a named file, a register row, a 17 CFR section, the FASB taxonomy or a FASB ASU"))
    for it, num, sha in asus:
        if not any(f"ASU {num}" in t and sha in t for t in records):
            bad.append((it, f"ASU {num}'s sha256 {sha} is in no re-read record this row cites (a named file holding the ASU's "
                            "number and that hash)"))
    if "element" in row:   # every year's label is compared by some taxonomy item of the row (the items may split the years)
        named = {y for i in items for f in [FASB_ITEM.match(i)] if f for y in re.findall(r"\d{4}", f.group(1))}
        unchecked = sorted(set(row.get("labels", {})) - named)
        if unchecked:
            bad.append(("labels", f"labels for {', '.join(unchecked)} are not checked: no FASB taxonomy item of the row names "
                                  f"{'that year' if len(unchecked) == 1 else 'those years'}"))
    if where.startswith("rules[") and isinstance(row.get("says"), str):
        for q in QUOTED.findall(row["says"]):
            if not any(qnorm(q) in t for _, t in sections) and not any(qnorm(q) == qnorm(a) for a in anchors):
                bad.append(("says", f"a quote in no cited CFR section and no anchor of this row: '{q}'"))
    for ph in row.get("absent", []):
        if not sections:
            bad.append(("absent", f"'{ph}' is claimed absent, but the row cites no CFR section"))
        for cite, t in sections:
            if qnorm(ph) in t:
                bad.append(("absent", f"'{ph}' is claimed absent but is in {cite}"))
    return len(items), bad


# ── main ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="saas.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mp = sub.add_parser("metric")
    mp.add_argument("name", nargs="+")
    mp.add_argument("--grep", metavar="DIR", help="a code folder to search for lines naming each element (live)")
    sub.add_parser("list")
    sub.add_parser("check-claim").add_argument("text", nargs="+")
    sub.add_parser("sources")
    a = ap.parse_args(argv)
    try:
        d = load()
    except DataError as e:
        print(f"saas: data unreadable: {e}", file=sys.stderr)
        return 2
    if a.cmd == "metric":
        name = " ".join(a.name)
        hits = find(d, name)
        if not hits:
            print(f"saas: no metric {name!r}; known: {', '.join(m['id'] for m in d['metrics'])}")
            return 1
        if a.grep is not None and not os.path.isdir(a.grep):
            print(f"saas: --grep {a.grep}: no such folder", file=sys.stderr)
            return 1
        print("\n\n".join(show(m, d, a.grep) for m in hits))
        return 0
    if a.cmd == "list":
        print(f"metrics ({len(d['metrics'])}):")
        for m in d["metrics"]:
            print(f"  {m['id']:<24} {m['kind']:<16} {len(m.get('elements', [])):>2} elements  {m['name']}")
        print(f"rules ({len(d['rules'])}):")
        for r in d["rules"]:
            print(f"  {r['id']:<24} {r['cite']}")
        print(f"checks ({len(d['checks'])}):")
        for c in d["checks"]:
            print(f"  {c['id']:<24} {c['says']}")
        print(f"sourced rows: {len(sourced(d))}")
        return 0
    if a.cmd == "check-claim":
        flags = check_claim(d, " ".join(a.text))
        for cid, msg in flags:
            print(f"FLAG {cid}: {msg}")
        if not flags:
            print(f"claim clean: {', '.join(c['id'] for c in d['checks'])} checked, none raised")
        return 1 if flags else 0
    # sources
    rows, bad, n = sourced(d), [], 0
    files, cfr, tax = Files(), Cfr(), Tax()
    try:
        cfr.where()   # a missing eCFR cache is said before any other work
        for where, src, row in rows:
            k, b = resolve(where, src, row, files, cfr, tax)
            n += k
            bad += [(where, it, why) for it, why in b]
    except Unchecked as e:
        print(f"saas: sources not checked: {e}", file=sys.stderr)
        return 2
    print(f"sources: {len(rows)} sourced rows, {n} items, {len(bad)} dangling (named files in {files.root or 'no checkout'}; "
          f"eCFR as of {cfr.as_of()}; FASB taxonomy {tax.read()} offline)")
    for where, it, why in bad:
        print(f"  DANGLING {where}: {why}\n    item: {it}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
