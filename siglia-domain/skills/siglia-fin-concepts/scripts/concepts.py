#!/usr/bin/env python3
"""siglia-fin-concepts: the market-standard reading of investor questions, from the register. Read-only.

  read "QUESTION"   the reading: which concepts the question names, the qualifier's comparison frame ("low" against
                    what?), the figures and elements, any line a named source draws or "no market threshold", the
                    pitfalls, and what "cannot establish" means for it
  find "WORDS"      the entries that best match, ranked
  show ID [ID...]   one entry in full, with every source, its tier, licence and whether it was re-read
  list [--family F] every entry, one line each
  validate          the register's rules (below); exit 1 on any FAIL
  elements          every XBRL element the register names, checked against siglia-xbrl-element's cached FASB index
  review FILE.json  apply Research's row corrections mechanically (1.1): a JSON list of {id, field, should_be, why, url,
                    quote, accessed, verdict}; all or nothing; every change logged in the row with its source

The register is data/*.json in this skill, one file per family. The knowledge is Research's and its agents', read from
primary and authoritative sources; this script only finds and checks it. It never answers a finance question from
anything but a register row, and a question no row covers reads "not in the register".
Exit: 0 · 1 a FAIL (validate) or nothing found (read/find/show) · 2 cannot load
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("SIGLIA_FIN_DATA") or os.path.join(os.path.dirname(HERE), "data")
_W = re.compile(r"[a-z0-9]+")
STOP = frozenset("""a an and are as at be been but by can could did do does for from had has have how i if in into is it
its of on or our s should so than that the their them then there these they this to was we were what when where whether
which while who why will with would you your company companys companies firm business stock inc corp co ltd x""".split())
TIERS = (1, 2)
LICENCES = ("PD", "ref", "OD", "none")
KINDS = ("definitional", "source-drawn", "rule-of-thumb", "owner-specific")   # 1.1: and any kind starting "withdrawn"
# 1.2 (Research): "owner-specific" = a line a named owner draws for its own purpose, not a market threshold (S&P's bands on
# S&P-adjusted figures, an exchange's 20% approval trigger, Item 3.02's filing floor, the SEC's 12-month disclosure horizon);
# "source-drawn" = a line the source draws as the market's reading, which is rare
NEVER = [(r"financialmodelingprep|\bFMP\b", "FMP: a redistributor, never cited (rule 4)"),
         (r"nasdaq\.com", "Nasdaq data pages: a redistributor"), (r"stooq", "Stooq: a redistributor"),
         (r"finance\.yahoo|yahoo finance", "Yahoo Finance: a redistributor"), (r"macrotrends", "Macrotrends: a redistributor"),
         (r"google\.com/finance", "Google Finance: a redistributor"),
         (r"moodys\.com|\bMoody'?s\b", "Moody's: DO NOT USE (Research §1)"), (r"fitchratings|\bFitch\b", "Fitch: DO NOT USE"),
         (r"finra\.org|\bFINRA\b", "FINRA: DO NOT USE (Research §1)"), (r"\blsta\b", "LSTA: DO NOT USE (Research §1)"),
         (r"ifrs\.org", "IFRS taxonomy: an owner decision (Research §1)"),
         # 1.4 (the skill-store vet, Research 24 Sep): commentary and aggregator sites, never a source
         # a whole domain only: expectationsinvesting.com (a book's site, VA-27) is not investing.com
         (r"(?:^|[/.@\s])seekingalpha\.com\b|\bSeeking Alpha\b", "Seeking Alpha: commentary, never cited"),
         (r"(?:^|[/.@\s])fool\.com\b|\bMotley Fool\b", "Motley Fool: commentary, never cited"),
         (r"(?:^|[/.@\s])stocktitan\.net\b", "StockTitan: a redistributor"),
         (r"(?:^|[/.@\s])marketscreener\.com\b", "MarketScreener: a redistributor"),
         (r"(?:^|[/.@\s])investing\.com\b", "Investing.com: a redistributor")]
# 1.4: an SEC citation names a filing (/Archives/edgar/data/...) or a rule, form or release, never a browse or search page
SEC_SEARCH = re.compile(r"sec\.gov/cgi-bin/(browse-edgar|srch-edgar|own-disp)|efts\.sec\.gov|sec\.gov/edgar/search|"
                        r"sec\.gov/edgar/browse", re.I)
# cited by reference only: a PD licence on these is wrong, and they carry no quote
BYREF = r"fasb\.org|\bASC\b|cfainstitute|\bCFA\b|spglobal|S&P\b|bdc\.ca|corporatefinanceinstitute|\bCFI\b|" \
        r"wallstreetprep|investopedia|damodaran|nareit|naic\.org|\bJournal of\b|\bReview of (Financial|Accounting|Economic)"
PHRASING_ONLY = r"investor\.gov"
QUALIFIER = re.compile(r"\b(low|high|weak|strong|healthy|risky|safe|cheap|expensive|stretched|too much|a lot|enough|"
                       r"good|bad|poor|solid|improving|deteriorating|declining|shrinking|growing)\b", re.I)
RULES0 = """Research's six rules for every reading:
  1. "low", "weak", "strong", "a lot" need a stated comparison, and the reading names it (own history, a peer set,
     a scale figure, the prior same-length period)
  2. a line exists only where a named owner draws it, labelled as that owner's; S&P's bands are S&P's, on S&P-adjusted
     figures, never on as-reported GAAP figures; where no owner draws one, show the figure and the comparison only
  3. never a verdict, never a forecast: "<figure, basis named> at <date> against <comparison>"
  4. the period comes from each fact's own dates: 10-Q cash flows are year-to-date (Reg S-X 10-01(c)(3));
     TTM = latest FY + current YTD - prior YTD; weighted-average shares are never summed
  5. lenders are different: runway, current ratio and interest coverage read not applicable for banks, insurers,
     broker-dealers and BDCs
  6. an absence is never a finding: no event filed reads "cannot establish\""""


def words(s: str) -> list[str]:
    return _W.findall(str(s).lower().replace("'", ""))


def load(data: str = DATA) -> dict:
    files = sorted(glob.glob(os.path.join(data, "*.json")))
    if not files:
        raise SystemExit(f"concepts.py: no register files in {data}")
    fams, entries = {}, []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"concepts.py: {f} does not load: {e}", file=sys.stderr)
            raise SystemExit(2)
        fams[f] = d
    return build(fams)


def build(files: dict) -> dict:
    """{path: family file dict} -> the register as validate() reads it (1.5: review validates its result in memory)."""
    fams, entries = {}, []
    for f, d in sorted(files.items()):
        fam = d.get("family") or os.path.basename(f)
        fams[os.path.basename(f)] = d
        for e in d.get("entries") or []:
            e = dict(e)
            e["_file"] = os.path.basename(f)
            e["_family"] = fam
            entries.append(e)
    return {"files": fams, "entries": entries, "by_id": {e.get("id"): e for e in entries}}


# ── validate ────────────────────────────────────────────────────────────────────────────────────────────────────────
def repo_dir() -> str | None:
    """1.1 (Research's finding): the repository whose main R10 reads — the caller's, else the one this skill lives in;
    None from an export outside any repository (then R10 is not checked, never a false FAIL)."""
    import subprocess
    for d in (os.getcwd(), HERE):
        r = subprocess.run(["git", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.dirname(r.stdout.strip())
    return None


def on_main(path: str, repo: str) -> bool:
    import subprocess
    r = subprocess.run(["git", "-C", repo, "cat-file", "-e", f"main:{path}"], capture_output=True)
    return r.returncode == 0


def validate(R: dict, index: dict | None = None) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    add = lambda lvl, code, msg: out.append((lvl, code, msg))  # noqa: E731
    seen: dict[str, str] = {}
    repo = repo_dir()
    if repo is None:
        add("INFO", "R10", "no repository here (an export): sources of record were not checked on main")
    for e in R["entries"]:
        i = str(e.get("id") or "")
        where = f"{i or '?'} ({e['_file']})"
        # R1 shape
        if not re.fullmatch(r"[A-Z]{2,3}-\d{2,3}", i):
            add("FAIL", "R1", f"{where}: id must look like CF-01")
        if i in seen:
            add("FAIL", "R1", f"{where}: id also in {seen[i]}")
        seen[i] = e["_file"]
        for f in ("concept", "market_reading"):
            if not str(e.get(f) or "").strip():
                add("FAIL", "R1", f"{where}: no {f}")
        if len(e.get("questions") or []) < 3:
            add("FAIL", "R1", f"{where}: fewer than 3 plain questions (the reader needs the user's words)")
        if e.get("confidence") not in ("high", "medium", "low"):
            add("FAIL", "R1", f"{where}: confidence {e.get('confidence')!r}")
        srcs = e.get("sources") or []
        if not srcs:
            add("FAIL", "R2", f"{where}: no source")
        ids = set()
        for s in srcs:
            sid = s.get("id")
            ids.add(sid)
            txt = " ".join(str(s.get(k) or "") for k in ("title", "publisher", "url"))
            # R2 tier and licence
            if s.get("tier") not in TIERS:
                add("FAIL", "R2", f"{where} {sid}: tier {s.get('tier')!r}")
            if s.get("licence") not in LICENCES:
                add("FAIL", "R2", f"{where} {sid}: licence {s.get('licence')!r}")
            if s.get("licence") == "none":
                add("FAIL", "R2", f"{where} {sid}: licence none is not usable as a source")
            # R3 never a source; no fetched sec.gov
            for rx, why in NEVER:
                if re.search(rx, txt, re.I):
                    add("FAIL", "R3", f"{where} {sid}: {why}")
            if SEC_SEARCH.search(str(s.get("url") or "")):
                add("FAIL", "R12", f"{where} {sid}: an SEC browse or search page is not a citation: cite the filing "
                                   f"(/Archives/edgar/data/...), or the rule, form or release")
            host = re.match(r"https?://([^/]+)", str(s.get("url") or ""))
            if host and re.search(r"(^|\.)sec\.gov$", host.group(1)) and s.get("fetched"):
                add("FAIL", "R3", f"{where} {sid}: marked fetched from {host.group(1)}; no seat fetches sec.gov")
            # R4 quotes: public-domain text actually fetched, 25 words at most; nothing from a by-reference work
            q = str(s.get("quote") or "").strip()
            if q:
                if s.get("licence") != "PD":
                    add("FAIL", "R4", f"{where} {sid}: a quote from a {s.get('licence')} source (only public-domain "
                                      f"text may be quoted)")
                if not s.get("fetched"):
                    add("FAIL", "R4", f"{where} {sid}: a quote from a page not re-read in the run")
                if len(q.split()) > 25:
                    add("FAIL", "R4", f"{where} {sid}: a quote of {len(q.split())} words (25 at most)")
            # R7 by-reference works are licensed ref (or OD), never PD
            gov = re.match(r"https?://([^/]+\.)?[a-z0-9-]+\.gov(/|$)", str(s.get("url") or ""))   # US government text
            if re.search(BYREF, txt, re.I) and s.get("licence") == "PD" and not gov:
                add("FAIL", "R7", f"{where} {sid}: '{s.get('publisher') or s.get('title')}' is by reference only, "
                                  f"not public domain")
        # R3b investor.gov is phrasing material, never the only source
        if srcs and all(re.search(PHRASING_ONLY, str(s.get("url") or ""), re.I) for s in srcs):
            add("FAIL", "R3", f"{where}: investor.gov is its only source (phrasing material, never defining)")
        # R5 every threshold names the source that draws it
        ths = e.get("thresholds") or []
        for t in ths:
            line = t.get("line") or "?"
            if t.get("kind") not in KINDS and not str(t.get("kind") or "").startswith("withdrawn"):
                add("FAIL", "R5", f"{where}: threshold {line!r} kind {t.get('kind')!r}")
            sids = t.get("source_ids") or []
            if not sids and t.get("kind") == "definitional":
                # 1.4 (Research): an arithmetic line needs no source, when its meaning says it is arithmetic
                if not re.search(r"arithmetic|by definition|definitional|the sign|negative|positive", str(t.get("meaning") or "")
                                 + " " + str(t.get("line") or ""), re.I):
                    add("REVIEW", "R5", f"{where}: definitional line {line!r} names no source (arithmetic, or say which "
                                        f"definition makes it so)")
            elif not sids:
                add("FAIL", "R5", f"{where}: threshold {line!r} names no source (no line unless a named source draws it)")
            for sid in sids:
                if sid not in ids:
                    add("FAIL", "R5", f"{where}: threshold {line!r} cites {sid}, which is not among its sources")
        if ths and e.get("no_market_threshold") is True and any(t.get("kind") == "source-drawn" for t in ths):
            add("REVIEW", "R5", f"{where}: says no market threshold and lists a source-drawn one")
        if not ths and e.get("no_market_threshold") is not True:
            add("REVIEW", "R5", f"{where}: no threshold and no_market_threshold not set: say which")
        # R6b (1.4, Research): a fallback stands in for its primary, so it shares the primary's period type and item type
        if index is not None:
            for fg in e.get("figures") or []:
                prim = [x.split(":", 1)[1] for x in fg.get("xbrl") or [] if str(x).startswith("us-gaap:")]
                p0 = next((x for x in prim if x in index and index[x].get("period")), None)
                if p0 is None:
                    continue
                k0 = (index[p0].get("period"), text_kind(index[p0].get("type")))
                for x in fg.get("fallbacks") or []:
                    n = str(x).split(":", 1)[-1]
                    if str(x).startswith("us-gaap:") and n in index and index[n].get("period") and \
                            (index[n].get("period"), text_kind(index[n].get("type"))) != k0:
                        add("REVIEW", "R6", f"{where}: fallback {x} ({index[n].get('period')}, {index[n].get('type')}) "
                                            f"does not match its primary us-gaap:{p0} ({k0[0]}, {k0[1]}) in "
                                            f"'{fg.get('name')}'")
        # R6 elements named well; checked against FASB's index when it is cached
        rowtext = " ".join([str(fg.get("notes") or "") for fg in e.get("figures") or []] +
                           [str(p) for p in e.get("pitfalls") or []] + [str(e.get("notes") or "")])
        for fg in e.get("figures") or []:
            for el in list(fg.get("xbrl") or []) + list(fg.get("fallbacks") or []):
                m = re.fullmatch(r"(us-gaap|dei|srt|ifrs-full|[a-z-]+):([A-Za-z0-9_]+)", str(el))
                if not m:
                    add("REVIEW", "R6", f"{where}: element {el!r} is not prefix:Name")
                elif index is not None and m.group(1) == "us-gaap":
                    x = index.get(m.group(2))
                    # a row may name a removed element on purpose, for older filings; it must say so itself
                    legacy = re.search(rf"{m.group(2)}[^|;]*?(deprecat|older filings|legacy|removed|gone from|absent from)",
                                       rowtext, re.I)
                    lvl = "INFO" if legacy else "REVIEW"
                    if x is None:
                        add(lvl, "R6", f"{where}: {el} is absent from FASB's {index.get('__year__', '')} taxonomy"
                                       + (" (the row names it as a legacy fallback)" if legacy else ""))
                    elif x.get("dep"):
                        add(lvl, "R6", f"{where}: {el} is deprecated (replaced by {x['dep'][0][1]})"
                                       + (" (the row names it as a legacy fallback)" if legacy else ""))
        # R10 a source of record (a Research doc) must exist on main
        if e.get("record") and repo is not None:
            path = str(e["record"]).split(" ")[0].split("#")[0]
            if not on_main(path, repo):
                add("FAIL", "R10", f"{where}: source of record {path} is not on main")
        # R11 (1.1) a duplicate row points to the canonical one, which must exist and not point on again
        if e.get("see"):
            tgt = R["by_id"].get(e["see"])
            if tgt is None:
                add("FAIL", "R11", f"{where}: see {e['see']!r}, which is not in the register")
            elif tgt.get("see"):
                add("FAIL", "R11", f"{where}: see {e['see']}, which itself points to {tgt['see']} (name the canonical row)")
        # R8 leads: nothing re-read
        if srcs and not any(s.get("fetched") for s in srcs):
            add("REVIEW", "R8", f"{where}: no source was re-read in the run (a lead until Research re-reads one)")
        rv = (e.get("review") or {}).get("research")
        if rv not in (None, "pending", "confirmed", "corrected"):
            add("FAIL", "R9", f"{where}: review.research {rv!r}")
        blob = " ".join(str(e.get(k) or "") for k in ("market_reading", "frame_notes", "notes", "formula")) + " " + \
               " ".join(str(p) for p in e.get("pitfalls") or [])
        qual = [q for q in e.get("questions") or [] if QUALIFIER.search(str(q))]
        if qual and not e.get("frames") and not i.startswith("QF-"):
            add("FAIL", "Q1", f"{where}: a qualifier question ({qual[0]!r}) with no named comparison frame "
                              f"(§0.1: 'low' needs a stated comparison, and Case names it)")
        for t in ths:
            pubs = " ".join(str(s.get("publisher") or s.get("title") or "") for s in srcs if s.get("id") in (t.get("source_ids") or []))
            # S&P Global Ratings' bands (S&P-adjusted figures and forecasts), not S&P Dow Jones Indices' GAAP-based rules
            if re.search(r"S&P Global Ratings|Standard & Poor'?s Ratings|RatingsDirect", pubs) and not re.search(r"S&P[- ]adjusted|adjusted", str(t.get("meaning") or "") + str(t.get("line") or "")):
                add("REVIEW", "Q2", f"{where}: threshold {t.get('line')!r} is S&P's: say it is on S&P-adjusted figures "
                                    f"and never applied to as-reported GAAP figures (§0.2)")
        cash_duration = [el for fg in e.get("figures") or [] if fg.get("period") == "duration"
                         for el in (fg.get("xbrl") or []) if re.search(r":(NetCash|PaymentsTo|ProceedsFrom|Repayments)", str(el))]
        if cash_duration and not re.search(r"year[- ]to[- ]date|\bYTD\b", blob, re.I):
            add("REVIEW", "Q4", f"{where}: reads {cash_duration[0]} but no pitfall says 10-Q cash flows are year-to-date "
                                f"(§0.4; Reg S-X 10-01(c)(3))")
        if re.search(r"current ratio|quick ratio|cash ratio|working capital|interest coverage|runway|cash burn",
                     " ".join([str(e.get("concept") or "")] + [str(x) for x in e.get("aka") or []]), re.I) \
                and not re.search(r"\bbank|lender|insurer|financial institution|broker|\bBDC\b", blob, re.I):
            add("REVIEW", "Q5", f"{where}: does not say this reads not applicable for lenders (banks, insurers, "
                                f"broker-dealers, BDCs) (§0.5)")
        if re.search(r"\bItem \d\.\d\d\b|8-K", " ".join(str(fg.get("name") or "") + " " + str(fg.get("notes") or "")
                                                          for fg in e.get("figures") or [])) \
                and not re.search(r"cannot establish|absence|not a finding", blob, re.I):
            add("REVIEW", "Q6", f"{where}: reads a filed event but never says its absence is not a finding (§0.6)")
    n = len(R["entries"])
    fetched = sum(1 for e in R["entries"] for s in e.get("sources") or [] if s.get("fetched"))
    total = sum(len(e.get("sources") or []) for e in R["entries"])
    add("INFO", "R0", f"{n} entries in {len(R['files'])} families; {fetched} of {total} sources re-read in the run; "
                      f"Research review: " + ", ".join(f"{k} {v}" for k, v in sorted(_count(R).items())))
    return out


def _count(R: dict) -> dict:
    c: dict = {}
    for e in R["entries"]:
        k = (e.get("review") or {}).get("research") or "pending"
        c[k] = c.get(k, 0) + 1
    return c


# ── find and read ───────────────────────────────────────────────────────────────────────────────────────────────────
def _vocab(R: dict) -> set:
    v = set()
    for e in R["entries"]:
        for f in ("concept", "aka", "questions"):
            x = e.get(f)
            for s in (x if isinstance(x, list) else [x]):
                v.update(words(s or ""))
    return v


def qwords(R: dict, text: str) -> list[str]:
    """The question's content words, with run-together words split where both halves are register words
    ('cashflow' -> cash, flow)."""
    v = _vocab(R)
    out = []
    for w in words(text):
        if w in STOP:
            continue
        out.append(w)
        if w not in v:
            for k in range(3, len(w) - 2):
                if w[:k] in v and w[k:] in v:
                    out += [w[:k], w[k:]]
                    break
    return out


def score(R: dict, text: str) -> list[tuple[float, dict]]:
    q = qwords(R, text)
    if not q:
        return []
    N = len(R["entries"])
    docs = []
    df: dict = {}
    for e in R["entries"]:
        strong = set(words(e.get("concept") or "")) | {w for a in (e.get("aka") or []) for w in words(a)}
        weak = {w for s in (e.get("questions") or []) for w in words(s)} | set(words(e.get("market_reading") or ""))
        docs.append((e, strong - STOP, weak - STOP))
        for w in (strong | weak) - STOP:
            df[w] = df.get(w, 0) + 1
    res = []
    for e, strong, weak in docs:
        s = 0.0
        for w in set(q):
            idf = math.log(1 + N / (1 + df.get(w, 0)))
            s += idf * (2.0 if w in strong else (1.0 if w in weak else 0.0))
        # a whole plain question in the entry is the strongest evidence
        qs = " ".join(words(text))
        if any(" ".join(words(x)) == qs for x in e.get("questions") or []):
            s += 10
        if s > 0:
            res.append((s, e))
    res.sort(key=lambda r: (-r[0], r[1].get("id") or ""))
    return res


def qualifiers(R: dict, text: str) -> list[dict]:
    """QF entries whose concept (the qualifier) is a word of the question: 'low', 'cheap', 'too much' ..."""
    ws = set(words(text))
    out = []
    for e in R["entries"]:
        if not str(e.get("id") or "").startswith("QF-"):
            continue
        names = [e.get("concept") or ""] + list(e.get("aka") or [])
        for n in names:
            nw = words(n)
            if nw and all(w in ws for w in nw) and len(nw) <= 3:
                out.append(e)
                break
    return out


def short(s, n=220) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def card(e: dict, full: bool) -> list[str]:
    rv = (e.get("review") or {}).get("research") or "pending"
    out = [f"{e.get('id')}  {e.get('concept')}  [{e['_family']}; confidence {e.get('confidence')}; Research review: {rv}]"]
    if e.get("record"):
        out.append(f"  source of record: {e['record']} (Research; it wins on any conflict with this row)")
    if e.get("see"):
        out.append(f"  canonical row: {e['see']} (this row points there; read both)")
    out.append(f"  reading: {short(e.get('market_reading'), 600 if full else 260)}")
    for fg in e.get("figures") or []:
        els = ", ".join(fg.get("xbrl") or []) or "no element"
        fb = f"; fallbacks {', '.join(fg['fallbacks'])}" if fg.get("fallbacks") else ""
        out.append(f"  figure: {fg.get('name')} = {els}{fb} ({fg.get('period') or '?'}; {fg.get('sign') or ''})".rstrip("; )") + ")")
        if full and fg.get("notes"):
            out.append(f"    note: {short(fg['notes'], 400)}")
    if e.get("formula"):
        out.append(f"  formula: {short(e['formula'], 300)}")
    if e.get("period_convention"):
        out.append(f"  period: {short(e['period_convention'], 200)}")
    if e.get("frames"):
        out.append(f"  frames: {', '.join(e['frames'])}" + (f" — {short(e.get('frame_notes'), 400 if full else 200)}" if e.get("frame_notes") else ""))
    ths = e.get("thresholds") or []
    if ths:
        for t in ths:
            owner = ", ".join(t.get("source_ids") or []) or "arithmetic: the definition itself, no source named"
            if str(t.get("kind") or "").startswith("withdrawn"):
                out.append(f"  WITHDRAWN line (historical; never a current line): {t.get('line')} [{t.get('kind')}; "
                           f"{owner}] {short(t.get('meaning'), 200)}")
                continue
            if t.get("kind") == "owner-specific":
                pubs = "; ".join(str(x.get("publisher") or x.get("title") or x.get("id")) for x in e.get("sources") or []
                                 if x.get("id") in (t.get("source_ids") or [])) or owner
                out.append(f"  {short(pubs, 80)}'s line, for its own purpose; not a market threshold: {t.get('line')} "
                           f"[{owner}] {short(t.get('meaning'), 200)}")
                continue
            out.append(f"  line: {t.get('line')} [{t.get('kind')}; drawn by {owner}] "
                       f"{short(t.get('meaning'), 200)}")
    if e.get("no_market_threshold"):
        out.append("  no market threshold" + (f": {short(e.get('notes'), 300)}" if full and e.get("notes") else ""))
    if e.get("measurable_from_filings") is False:
        out.append("  NOT measurable from filings alone" + (f": {short(e.get('notes'), 200)}" if e.get("notes") and not full else ""))
    pit = e.get("pitfalls") or []
    for p in (pit if full else pit[:3]):
        out.append(f"  pitfall: {short(p, 400 if full else 200)}")
    if not full and len(pit) > 3:
        out.append(f"  (+{len(pit) - 3} more pitfalls: show {e.get('id')})")
    for s in e.get("sources") or []:
        if full:
            out.append(f"  {s.get('id')}: {s.get('title')} — {s.get('publisher')}, {s.get('date') or 'n.d.'} "
                       f"[tier {s.get('tier')}, {s.get('licence')}, {'re-read' if s.get('fetched') else 'lead, not re-read'}]"
                       f" {s.get('url') or ''}")
            if s.get("quote"):
                out.append(f"      \"{s['quote']}\"")
    if not full:
        n = len(e.get("sources") or [])
        f = sum(1 for s in e.get("sources") or [] if s.get("fetched"))
        out.append(f"  sources: {n} ({f} re-read) — show {e.get('id')} for each, with tier and licence")
    return out


def cmd_read(a) -> int:
    R = load(a.data)
    text = " ".join(a.question)
    hits = score(R, text)
    quals = qualifiers(R, text)
    print(f'reading of "{text}" from the register ({len(R["entries"])} entries). Not advice; every line cites its row.')
    if not a.no_rules:
        print(RULES0)
    if not hits:
        print("  not in the register: no entry matches. Send Research a request; do not reason one up.")
        return 1
    qids = {e.get("id") for e in quals}
    hits = [(s, e) for s, e in hits if e.get("id") not in qids] or hits   # a qualifier is shown once, as the qualifier
    top = hits[0][0]
    main = [e for s, e in hits if s >= 0.5 * top][:a.top]
    print(f"\nconcepts the question names (best first; {len(hits)} matched in all):")
    for e in main:
        print("\n".join(card(e, False)))
    if quals:
        print("\nthe qualifier, and the comparison that makes a number that word:")
        for e in quals:
            print("\n".join(card(e, False)))
    else:
        print("\nno qualifier entry matched: the question asks for a measure, not a judgement, or its qualifier is not "
              "in the register yet")
    return 0


def cmd_find(a) -> int:
    R = load(a.data)
    hits = score(R, " ".join(a.words))
    if not hits:
        print("nothing in the register matches")
        return 1
    for s, e in hits[:a.top]:
        print(f"{s:6.2f}  {e.get('id'):<7} {e.get('concept')}  [{e['_family']}]")
    return 0


def cmd_show(a) -> int:
    R = load(a.data)
    rc = 0
    for i in a.ids:
        e = R["by_id"].get(i)
        if not e:
            print(f"{i}: not in the register")
            rc = 1
            continue
        print("\n".join(card(e, True)) + "\n")
    return rc


def cmd_list(a) -> int:
    R = load(a.data)
    for e in R["entries"]:
        if a.family and not (e["_family"].lower().startswith(a.family.lower()) or str(e.get("id", "")).startswith(a.family.upper())):
            continue
        rv = (e.get("review") or {}).get("research") or "pending"
        print(f"{e.get('id'):<7} {e.get('concept')}  [{rv}]")
    return 0


def xbrl_index(path: str | None) -> dict | None:
    cands = [path] if path else glob.glob(os.path.join(os.environ.get("TMPDIR", "/tmp"), "siglia-xbrl-cache", "*",
                                                       "index-v*.json"))
    for p in sorted(c for c in cands if c)[::-1]:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            idx = dict(d.get("elements") or {})
            idx["__year__"] = d.get("year")
            return idx
    return None


def cmd_validate(a) -> int:
    R = load(a.data)
    idx = xbrl_index(a.elements) if not a.no_elements else None
    res = validate(R, idx)
    if idx is None and not a.no_elements:
        res.append(("INFO", "R6", "no siglia-xbrl-element index cached: elements checked for shape only (run "
                                  "siglia-xbrl-element once, or pass --elements PATH)"))
    order = {"FAIL": 0, "REVIEW": 1, "INFO": 2}
    for lvl, code, msg in sorted(res, key=lambda x: (order[x[0]], x[1], x[2])):
        if lvl == "REVIEW" and a.quiet:
            continue
        print(f"{lvl:<6} {code}  {msg}")
    n = {k: sum(1 for x in res if x[0] == k) for k in order}
    print(f"verdict: {'FAIL' if n['FAIL'] else ('REVIEW' if n['REVIEW'] else 'CLEAN')} "
          f"({n['FAIL']} FAIL, {n['REVIEW']} REVIEW)")
    return 1 if n["FAIL"] else 0


def cmd_elements(a) -> int:
    R = load(a.data)
    idx = xbrl_index(a.elements)
    names: dict = {}
    for e in R["entries"]:
        for fg in e.get("figures") or []:
            for el in list(fg.get("xbrl") or []) + list(fg.get("fallbacks") or []):
                names.setdefault(el, []).append(e.get("id"))
    rc = 0
    for el in sorted(names):
        pfx, _, n = el.partition(":")
        st = "not checked (no index)" if idx is None else (
            "not us-gaap: not checked" if pfx != "us-gaap" else
            ("ABSENT" if n not in idx else ("DEPRECATED -> " + idx[n]["dep"][0][1] if idx[n].get("dep") else "ok")))
        if st.startswith(("ABSENT", "DEPRECATED")):
            rc = 1
        print(f"{st:<24} {el}  ({', '.join(sorted(set(names[el])))})")
    return rc


_PATH = re.compile(r"([A-Za-z_]+)(?:\[([^\]]+)\])?")


def resolve(entry: dict, path: str):
    """A field path in a row -> (container, key, current value). 'no_market_threshold', 'thresholds[0].kind',
    'sources[S2].licence' (a source by its id), 'thresholds[+]' (append). Raises KeyError on a path that does not resolve."""
    parts = path.split(".")
    cur = entry
    for n, part in enumerate(parts):
        m = _PATH.fullmatch(part)
        if not m:
            raise KeyError(f"bad path part {part!r}")
        key, idx = m.group(1), m.group(2)
        last = n == len(parts) - 1
        if idx is None:
            if last:
                return cur, key, cur.get(key)
            if key not in cur:
                raise KeyError(f"no field {key!r}")
            cur = cur[key]
            continue
        lst = cur.setdefault(key, []) if idx == "+" else cur.get(key)
        if not isinstance(lst, list):
            raise KeyError(f"{key!r} is not a list")
        if idx == "+":
            if not last:
                raise KeyError("an append '[+]' must end the path")
            return lst, None, None
        if re.fullmatch(r"\d+", idx):
            i = int(idx)
            if i >= len(lst):
                raise KeyError(f"{key}[{i}] out of range ({len(lst)})")
        else:
            hits = [k for k, x in enumerate(lst) if isinstance(x, dict) and x.get("id") == idx]
            if not hits:
                raise KeyError(f"no {key} with id {idx!r}")
            i = hits[0]
        if last:
            return lst, i, lst[i]
        cur = lst[i]
    raise KeyError(path)


#: 1.5 (Research): a string and a text block both carry words, so a text-block fallback for a string primary (or the reverse)
#: is not a type mismatch for R6b; any other type difference still is
TEXT_TYPES = {"stringItemType", "textBlockItemType", "normalizedStringItemType"}


def text_kind(t):
    base = str(t or "").split(":")[-1]
    return "text" if base in TEXT_TYPES else base


def cmd_review(a) -> int:
    """Research's corrections, applied mechanically and all-or-nothing; each change logged in the row with its source."""
    with open(a.file, encoding="utf-8") as fh:
        items = json.load(fh)
    if not isinstance(items, list):
        print("review: the file must hold a JSON list", file=sys.stderr)
        return 2
    files = {}
    for f in sorted(glob.glob(os.path.join(a.data, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            files[f] = json.load(fh)
    rows = {e.get("id"): (f, e) for f, d in files.items() for e in d.get("entries") or []}
    errors, changes, skipped, changed = [], [], [], set()
    for n, it in enumerate(items):
        iid, field, verdict = it.get("id"), it.get("field"), it.get("verdict")
        if field == "@new":
            # 1.5 (Research's RF-48): a NEW row, whole, into its family's file (the file whose ids share its prefix)
            row = it.get("should_be")
            if not isinstance(row, dict) or row.get("id") != iid:
                errors.append(f"item {n} ({iid}): an @new row must be the whole row, with id {iid!r}")
                continue
            if not (it.get("url") and it.get("accessed")):
                errors.append(f"item {n} ({iid}): a new row without its url and access date")
                continue
            if iid in rows:
                old = {k: v for k, v in rows[iid][1].items() if k != "review"}
                if old == row:
                    skipped.append(f"{iid}: @new already in the register")
                else:
                    errors.append(f"item {n} ({iid}): @new, but {iid} is already in the register with other content")
                continue
            pre = str(iid).split("-")[0] + "-"
            fam = next((f for f, d in files.items() if any(str(e.get("id", "")).startswith(pre) for e in d.get("entries") or [])), None)
            if fam is None:
                errors.append(f"item {n} ({iid}): no family file holds {pre}* rows")
                continue
            new = dict(row)
            log = {k: it.get(k) for k in ("field", "why", "url", "accessed")}
            log.update(was=None, now="(the row)", quote=" ".join(str(it.get("quote") or "").split()[:25]), by=a.by, verdict=verdict)
            new["review"] = {"research": verdict, "log": [log]}
            files[fam].setdefault("entries", []).append(new)
            rows[iid] = (fam, new)
            changed.add(fam)
            changes.append(f"{iid}: a new row in {os.path.basename(fam)} — {short(it.get('why'), 90)}")
            continue
        if iid not in rows:
            errors.append(f"item {n}: id {iid!r} is not in the register")
            continue
        if verdict not in ("confirmed", "corrected"):
            errors.append(f"item {n} ({iid}): verdict {verdict!r} (want confirmed or corrected)")
            continue
        if verdict == "corrected" and not field:
            errors.append(f"item {n} ({iid}): a correction names no field")
            continue
        if verdict == "corrected" and not (it.get("url") and it.get("accessed")):
            errors.append(f"item {n} ({iid}): a correction without its url and access date (every correction records "
                          f"the re-read)")
            continue
        f, e = rows[iid]
        # 1.5: idempotent. An item whose change the row's own log already records is skipped: re-running a batch
        # writes nothing new (1.4 re-logged every item and appended list values twice).
        prior = (e.get("review") or {}).get("log") or []
        want = json.dumps(it.get("should_be") if field else None, sort_keys=True)
        if any(l.get("field") == field and json.dumps(l.get("now"), sort_keys=True) == want and
               (field or (l.get("url") == it.get("url") and l.get("accessed") == it.get("accessed"))) for l in prior):
            skipped.append(f"{iid}: {field or '(the row)'} already applied")
            continue
        was = None
        if field:
            try:
                cont, key, was = resolve(e, field)
            except KeyError as ex:
                errors.append(f"item {n} ({iid}): field {field!r} does not resolve: {ex}")
                continue
            if key is None:
                cont.append(it.get("should_be"))
            else:
                cont[key] = it.get("should_be")
        q = " ".join(str(it.get("quote") or "").split()[:25])
        log = {k: it.get(k) for k in ("field", "why", "url", "accessed")}
        log.update(was=was, now=it.get("should_be") if field else None, quote=q, by=a.by, verdict=verdict)
        rv = e.setdefault("review", {})
        if rv.get("research") != "corrected":   # one correction marks the row corrected; confirmations never undo it
            rv["research"] = verdict
        rv.setdefault("log", []).append(log)
        changed.add(f)
        changes.append(f"{iid}: {field or '(the row)'} {verdict}" + (f": {short(was, 60)} -> {short(it.get('should_be'), 60)}"
                                                                        if field else "") + f" — {short(it.get('why'), 90)}")
    if errors:
        print(f"review: REFUSED, nothing written — {len(errors)} of {len(items)} item(s) do not apply:")
        for x in errors:
            print(f"  {x}")
        return 2
    for c in changes:
        print(f"  {c}")
    for x in skipped:
        print(f"  skipped: {x}")
    sk = f"; {len(skipped)} already applied (skipped)" if skipped else ""
    if not changes:
        print(f"review: nothing to apply{sk}; nothing written")
        return 0
    # 1.5: the RESULT is validated before anything is written, in a dry run too. 1.4 wrote first and validated after, so
    # a batch whose dry run read "clean" (batch 5, 24 Sep: a quote on a by-reference source) left a FAILing register.
    res = validate(build(files), None)
    fails = [x for x in res if x[0] == "FAIL"]
    if fails:
        for lvl, code, msg in fails:
            print(f"FAIL   {code}  {msg}")
        print(f"review: REFUSED, nothing written — with these {len(changes)} change(s) the register would not validate "
              f"({len(fails)} FAIL){sk}")
        return 2
    if a.dry_run:
        print(f"review: {len(changes)} change(s) would apply and the register would validate (dry run; nothing written){sk}")
        return 0
    touched = changed
    for f in sorted(touched):
        tmp = f + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(files[f], fh, indent=1, ensure_ascii=False)
        os.replace(tmp, f)
    print(f"review: {len(changes)} change(s) applied to {len(touched)} file(s){sk}; re-validating")
    R = load(a.data)
    res = validate(R, None)
    n = {k: sum(1 for x in res if x[0] == k) for k in ("FAIL", "REVIEW")}
    for lvl, code, msg in res:
        if lvl == "FAIL":
            print(f"FAIL   {code}  {msg}")
    print(f"validate after review: {n['FAIL']} FAIL, {n['REVIEW']} REVIEW")
    return 1 if n["FAIL"] else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="concepts.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=DATA, help="the register directory (default: this skill's data/)")
    s = p.add_subparsers(dest="cmd", required=True)
    r = s.add_parser("read")
    r.add_argument("question", nargs="+")
    r.add_argument("--top", type=int, default=3)
    r.add_argument("--no-rules", action="store_true", help="omit Research's six rules above the reading")
    f = s.add_parser("find")
    f.add_argument("words", nargs="+")
    f.add_argument("--top", type=int, default=10)
    sh = s.add_parser("show")
    sh.add_argument("ids", nargs="+")
    ls = s.add_parser("list")
    ls.add_argument("--family")
    v = s.add_parser("validate")
    v.add_argument("--elements", help="a siglia-xbrl-element index-v*.json (default: the cached one, if any)")
    v.add_argument("--no-elements", action="store_true")
    v.add_argument("--quiet", action="store_true", help="hide REVIEW lines")
    el = s.add_parser("elements")
    el.add_argument("--elements")
    rv = s.add_parser("review")
    rv.add_argument("file", help="a JSON list of {id, field, should_be, why, url, quote, accessed, verdict}")
    rv.add_argument("--dry-run", action="store_true")
    rv.add_argument("--by", default="Research")
    a = p.parse_args(argv)
    return {"read": cmd_read, "find": cmd_find, "show": cmd_show, "list": cmd_list, "validate": cmd_validate,
            "elements": cmd_elements, "review": cmd_review}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
