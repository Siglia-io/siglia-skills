#!/usr/bin/env python3
"""siglia-xbrl-element: a US GAAP taxonomy element, from FASB's own files, in one call.

  show NAME[,NAME...]   label, period type, balance, data type, abstract, deprecation (with the replacement and how),
                        FASB's documentation (the definition) and its ASC references (by paragraph only)
  search WORDS...       elements whose standard label holds every word, ranked (reportable first, deprecated last)

Source: https://xbrl.fasb.org/us-gaap/<year>/elts/ (not sec.gov). Files are fetched once with curl (Python's urllib
gets an IncompleteRead through the proxy on these 14 MB linkbases, Research 24 Sep) into a cache, and parsed into an
index there. dei elements are served from xbrl.sec.gov, which no seat fetches, so a dei name reads "not fetched".
Labels and documentation are quoted UNCHANGED under FASB's Authorized Uses notice, which is printed with them; ASC text
is never fetched or shown (the FAF terms; cite by paragraph). Writes only its cache. Deletes nothing.
Exit: 0 every name found · 1 a name absent or not fetched · 2 cannot fetch or parse
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = "https://xbrl.fasb.org/us-gaap/{year}/elts/"
FILES = ("us-gaap-{year}.xsd", "us-gaap-lab-{year}.xml", "us-gaap-doc-{year}.xml", "us-gaap-ref-{year}.xml",
         "us-gaap-depcon-def-{year}.xml")
NOTICE = ("Labels and documentation below are quoted unchanged from the US GAAP Financial Reporting Taxonomy: "
          "(c) 2010-{year} Financial Accounting Foundation; (c) 2007-2010 XBRL US, Inc. All Rights Reserved. "
          "Notice: Authorized Uses are Set Forth at https://xbrl.fasb.org/terms/TaxonomiesTermsConditions.html")
X = "{http://www.w3.org/1999/xlink}"
LB = "{http://www.xbrl.org/2003/linkbase}"
INDEX_VERSION = 1
DEP = {"dep-concept-deprecatedConcept": "replaced by",
       "dep-dimensionallyQualifiedConcept-deprecatedConcept": "replaced by a dimensionally qualified",
       "dep-partConcept-deprecatedAggregateConcept": "split into, among others,",
       "dep-mutuallyExclusiveConcept-deprecatedConcept": "replaced by one of the mutually exclusive",
       "essence-alias": "an essence alias of"}


class Fail(Exception):
    pass


def cache_dir(a) -> str:
    return os.path.join(a.cache or os.path.join(os.environ.get("TMPDIR", "/tmp"), "siglia-xbrl-cache"), str(a.year))


def fetch(a) -> None:
    d = cache_dir(a)
    os.makedirs(d, exist_ok=True)
    curl = os.environ.get("SIGLIA_XBRL_CURL", "curl")
    for f in FILES:
        name = f.format(year=a.year)
        path = os.path.join(d, name)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            continue
        if a.offline:
            raise Fail(f"{name} is not in the cache ({d}) and --offline was given")
        part = path + ".part"
        url = BASE.format(year=a.year) + name
        r = subprocess.run([curl, "-sS", "--fail", "--retry", "3", "--max-time", "300", "-o", part, url],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(part) or os.path.getsize(part) == 0:
            raise Fail(f"could not fetch {url} (curl exit {r.returncode}: {r.stderr.strip()[:200]})")
        os.replace(part, path)   # whole or not at all: a cut download never becomes the cached file


def build(a) -> dict:
    d = cache_dir(a)
    idx_path = os.path.join(d, f"index-v{INDEX_VERSION}.json")
    if os.path.isfile(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            return json.load(fh)
    fetch(a)
    p = lambda f: os.path.join(d, f.format(year=a.year))  # noqa: E731
    # no DTD, no entity: the stdlib parser would expand an internal entity (billion laughs), and FASB's files carry none
    for f in FILES:
        with open(p(f), "rb") as fh:
            head = fh.read(1 << 20)
        if re.search(rb"<!DOCTYPE|<!ENTITY", head):
            raise Fail(f"{f.format(year=a.year)} declares a DOCTYPE or an ENTITY; refused (FASB's files carry none)")
    E: dict = {}
    try:
        for el in ET.parse(p(FILES[0])).getroot().iter("{http://www.w3.org/2001/XMLSchema}element"):
            n = el.get("name")
            if not n:
                continue
            E[n] = {"type": (el.get("type") or "").split(":")[-1],
                    "period": el.get("{http://www.xbrl.org/2003/instance}periodType") or "",
                    "balance": el.get("{http://www.xbrl.org/2003/instance}balance") or "",
                    "abstract": el.get("abstract") == "true", "labels": {}, "doc": "", "refs": [], "dep": []}
        for f, want in ((FILES[1], None), (FILES[2], "documentation")):
            for lab in ET.parse(p(f)).getroot().iter(LB + "label"):
                m = re.match(r"lab_(.+?)_([A-Za-z]+)_en-US$", lab.get("id") or "")
                if not m or m.group(1) not in E:
                    continue
                role = (lab.get(X + "role") or "").rsplit("/", 1)[-1]
                if want == "documentation":
                    if role == "documentation":
                        E[m.group(1)]["doc"] = (lab.text or "").strip()
                else:
                    E[m.group(1)]["labels"][role] = (lab.text or "").strip()
        root = ET.parse(p(FILES[3])).getroot()
        for link in root:
            locs, arcs, refs = {}, [], {}
            for ch in link:
                if ch.tag == LB + "loc":
                    locs[ch.get(X + "label")] = (ch.get(X + "href") or "").split("#us-gaap_")[-1]
                elif ch.tag == LB + "referenceArc":
                    arcs.append((ch.get(X + "from"), ch.get(X + "to")))
                elif ch.tag == LB + "reference":
                    parts = {re.sub(r"\{.*\}", "", q.tag): (q.text or "").strip() for q in ch}
                    refs.setdefault(ch.get(X + "label"), []).append(((ch.get(X + "role") or "").rsplit("/", 1)[-1], parts))
            for fr, to in arcs:
                el = locs.get(fr)
                if el in E:
                    for role, q in refs.get(to, []):
                        s = "-".join(x for x in (q.get("Topic"), q.get("SubTopic"), q.get("Section"), q.get("Paragraph")) if x)
                        s += q.get("Subparagraph", "")
                        if s:
                            E[el]["refs"].append(f"ASC {s} [{role}]")
        for link in ET.parse(p(FILES[4])).getroot():
            locs = {ch.get(X + "label"): (ch.get(X + "href") or "").split("#")[-1]
                    for ch in link if ch.tag == LB + "loc"}
            for ch in link:
                if ch.tag != LB + "definitionArc":
                    continue
                kind = (ch.get(X + "arcrole") or "").rsplit("/", 1)[-1]
                fr, to = locs.get(ch.get(X + "from"), ""), locs.get(ch.get(X + "to"), "")
                if kind == "essence-alias" or not to.startswith("us-gaap_"):
                    continue
                n = to[len("us-gaap_"):]
                if n in E:
                    E[n]["dep"].append([kind, fr.replace("us-gaap_", "us-gaap:").replace("srt_", "srt:")])
    except (ET.ParseError, OSError) as e:
        raise Fail(f"cannot parse the {a.year} taxonomy in {d}: {e}")
    for v in E.values():
        v["refs"] = sorted(set(v["refs"]))
    idx = {"year": a.year, "elements": E}
    tmp = idx_path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh)
    os.replace(tmp, idx_path)
    return idx


def bare(name: str) -> tuple[str, str]:
    name = name.strip()
    m = re.match(r"^(us-gaap|dei|srt|ifrs-full|[a-z]+)[:_](.+)$", name)
    return (m.group(1), m.group(2)) if m else ("us-gaap", name)


def card(n: str, e: dict, year: int, refs: int) -> list[str]:
    lab = e["labels"].get("label", "")
    out = [f"us-gaap:{n}  ({year})", f"  label: {lab}"]
    flags = [e["period"] or "no period type", f"balance {e['balance']}" if e["balance"] else "no balance",
             e["type"] or "no type"]
    if e["abstract"]:
        flags.append("ABSTRACT (a heading; never carries a value)")
    out.append("  " + " · ".join(flags))
    if e["dep"]:
        y = re.search(r"\(Deprecated (\d{4})\)", lab)
        since = f" since {y.group(1)} (its label)" if y else f" (the {year} deprecated-concepts linkbase)"
        for kind, rep in e["dep"]:
            out.append(f"  DEPRECATED{since}: {DEP.get(kind, kind)} {rep}")
    other = {k: v for k, v in e["labels"].items() if k != "label" and v != lab}
    if other:
        out.append("  other labels: " + "; ".join(f"{k}: {v}" for k, v in sorted(other.items())))
    out.append(f"  documentation: {e['doc'] or '(none in the doc linkbase)'}")
    if e["refs"]:
        rr = e["refs"][:refs]
        more = f" (+{len(e['refs']) - refs} more)" if len(e["refs"]) > refs else ""
        out.append(f"  ASC references (by paragraph; the Codification's text is never fetched): {'; '.join(rr)}{more}")
        if all("legacyRef" in r for r in e["refs"]):
            out.append("  note: every ASC tie is legacyRef, which FASB describes as unreviewed")
    else:
        out.append("  ASC references: none in the reference linkbase")
    return out


def cmd_show(a) -> int:
    names = [x for part in a.names for x in part.split(",") if x.strip()]
    idx = build(a)
    E = idx["elements"]
    rc, printed, js = 0, False, []
    for raw in names:
        pfx, n = bare(raw)
        if pfx == "dei":
            print(f"dei:{n}  not fetched: the dei taxonomy is served from xbrl.sec.gov, which no seat fetches "
                  f"(the SEC request budget). Do not guess its definition.")
            js.append({"name": raw, "status": "not fetched (dei on xbrl.sec.gov)"})
            rc = 1
            continue
        if pfx != "us-gaap":
            print(f"{raw}  not loaded: this skill reads the us-gaap taxonomy only")
            js.append({"name": raw, "status": f"not loaded ({pfx})"})
            rc = 1
            continue
        e = E.get(n)
        if e is None:
            near = [k for k in E if k.lower() == n.lower()]
            hint = f"; did you mean {near[0]}?" if near else ""
            print(f"us-gaap:{n}  ABSENT from the {a.year} taxonomy (removed after deprecation, misspelled, or never "
                  f"an element{hint}). An earlier year may hold it: --year {a.year - 5}")
            js.append({"name": raw, "status": f"absent from {a.year}"})
            rc = 1
            continue
        if not printed and not a.json:
            print(NOTICE.format(year=a.year) + "\n")
            printed = True
        if a.json:
            js.append(dict(name=f"us-gaap:{n}", status="found", year=a.year, **e))
        else:
            print("\n".join(card(n, e, a.year, a.refs)) + "\n")
    if a.json:
        print(json.dumps({"notice": NOTICE.format(year=a.year), "elements": js}, indent=1))
    return rc


def cmd_search(a) -> int:
    idx = build(a)
    ws = [w.lower() for w in a.words]
    hits = []
    for n, e in idx["elements"].items():
        lab = e["labels"].get("label", "")
        low = lab.lower() + (" " + e["doc"].lower() if a.doc else "")
        if all(w in low for w in ws):
            hits.append((bool(e["dep"]), e["abstract"], len(lab), n, e))
    hits.sort(key=lambda h: (h[0], h[1], h[2], h[3]))
    print(NOTICE.format(year=a.year) + "\n")
    print(f"{len(hits)} element(s) in us-gaap {a.year} whose standard label{' or documentation' if a.doc else ''} holds {' + '.join(repr(w) for w in ws)}"
          + (f"; the first {a.top}" if len(hits) > a.top else ""))
    for dep, ab, _, n, e in hits[:a.top]:
        tags = [e["period"] or "-", e["balance"] or "-"] + (["ABSTRACT"] if ab else []) + (["DEPRECATED"] if dep else [])
        print(f"  us-gaap:{n}  [{', '.join(tags)}]  {e['labels'].get('label', '')}")
    return 0 if hits else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="xbrl_element.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, default=2026, help="the taxonomy year (default 2026)")
    p.add_argument("--cache", help="the cache root (default $TMPDIR/siglia-xbrl-cache)")
    p.add_argument("--offline", action="store_true", help="never fetch; fail if the cache lacks a file")
    s = p.add_subparsers(dest="cmd", required=True)
    sh = s.add_parser("show")
    sh.add_argument("names", nargs="+", help="element names, bare or us-gaap:, comma- or space-separated")
    sh.add_argument("--json", action="store_true")
    sh.add_argument("--refs", type=int, default=12, help="how many ASC references to print (default 12)")
    se = s.add_parser("search")
    se.add_argument("words", nargs="+")
    se.add_argument("--top", type=int, default=20)
    se.add_argument("--doc", action="store_true", help="search FASB's documentation (the definition) too")
    a = p.parse_args(argv)
    try:
        return cmd_show(a) if a.cmd == "show" else cmd_search(a)
    except Fail as e:
        print(f"xbrl_element.py: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
