#!/usr/bin/env python3
"""eq.py — siglia-earnings-quality: which earnings-quality signals a set of supplied XBRL facts shows, each with its
definition and source, and never a verdict.

Part of the siglia-earnings-quality skill (SKILL.md, one folder up). The reference is data/*.json: signals.json (each
signal's definition, formula, elements, rules and pitfalls, each row with its source), rules.json (periods,
restatements, lenders, Regulation G and S-K Item 10(e), Research's 26 Sep 2026 rulings on gross margin and capex, the
words never printed) and annex.json (ER-001's rubric rows as Research ruled them). No signal carries a line: Research
has not ruled on earnings-quality thresholds.

  eq.py signals FACTS.json [--json]   the signals the facts show: cash conversion, accruals, receivables against revenue,
                                      one-off items, the company's non-GAAP measures, capex and capitalised costs,
                                      stock-based pay and the perimeter, each with its measured value, facts, definition
                                      and source
  eq.py explain KEY                   a signal (accruals), a rule (regg_100a), an ER-001 row (T4) or a CFR section (244.101)
  eq.py list                          every signal, rule and ER-001 row
  eq.py validate                      the reference's shape and sources; with the register beside it and in a checkout,
                                      every register row, Research note, ruled rubric row and cached CFR section cited
Exit: signals 0 a signal shown / 1 none shown / 2 bad input / 3 a never-printed word reached the text · explain and list
0 / 1 unknown · validate 0 clean / 1 a FAIL
Read-only and offline: it reads the files named, the register beside it and the checkout; it writes and fetches nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys

VERSION = "1.2"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("EQ_DATA") or os.path.join(HERE, "..", "data")
FILES = ("signals", "rules", "annex")
QUOTED = re.compile(r'"[^"\n]*"')
CALLER = re.compile(r"\b[A-Za-z][\w-]*:[A-Za-z]\w*|\bfacts? [^\s,;():]+|\bfact[^\s,;():]*")
# every source part is one of these named forms; none is a path, so the skill reads the same outside its repository
SOURCE_FORMS = (
    re.compile(r"^siglia-fin-concepts [A-Z]{2}-\d{2}$"),                        # a register row
    re.compile(r"^Research \d{4}-\d{2}-\d{2} [a-z0-9-]+( §\d+)?$"),             # a Research note, by date and name
    re.compile(r"^Research ruling \d{4}-\d{2}-\d{2} \([a-z ,&-]+\)$"),          # a ruling Research sent as a message
    re.compile(r"^ER-001 [A-Z]{1,2}\d+ \(ruled \d{4}-\d{2}-\d{2}\)$"),          # a rubric row as Research ruled it
    re.compile(r"^ER-001 \(unverified\) GAPS\.md G\d+$"),                       # a GAPS row, never ruled
    re.compile(r"^(12|17) CFR \d+\.\d+(-\d+)?(\([A-Za-z0-9]+\))*$"),            # a CFR section (cached eCFR)
    re.compile(r"^FASB US GAAP Taxonomy 2026 \(siglia-xbrl-element\)$"),        # FASB's element files
    re.compile(r"^Corpus pack \(next6_packs_clean\.json, earnings-quality\)$"),  # the corpus measurements
)
NO_YEAR = "annual duration, so no fiscal year is read"
RULED_STATUS = re.compile(r"^ER-001 ruled (\d{4}-\d{2}-\d{2}): (CODE|SOURCE-CHECK|JUDGE)$")


class InputError(Exception):
    pass


class Conflict(Exception):
    pass


# ---------------------------------------------------------------- the reference

def load(d: str | None = None) -> dict:
    d = d or DATA
    return {k: json.load(open(os.path.join(d, k + ".json"))) for k in FILES}


def rule(data: dict, rid: str) -> dict:
    return next(r for r in data["rules"]["rules"] if r["id"] == rid)


def sig(data: dict, sid: str) -> dict:
    return next(s for s in data["signals"]["signals"] if s["id"] == sid)


def els(s: dict, role: str) -> list:
    return next(i["elements"] for i in s["inputs"] if i["role"] == role)


# ---------------------------------------------------------------- formatting (ER-001 T6, X2)

def money(v: float) -> str:
    a = abs(v)
    return ("-" if v < 0 else "") + (f"${a / 1e9:.2f}bn" if a >= 1e9 else f"${a / 1e6:.2f}m")


def pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def times(v: float) -> str:
    return f"{v:.2f}x"


def pp(v: float) -> str:
    return f"{abs(v) * 100:.2f} pp"


def direction(prior, cur) -> str:
    """The sign's word, from BOTH periods' figures (ER-001 X2 as ruled: a direction word needs the comparison fact)."""
    if prior is None or cur is None:
        raise ValueError("a direction word needs both periods' figures (ER-001 X2)")
    return "higher" if cur > prior else "lower" if cur < prior else "unchanged"


def loss_change(prior: float, cur: float) -> str:
    """A loss in both years narrowed or widened, never improved (ER-001 X2 as ruled)."""
    if not (prior < 0 and cur < 0):
        raise ValueError("narrowed or widened describes a loss in both years")
    return "narrowed" if abs(cur) < abs(prior) else "widened" if abs(cur) > abs(prior) else "was unchanged"


def span(fy) -> str:
    return f"FY {fy[0]} to {fy[1]}"


def cite(f: dict) -> str:
    return f"fact {f['id']}, {f['element']}"


# ---------------------------------------------------------------- the facts

def _date(v, fid: str, field: str):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise InputError(f"{fid}: {field} {v!r} is not a date (YYYY-MM-DD)") from None


def norm(raw, i: int) -> dict:
    if not isinstance(raw, dict):
        raise InputError(f"fact {i}: not an object")
    fid = str(raw.get("id") or f"fact[{i}]")
    el = raw.get("element") or (f"{raw.get('taxonomy') or 'us-gaap'}:{raw['tag']}" if raw.get("tag") else None)
    if not el:
        raise InputError(f"{fid}: no element (give 'element', or 'tag' and 'taxonomy')")
    el = el if ":" in el else "us-gaap:" + el
    try:
        v = float(raw.get("value_numeric", raw.get("value")))
    except (TypeError, ValueError):
        raise InputError(f"{fid}: value is not a number") from None
    if not math.isfinite(v):
        raise InputError(f"{fid}: value is not finite")
    end = raw.get("period_end", raw.get("end"))
    if not end:
        raise InputError(f"{fid}: no period_end")
    start = raw.get("period_start", raw.get("start"))
    return {"id": fid, "element": el, "value": v, "end": _date(end, fid, "period_end"),
            "start": _date(start, fid, "period_start") if start else None,
            "filed": _date(raw["filed"], fid, "filed") if raw.get("filed") else None,
            "accession": raw.get("accession_number") or raw.get("accession"),
            "form": raw.get("form_type") or raw.get("form"), "unit": raw.get("unit"),
            "superseded_by": raw.get("superseded_by")}


class Book:
    """The supplied facts, as last restated: superseded facts are not read; among current facts for one element and period
    the latest filed wins; current facts that disagree with no later filing date between them are a conflict."""

    def __init__(self, facts: list):
        self.dur, self.inst, self.byid, self.conflicts = {}, {}, {}, {}
        self.replaced, self.dropped, self.other_unit, self.read = [], 0, 0, 0
        groups: dict = {}
        for i, raw in enumerate(facts):
            f = norm(raw, i)
            if f["superseded_by"]:
                self.dropped += 1
                continue
            if f["unit"] not in (None, "", "USD"):
                self.other_unit += 1
                continue
            self.read += 1
            self.byid[f["id"]] = f
            groups.setdefault((f["element"], f["start"], f["end"]), []).append(f)
        for key, fs in groups.items():
            fs = sorted(fs, key=lambda x: x["filed"] or dt.date.min)
            win = fs[-1]
            if len({x["value"] for x in fs}) > 1:
                rivals = [x for x in fs[:-1] if x["value"] != win["value"]]
                if not win["filed"] or any(not x["filed"] or x["filed"] >= win["filed"] for x in rivals):
                    self.conflicts[key] = [x["id"] for x in fs]
                    continue
                self.replaced.append((win, rivals))
            if win["start"] is None:
                self.inst.setdefault(win["element"], {})[win["end"]] = win
            else:
                self.dur.setdefault(win["element"], {})[(win["start"], win["end"])] = win

    def _check(self, key):
        if key in self.conflicts:
            when = f"{key[1]} to {key[2]}" if key[1] else str(key[2])
            raise Conflict(f"{key[0]} for {when}: facts {', '.join(self.conflicts[key])} disagree, and no later filing "
                           "date settles which is current")

    def get(self, elements, fy):
        for el in elements:
            self._check((el, fy[0], fy[1]))
            f = self.dur.get(el, {}).get(fy)
            if f:
                return f
        return None

    def at(self, elements, day):
        for el in elements:
            self._check((el, None, day))
            f = self.inst.get(el, {}).get(day)
            if f:
                return f
        return None

    def latest_end(self):
        ends = [f["end"] for f in self.byid.values()]
        return max(ends) if ends else None


class Ctx:
    def __init__(self, data: dict, doc: dict):
        if not isinstance(doc, dict):
            raise InputError("FACTS.json is not an object")
        if not isinstance(doc.get("facts"), list):
            raise InputError("FACTS.json has no 'facts' list")
        self.data, self.doc, self.book = data, doc, Book(doc["facts"])
        ad = rule(data, "annual_duration")["values"]
        self.lo, self.hi = ad["min_days"], ad["max_days"]
        self.gap = rule(data, "fiscal_chain")["values"]["gap_days"]
        self.cc = sig(data, "cash_conversion")
        self.revenue = els(sig(data, "receivables_vs_revenue"), "revenue")
        anchors = els(self.cc, "ocf") + els(self.cc, "earnings") + self.revenue + els(sig(data, "one_off_items"), "operating_income")
        self.chain = self.fiscal_years(anchors)
        disc = els(sig(data, "perimeter"), "discontinued")
        self.disc = {fy: self.discontinued(disc, fy) for fy in self.chain}
        self.lender = self.lender_type()
        self.bank, self.bank_open = self.bank_type()

    def annual(self, s, e) -> bool:
        """52 or 53 weeks: 364 to 371 days counting the start and the end date (ER-001 X1 as ruled)."""
        return s is not None and self.lo <= (e - s).days + 1 <= self.hi

    def fiscal_years(self, anchors) -> list:
        spans = {k for el in anchors for k in self.book.dur.get(el, {}) if self.annual(*k)}
        if not spans:
            return []
        chain = [max(spans, key=lambda p: (p[1], p[0]))]
        while len(chain) < 5:
            prev = [p for p in spans if self.gap[0] <= (chain[-1][0] - p[1]).days <= self.gap[1]]
            if not prev:
                break
            chain.append(max(prev, key=lambda p: p[1]))
        return chain

    def discontinued(self, elements, fy) -> list:
        out = []
        for el in elements:
            if (el, fy[0], fy[1]) in self.book.conflicts:
                out.append({"id": "/".join(self.book.conflicts[(el, fy[0], fy[1])]), "element": el, "value": float("nan")})
            f = self.book.dur.get(el, {}).get(fy)
            if f and f["value"] != 0:
                out.append(f)
        return out

    def lender_type(self):
        """ER-001 X7 as ruled: registrant type and a Call Report or FR Y-9C link decide first, never SIC alone when they
        are supplied; then Research's three tests (case-question-readings section 11)."""
        rt = self.doc.get("registrant_type")
        if rt not in (None, "") and not isinstance(rt, str):
            raise InputError("registrant_type is not a string")
        rt = (rt or "").strip().lower()
        if rt in rule(self.data, "lender_x7")["values"]["registrant_types"]:
            return f"a {rt} registrant (17 CFR 229.1401(a); ER-001 X7)"
        for key, name in (("call_report", "Call Report"), ("fr_y9c", "FR Y-9C")):
            if self.doc.get(key):
                return f"linked to an {name} (ER-001 X7)" if name[0] == "F" else f"linked to a {name} (ER-001 X7)"
        if self.doc.get("bdc") is True:
            return "a business development company by its Form N-54A election (Research section 11, test 2)"
        sic = self.doc.get("sic")
        if sic in (None, ""):
            return None
        try:
            n = int(str(sic).strip())
        except ValueError:
            raise InputError(f"sic {sic!r} is not a number") from None
        alone = "" if rt else ("; decided by SIC alone, as no registrant type or Call Report link was supplied "
                               "(ER-001 X7)")
        if any(lo <= n <= hi for lo, hi in rule(self.data, "lender_test_1")["values"]["ranges"]):
            return f"SIC {n} (Research section 11, test 1){alone}"
        if n in rule(self.data, "lender_test_3")["values"]["codes"]:
            last = max((f["end"] for f in self.book.byid.values() if f["start"] is None), default=None)
            held = last and self.book.at(["us-gaap:AssetsCurrent", "us-gaap:LiabilitiesCurrent"], last)
            if not held:
                return (f"SIC {n}, with a latest balance sheet reporting neither AssetsCurrent nor LiabilitiesCurrent "
                        f"(Research section 11, test 3){alone}")
        return None

    def bank_type(self):
        """A bank for revenue (ER-001 X7 as ruled): bank revenue is net interest income plus noninterest income, which a
        Revenues fact does not hold. Only a registrant type or a Call Report or FR Y-9C link decides a bank; the switch
        never keys on SIC alone. A depository-institution SIC (rules.json bank_sic, 6011-6089) with neither supplied
        leaves the question open, so no revenue-based ratio is given and the line names what the facts lack; 6091
        (nondeposit trusts) and 6099 are not deposit banking. Returns (bank, open)."""
        x7 = rule(self.data, "lender_x7")["values"]
        rt = str(self.doc.get("registrant_type") or "").strip().lower()
        if rt in x7["registrant_types"] or self.doc.get("call_report") or self.doc.get("fr_y9c"):
            return self.lender, None
        try:
            n = int(str(self.doc.get("sic") or "").strip())
        except ValueError:
            return None, None
        if rt or not any(lo <= n <= hi for lo, hi in x7["bank_sic"]):
            return None, None
        return None, (f"SIC {n} is a depository-institution code, and SIC alone does not decide a bank (ER-001 X7); the "
                      "facts supplied hold no bank registrant type and no Call Report or FR Y-9C link")

    def nci_note(self, fy, e):
        """Operating cash flow is consolidated; NetIncomeLoss and IncomeLossFromContinuingOperations are attributable to the
        parent (FASB 2026). When the consolidated figure is held and differs, the noncontrolling interests' share is shown;
        a parent-only continuing figure with no consolidated one beside it is named as such (Research's B2 checks)."""
        if not e:
            return None
        cons = {"us-gaap:NetIncomeLoss": "us-gaap:ProfitLoss",
                "us-gaap:IncomeLossFromContinuingOperations":
                    "us-gaap:IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
                }.get(e["element"])
        if not cons:
            return None
        c = self.book.get([cons], fy)
        if c and c["value"] != e["value"]:
            return (f"{e['element']} is attributable to the parent, and operating cash flow is consolidated: {cons} is "
                    f"{money(c['value'])} (fact {c['id']}), {money(c['value'] - e['value'])} apart, the noncontrolling "
                    "interests' share, so the pair mixes perimeters by that amount.")
        if not c and e["element"] == "us-gaap:IncomeLossFromContinuingOperations":
            return (f"{e['element']} is attributable to the parent, and operating cash flow is consolidated; the facts "
                    f"supplied hold no {cons} to show the noncontrolling interests' share.")
        return None

    def pair(self, fy):
        """(earnings fact, operating cash flow fact, basis) for one fiscal year: the continuing-operations pair when
        discontinued operations are present and both are held (CF-08, CF-10); otherwise the total pair."""
        if self.disc.get(fy):
            e = self.book.get(els(self.cc, "earnings_continuing"), fy)
            o = self.book.get(els(self.cc, "ocf_continuing"), fy)
            if e and o:
                return e, o, "continuing operations"
            return (self.book.get(els(self.cc, "earnings"), fy), self.book.get(els(self.cc, "ocf"), fy),
                    "total, including discontinued operations")
        return (self.book.get(els(self.cc, "earnings") + els(self.cc, "earnings_continuing"), fy),
                self.book.get(els(self.cc, "ocf") + els(self.cc, "ocf_continuing"), fy), "total")

    def same_perimeter(self, cur, prior, facts) -> str | None:
        """None when two fiscal years compare like for like (ER-001 T4, B5); else the reason they do not."""
        if not (self.disc.get(cur) or self.disc.get(prior)):
            return None
        acc = {f.get("accession") for f in facts}
        if len(acc) == 1 and None not in acc:
            return None
        which = cur if self.disc.get(cur) else prior
        return (f"not compared: discontinued operations are present in {span(which)}, and the figures are not all from "
                "one filing (the recast comparative), so the perimeter may differ (ER-001 T4)")


# ---------------------------------------------------------------- the signals

def result(s: dict, status: str, lines: list, facts=(), values=None) -> dict:
    srcs = []
    for row in [s["definition"], s["formula"]] + s["inputs"] + s["rules"] + s["pitfalls"] + [s.get("not_applicable") or {}]:
        for part in (row.get("source") or "").split(" ; "):
            if part and part not in srcs:
                srcs.append(part)
    return {"id": s["id"], "title": s["title"], "status": status, "lines": lines, "facts": sorted(set(facts)),
            "values": values or {}, "register": s["register"], "definition": s["definition"]["text"],
            "definition_source": s["definition"]["source"], "sources": srcs}


def not_applicable(ctx: Ctx, s: dict) -> dict | None:
    if ctx.lender and s.get("not_applicable"):
        return result(s, "not_applicable", [f"not applicable: {ctx.lender}. {s['not_applicable']['text']}"])
    return None


def nothing(s: dict, what: str) -> dict:
    """A bounded absence (ER-001 X9 as ruled): what the facts supplied do not hold, named; never 'the company has no'."""
    return result(s, "not_held", [f"not computed: the facts supplied hold no {what}."])


def s_cash_conversion(ctx: Ctx) -> dict:
    s = ctx.cc
    na = not_applicable(ctx, s)
    if na:
        return na
    if not ctx.chain:
        return nothing(s, "annual operating cash flow or net income")
    rows, lines, facts, values = [], [], [], {}
    for fy in ctx.chain:
        e, o, basis = ctx.pair(fy)
        if not (e and o):
            rows.append((fy, None))
            continue
        facts += [e["id"], o["id"]]
        r = o["value"] / e["value"] if e["value"] > 0 else None
        rows.append((fy, {"e": e, "o": o, "basis": basis, "ratio": r}))
    cur = rows[0][1]
    if not cur:
        return nothing(s, f"annual pair of {' or '.join(els(s, 'ocf'))} and {' or '.join(els(s, 'earnings'))} for "
                          f"{span(ctx.chain[0])}")
    e, o = cur["e"], cur["o"]
    side = "below" if o["value"] < e["value"] else "above" if o["value"] > e["value"] else "equal to"
    head = (f"{span(ctx.chain[0])} ({cur['basis']}): operating cash flow {money(o['value'])} ({cite(o)}) against "
            f"earnings {money(e['value'])} ({cite(e)}); operating cash flow is {side} earnings")
    if cur["ratio"] is None:
        lines.append(head + f". Earnings are zero or below, so the ratio is not given: operating cash flow minus earnings = "
                            f"{money(o['value'] - e['value'])}.")
        values["difference"] = o["value"] - e["value"]
        prev = rows[1][1] if len(rows) > 1 else None
        if prev and prev["basis"] == cur["basis"] and prev["e"]["value"] < 0 and e["value"] < 0 \
                and not ctx.same_perimeter(ctx.chain[0], ctx.chain[1], [e, prev["e"]]):
            how = loss_change(prev["e"]["value"], e["value"])
            values["loss_change"] = how
            lines.append(f"the loss {how}: {money(-prev['e']['value'])} in {span(ctx.chain[1])} ({cite(prev['e'])}) "
                         f"and {money(-e['value'])} in {span(ctx.chain[0])}.")
    else:
        lines.append(head + f": {times(cur['ratio'])}.")
        values["ratio"] = cur["ratio"]
    nci = ctx.nci_note(ctx.chain[0], e)
    if nci:
        lines.append(nci)
    for (fy, r), (pfy, pr) in zip(rows, rows[1:]):
        if not pr:
            lines.append(f"{span(pfy)}: no annual pair held; the history stops here.")
            break
        if pr["ratio"] is None:
            lines.append(f"{span(pfy)} ({pr['basis']}): earnings zero or below, ratio not given; operating cash flow minus "
                         f"earnings = {money(pr['o']['value'] - pr['e']['value'])}.")
            continue
        why = None
        if r is None or r["ratio"] is None:
            why = "not compared: the later year has no ratio"
        elif r["basis"] != pr["basis"]:
            why = f"not compared: the basis differs ({r['basis']} against {pr['basis']}; ER-001 T4)"
        else:
            why = ctx.same_perimeter(fy, pfy, [r["e"], r["o"], pr["e"], pr["o"]])
        cmp_ = why or f"the ratio for {span(fy)} is {direction(pr['ratio'], r['ratio'])}"
        lines.append(f"{span(pfy)} ({pr['basis']}): {times(pr['ratio'])}; {cmp_}.")
        values.setdefault("history", []).append({"fiscal_year_end": str(pfy[1]), "ratio": pr["ratio"]})
    return result(s, "shown", lines, facts, values)


def s_accruals(ctx: Ctx) -> dict:
    s = sig(ctx.data, "accruals")
    na = not_applicable(ctx, s)
    if na:
        return na
    if not ctx.chain:
        return nothing(s, "annual earnings or operating cash flow")
    assets = els(s, "assets")
    lines, facts, values = [], [], {}
    for i, fy in enumerate(ctx.chain):
        e, o, basis = ctx.pair(fy)
        opening = ctx.chain[i + 1][1] if i + 1 < len(ctx.chain) else fy[0] - dt.timedelta(days=1)
        a1, a0 = ctx.book.at(assets, fy[1]), ctx.book.at(assets, opening)
        if not (e and o and a1 and a0):
            if i == 0:
                miss = [n for n, f in (("earnings", e), ("operating cash flow", o), (f"total assets at {fy[1]}", a1),
                                       (f"total assets at {opening}", a0)) if not f]
                return nothing(s, f"{', '.join(miss)} for {span(fy)}")
            break
        avg = (a0["value"] + a1["value"]) / 2
        if avg <= 0:
            lines.append(f"{span(fy)}: average total assets are zero or below; the ratio is not given.")
            continue
        acc = e["value"] - o["value"]
        facts += [e["id"], o["id"], a0["id"], a1["id"]]
        if i == 0:
            values = {"accruals": acc, "average_total_assets": avg, "ratio": acc / avg}
            sign = "earnings above operating cash flow" if acc > 0 else "earnings below operating cash flow" if acc < 0 else "earnings equal to operating cash flow"
            lines.append(f"{span(fy)} ({basis}): earnings {money(e['value'])} ({cite(e)}) less operating cash flow "
                         f"{money(o['value'])} ({cite(o)}) = accruals of {money(acc)}, {pct(acc / avg)} of average total "
                         f"assets ({money(avg)}: {money(a0['value'])} at {opening} and {money(a1['value'])} at {fy[1]}); "
                         f"{sign}.")
            nci = ctx.nci_note(fy, e)
            if nci:
                lines.append(nci)
            imp = [f for el in els(sig(ctx.data, "one_off_items"), "impairment") for f in [ctx.book.dur.get(el, {}).get(fy)] if f]
            if imp:
                lines.append("impairment facts are held for this year (" + ", ".join(f["id"] for f in imp) +
                             "): large impairments push accruals below zero without saying anything about cash (CF-10).")
        else:
            lines.append(f"{span(fy)} ({basis}): accruals of {money(acc)}, {pct(acc / avg)} of average total assets.")
            values.setdefault("history", []).append({"fiscal_year_end": str(fy[1]), "ratio": acc / avg})
    return result(s, "shown", lines, facts, values)


def _series(ctx: Ctx, elements, cur_key, prior_key, instant: bool):
    """(element, current fact, prior fact) on ONE element (QF-40), or raise Conflict naming the two elements."""
    get = ctx.book.at if instant else ctx.book.get
    for el in elements:
        c, p = get([el], cur_key), get([el], prior_key)
        if c and p:
            return el, c, p
    c, p = get(elements, cur_key), get(elements, prior_key)
    if c and p and c["element"] != p["element"]:
        raise Conflict(f"tagged {c['element']} ({c['id']}) and {p['element']} ({p['id']}); a comparison across "
                       "elements is refused (QF-40)")
    return None, c, p


def s_receivables(ctx: Ctx) -> dict:
    s = sig(ctx.data, "receivables_vs_revenue")
    na = not_applicable(ctx, s)
    if na:
        return na
    if len(ctx.chain) < 2:
        return nothing(s, "prior fiscal year chained to the latest one" if ctx.chain else "annual revenue")
    cur, prior = ctx.chain[0], ctx.chain[1]
    try:
        ar_el, ar1, ar0 = _series(ctx, els(s, "receivables"), cur[1], prior[1], True)
        rv_el, rv1, rv0 = _series(ctx, els(s, "revenue"), cur, prior, False)
    except Conflict as e:
        return result(s, "refused", [f"refused: {e}"])
    if not (ar_el and rv_el):
        miss = ([] if ar_el else [f"receivables on one element ({' or '.join(els(s, 'receivables'))}) at both {prior[1]} "
                                  f"and {cur[1]}"]) + \
               ([] if rv_el else [f"revenue on one element ({' or '.join(els(s, 'revenue'))}) for both fiscal years"])
        return nothing(s, "; and no ".join(miss))
    lines, values = [], {}
    days1, days0 = (cur[1] - cur[0]).days + 1, (prior[1] - prior[0]).days + 1
    dso1 = ar1["value"] / rv1["value"] * days1 if rv1["value"] > 0 else None
    dso0 = ar0["value"] / rv0["value"] * days0 if rv0["value"] > 0 else None
    lines.append(f"receivables ({ar_el}) {money(ar1['value'])} at {cur[1]} (fact {ar1['id']}) and {money(ar0['value'])} "
                 f"at {prior[1]} (fact {ar0['id']}); revenue ({rv_el}) {money(rv1['value'])} in {span(cur)} (fact "
                 f"{rv1['id']}) and {money(rv0['value'])} in {span(prior)} (fact {rv0['id']}).")
    why = ctx.same_perimeter(cur, prior, [ar1, ar0, rv1, rv0])
    if not why and (ctx.disc.get(cur) or ctx.disc.get(prior)):
        # ER-001 B5 as ruled: a revenue comparison with discontinued operations in either period carries its own
        # perimeter note, so a reader of this signal alone never gets the comparison without it
        held = "; ".join(f"{f['element']} {money(f['value']) if math.isfinite(f['value']) else 'in conflict'} (fact "
                         f"{f['id']}) in {span(fy)}" for fy in (cur, prior) for f in ctx.disc.get(fy, []))
        lines.append(f"perimeter note: discontinued operations are present ({held}); the comparatives are the recast "
                     "figures from one filing, so revenue and receivables compare on one perimeter (ER-001 B5).")
        values["perimeter_note"] = lines[-1]
    if why:
        lines.append(why + ".")
    elif ar0["value"] <= 0 or rv0["value"] <= 0:
        lines.append("growth not given: the prior year's base is zero or below (QF-28).")
    else:
        g_ar, g_rv = ar1["value"] / ar0["value"] - 1, rv1["value"] / rv0["value"] - 1
        rel = "above" if g_ar > g_rv else "below" if g_ar < g_rv else "equal to"
        lines.append(f"receivables growth {pct(g_ar)} is {rel} revenue growth {pct(g_rv)}" +
                     (f", by {pp(g_ar - g_rv)}." if rel != "equal to" else "."))
        values.update({"receivables_growth": g_ar, "revenue_growth": g_rv, "gap": g_ar - g_rv})
    if dso1 is not None and dso0 is not None:
        dso = (f"DSO (ending receivables / fiscal-year revenue x the year's days): {dso1:.2f} days at {cur[1]} "
               f"({days1}-day year) and {dso0:.2f} days at {prior[1]} ({days0}-day year)")
        lines.append(dso + (", each on its own year." if why else f"; {direction(dso0, dso1)} at {cur[1]}."))
        values.update({"dso": dso1, "dso_prior": dso0})
    ca = els(s, "contract_assets")
    c1, c0 = ctx.book.at(ca, cur[1]), ctx.book.at(ca, prior[1])
    if c1 or c0:
        held = "; ".join(f"{money(f['value'])} at {d} (fact {f['id']})" for f, d in ((c1, cur[1]), (c0, prior[1])) if f)
        lines.append(f"contract assets ({ca[0]}): {held}; shown apart and not in DSO (CF-17).")
    facts = [ar1["id"], ar0["id"], rv1["id"], rv0["id"]] + [f["id"] for f in (c1, c0) if f]
    return result(s, "shown", lines, facts, values)


def s_one_offs(ctx: Ctx) -> dict:
    s = sig(ctx.data, "one_off_items")
    if not ctx.chain:
        return nothing(s, NO_YEAR)
    fy = ctx.chain[0]
    lines, facts, values = [], [], {}
    for role in ("restructuring", "impairment", "settlement"):
        for el in els(s, role):
            f = ctx.book.get([el], fy)
            if not f:
                continue
            years = [str(y[1]) for y in reversed(ctx.chain) if ctx.book.dur.get(el, {}).get(y)]
            facts.append(f["id"])
            lines.append(f"{el} {money(f['value'])} (fact {f['id']}); held for the fiscal years ending {', '.join(years)}.")
            values.setdefault("items", []).append({"element": el, "value": f["value"], "years": years})
    if lines:
        lines.append("the lines are listed, never summed: filers tag impairments on different elements and totals (RF-12).")
    oi = ctx.book.get(els(s, "operating_income"), fy)
    rv = ctx.book.get(ctx.revenue, fy)
    named = ctx.doc.get("separately_presented") or []
    if not isinstance(named, list):
        raise InputError("separately_presented is not a list")
    if ctx.bank is not None:
        lines.append(f"operating margin not given: {ctx.bank}. Bank revenue is net interest income plus noninterest "
                     "income, which a Revenues fact does not hold (ER-001 X7; the captions are S-X 9-04's).")
    elif ctx.bank_open is not None:
        lines.append(f"operating margin not given: {ctx.bank_open}. A bank's revenue is net interest income plus "
                     "noninterest income, which a Revenues fact does not hold (ER-001 X7; the captions are S-X 9-04's).")
    elif oi and rv and rv["value"] > 0:
        m = oi["value"] / rv["value"]
        facts += [oi["id"], rv["id"]]
        values["operating_margin"] = m
        lines.append(f"operating margin as filed: {pct(m)} (operating income {money(oi['value'])}, fact {oi['id']}, over "
                     f"revenue {money(rv['value'])}, fact {rv['id']}).")
        adj, labels = oi["value"], []
        for n in named:
            if not isinstance(n, dict) or n.get("sign") not in ("expense", "income"):
                raise InputError("each separately_presented line needs a fact_id, a label and a sign of 'expense' or 'income'")
            f = ctx.book.byid.get(str(n.get("fact_id")))
            if not f or (f["start"], f["end"]) != fy:
                lines.append(f"separately presented line \"{n.get('fact_id')}\" is not an annual fact for {span(fy)}; not used.")
                continue
            adj = adj + f["value"] if n["sign"] == "expense" else adj - f["value"]
            facts.append(f["id"])
            labels.append(f"\"{n.get('label') or f['element']}\" ({money(f['value'])}, fact {f['id']}, {n['sign']})")
        if labels:
            values["operating_margin_excluding_named"] = adj / rv["value"]
            lines.append(f"operating margin excluding {', '.join(labels)}: {pct(adj / rv['value'])}. Siglia's arithmetic "
                         "on the filed lines named, shown beside the GAAP margin and never instead of it; it excludes amounts "
                         "included in GAAP operating income (17 CFR 244.101(a)(1); ER-001 T5).")
    if not lines:
        return result(s, "none", ["the facts supplied hold none of the one-off elements, and no operating income with "
                                  f"revenue, for {span(fy)}. An absence here is not a finding (X9): an impairment "
                                  "concluded while preparing a periodic report that discloses it on time needs no Item 2.06 "
                                  "8-K, and a restructuring plan whose charges are not material needs no Item 2.05 8-K."])
    return result(s, "shown", lines, facts, values)


def s_non_gaap(ctx: Ctx) -> dict:
    s = sig(ctx.data, "non_gaap_measures")
    ms = ctx.doc.get("company_measures") or []
    if not isinstance(ms, list):
        raise InputError("company_measures is not a list")
    if not ms:
        return result(s, "not_held", [
            "not computed: no company measure was supplied. The company's consolidated non-GAAP measures are not in the "
            "financial statements or notes (17 CFR 229.10(e)(1)(ii)(C)); a segment measure GAAP requires may carry an "
            "\"adjusted\" name in the notes and is not one (17 CFR 229.10(e)(5)). Read the company's measure and its "
            "reconciliation from the 8-K Item 2.02 exhibit or MD&A and supply it under company_measures."])
    lines, facts, values, byname, adjs = [], [], [], {}, {}
    for m in ms:
        if not isinstance(m, dict) or not m.get("name") or not m.get("period_end"):
            raise InputError("each company measure needs a name, a period_end, a value and a comparator_fact_id")
        try:
            v = float(m.get("value"))
        except (TypeError, ValueError):
            raise InputError(f"company measure {m.get('name')!r}: value is not a number") from None
        end = _date(m["period_end"], m["name"], "period_end")
        comp = ctx.book.byid.get(str(m.get("comparator_fact_id")))
        label = f"the company's \"{m['name']}\" for the period ending {end}"
        if not comp or comp["end"] != end:
            lines.append(f"{label}: refused, its GAAP comparator \"{m.get('comparator_fact_id')}\" is not a fact supplied for "
                         "the same period (PG-04).")
            continue
        gap = v - comp["value"]
        rel = gap / abs(comp["value"]) if comp["value"] else None
        facts.append(comp["id"])
        rec = m.get("reconciliation")
        rec_txt = (f"reconciliation: \"{rec}\"" if rec else
                   "reconciliation: the documents supplied print none; a measure given orally may instead be reconciled "
                   "on the company's website (17 CFR 244.100 Note 1), which is not among them")
        lines.append(f"{label}: {money(v)} against {comp['element']} {money(comp['value'])} (fact {comp['id']}); the gap is "
                     f"{money(gap)}" + (f", {pct(rel)} of the GAAP figure's absolute value" if rel is not None else "") +
                     f"; {rec_txt}" + (f"; from \"{m['source']}\"" if m.get("source") else "") + ".")
        values.append({"name": m["name"], "period_end": str(end), "value": v, "gaap": comp["value"], "gap": gap,
                       "relative_gap": rel, "reconciliation": rec})
        byname.setdefault(m["name"], []).append((end, gap))
        for a in m.get("adjustments") or []:
            adjs.setdefault((m["name"], a if isinstance(a, str) else str(a.get("label"))), set()).add(end)
    for name, pts in byname.items():
        pts = sorted(pts)
        for (e0, g0), (e1, g1) in zip(pts, pts[1:]):
            lines.append(f"the gap on \"{name}\" is {money(g1)} for the period ending {e1} against {money(g0)} for "
                         f"{e0}: {direction(g0, g1)}; compare only like with like, as definitions change over time (PG-04).")
    for (name, a), ends in sorted(adjs.items()):
        if len(ends) > 1:
            lines.append(f"the adjustment \"{a}\" to \"{name}\" is listed in the periods ending "
                         f"{', '.join(str(e) for e in sorted(ends))}.")
    return result(s, "shown" if values else "refused", lines, facts, {"measures": values})


def _named(fs) -> str:
    return "; ".join(f"{f['element']} {money(f['value'])} (fact {f['id']})" for f in fs)


def _software(ctx: Ctx, s: dict, fy):
    """Capitalised software as Research ruled it (26 Sep 2026): PaymentsForSoftware, the total, whenever it is held, with
    the parts held beside it inside it and never added; else PaymentsToDevelopSoftware + PaymentsToAcquireSoftware, each
    named. Returns (value or None, the facts that make the line, the parts held inside the total)."""
    tot = [f for el in els(s, "software") for f in [ctx.book.get([el], fy)] if f]
    parts = [f for el in els(s, "software_parts") for f in [ctx.book.get([el], fy)] if f]
    if tot:
        return tot[0]["value"], tot[:1], parts
    if parts:
        return sum(f["value"] for f in parts), parts, []
    return None, [], []


def _capex(ctx: Ctx, s: dict, fy, lines: list, facts: list, values: dict) -> None:
    """Capex as Research ruled it (26 Sep 2026): PP&E purchases and capitalised software, two named lines;
    PaymentsToAcquireProductiveAssets replaces the parts, never adds to them; free cash flow on it is non-GAAP."""
    ppe = [f for el in els(s, "ppe") for f in [ctx.book.get([el], fy)] if f]
    prod = [f for el in els(s, "productive") for f in [ctx.book.get([el], fy)] if f]
    sw_val, sw, inside = _software(ctx, s, fy)
    sw_txt = _named(sw) if len(sw) < 2 else " + ".join(_named([f]) for f in sw) + f" = {money(sw_val)}"
    total = None
    if prod:
        p = prod[0]
        facts += [p["id"]] + [f["id"] for f in ppe + sw + inside]
        total = p["value"]
        values.update(capex=total, capex_basis=p["element"])
        lines.append(f"capex: {_named([p])}, PP&E, software and other intangibles in one figure; it replaces the parts and "
                     "is never added to them (Research's capex ruling)" +
                     (f". The parts held sit inside it and are not added: {_named(ppe + sw + inside)}." if ppe + sw + inside
                      else "."))
    elif ppe or sw:
        facts += [f["id"] for f in ppe + sw + inside]
        if ppe and sw:
            total = ppe[0]["value"] + sw_val
            values.update(capex=total, capex_basis="PP&E purchases + capitalised software")
            lines.append(f"capex, as two named lines (Research's capex ruling): PP&E purchases {_named(ppe)} and capitalised "
                         f"software {sw_txt}; together {money(total)}.")
        elif ppe:
            total = ppe[0]["value"]
            values.update(capex=total, capex_basis="PP&E purchases")
            lines.append(f"capex: PP&E purchases {_named(ppe)}; the facts supplied hold no capitalised software line "
                         f"({' or '.join(els(s, 'software') + els(s, 'software_parts'))}), so capex is the PP&E line alone.")
        else:
            lines.append(f"capitalised software {sw_txt}; the facts supplied hold no PP&E purchase line, so no capex "
                         "total is given.")
    if sw_val is not None:
        values["software"] = sw_val
        values["software_basis"] = " + ".join(f["element"] for f in sw)
    if inside:
        lines.append(f"{_named(inside)}: inside {sw[0]['element']}, the software total, so not added to it (Research's "
                     "capex ruling).")
    if sw_val is not None and total and total > 0:
        values["software_share_of_capex"] = sw_val / total
        lines.append(f"capitalised software is {pct(sw_val / total)} of capex ({money(sw_val)} of {money(total)}).")
    if prod or ppe or sw:
        lines.append("a filer's investing line for capitalised software to be sold (ASC 985-20) is a filer extension or a "
                     "line the caller reads from the filing; this skill does not read it, so the capex shown leaves it out.")
    if total is not None:
        lines.append("free cash flow built on this capex is a non-GAAP measure, labelled so; this skill does not compute it.")


def s_capitalised(ctx: Ctx) -> dict:
    s = sig(ctx.data, "capitalised_costs")
    if not ctx.chain:
        return nothing(s, NO_YEAR)
    fy, lines, facts, values = ctx.chain[0], [], [], {}
    _capex(ctx, s, fy, lines, facts, values)
    for el in els(s, "interest"):
        f = ctx.book.get([el], fy)
        if f:
            facts.append(f["id"])
            values[el] = f["value"]
            lines.append(f"{el} {money(f['value'])} (fact {f['id']}): capitalised interest; the capitalised interest paid "
                         "sits inside capex, not operating cash flow (CF-04).")
            break
    ab, ex = ctx.book.get(els(s, "sbc_addback"), fy), ctx.book.get(els(s, "sbc_expense"), fy)
    if ab and ex:
        facts += [ab["id"], ex["id"]]
        values["sbc_gap"] = ab["value"] - ex["value"]
        lines.append(f"stock-based pay added back {money(ab['value'])} ({cite(ab)}) against {money(ex['value'])} expensed "
                     f"({cite(ex)}): a gap of {money(ab['value'] - ex['value'])}. The two can differ for capitalised pay, "
                     "liability-classified awards or discontinued operations; no single cause is asserted (CF-22).")
    status = "shown" if lines else "none"
    if not lines:
        lines.append(f"the facts supplied hold none of the capex or capitalised-cost elements for {span(fy)}; that is not "
                     "a finding (X9).")
    lines.append("contract costs capitalised under ASC 340-40: not in the register, so not read.")
    return result(s, status, lines, facts, values)


def s_sbc(ctx: Ctx) -> dict:
    s = sig(ctx.data, "sbc_share")
    if not ctx.chain:
        return nothing(s, NO_YEAR)
    fy = ctx.chain[0]
    sb = ctx.book.get(els(s, "sbc"), fy)
    if not sb:
        return result(s, "none", [f"the facts supplied hold no stock-based pay ({' or '.join(els(s, 'sbc'))}) for "
                                  f"{span(fy)}; that is not a finding (X9)."])
    # the add-back sits in TOTAL operating cash flow, so the base is the total figure (the continuing one only when no
    # discontinued operations are present, where the two are the same)
    o = ctx.book.get(els(ctx.cc, "ocf") + ([] if ctx.disc.get(fy) else els(ctx.cc, "ocf_continuing")), fy)
    rv = ctx.book.get(ctx.revenue, fy)
    parts, values, facts = [], {"sbc": sb["value"]}, [sb["id"]]
    if ctx.lender:
        parts.append(f"the share of operating cash flow is not given, as operating cash flow is not read for a "
                     f"lender-type filer ({ctx.lender})")
        o = None
    if ctx.bank:
        parts.append("the share of revenue is not given for a bank: bank revenue is net interest income plus noninterest "
                     "income (ER-001 X7)")
        rv = None
    elif ctx.bank_open:
        parts.append(f"the share of revenue is not given: {ctx.bank_open}")
        rv = None
    for name, f, key in (("operating cash flow", o, "of_ocf"), ("revenue", rv, "of_revenue")):
        if not f:
            continue
        facts.append(f["id"])
        if f["value"] > 0:
            values[key] = sb["value"] / f["value"]
            parts.append(f"{pct(sb['value'] / f['value'])} of {name} ({money(f['value'])}, fact {f['id']})")
        else:
            parts.append(f"{name} is {money(f['value'])} (fact {f['id']}), zero or below, so no share is given")
    return result(s, "shown", [f"stock-based pay {money(sb['value'])} ({cite(sb)}) in {span(fy)}" +
                               (": " + "; ".join(parts) if parts else "; neither operating cash flow nor revenue is held") +
                               "."], facts, values)


def s_perimeter(ctx: Ctx) -> dict:
    s = sig(ctx.data, "perimeter")
    if not ctx.chain:
        return nothing(s, NO_YEAR)
    lines, facts, groups = [], [], []
    for fy in ctx.chain[:2]:
        for f in ctx.disc.get(fy, []):
            facts.append(f["id"])
            val = money(f["value"]) if math.isfinite(f["value"]) else "in conflict"
            lines.append(f"discontinued operations are present in {span(fy)}: {f['element']} {val} (fact {f['id']}).")
        # a disposal group's revenue is named, and alone it never marks discontinued operations present (FASB 2026)
        for el in els(s, "disposal_group"):
            f = ctx.book.dur.get(el, {}).get(fy)
            if f and f["value"] != 0:
                facts.append(f["id"])
                groups.append(f"a disposal group's revenue is held for {span(fy)}: {el} {money(f['value'])} (fact "
                              f"{f['id']}); a disposal group need not be a discontinued operation, so alone it does not "
                              "change the perimeter.")
    if not lines:
        where = " or ".join(span(fy) for fy in ctx.chain[:2])
        if groups:
            return result(s, "shown", groups + [f"the facts supplied hold no element of discontinued operations for {where}"
                                                "; the comparisons are on the total perimeter."], facts)
        return result(s, "none", ["the facts supplied hold no discontinued-operations element for " + where +
                                  "; the comparisons are on the total perimeter. An absence here is not a finding (X9)."])
    lines += groups
    lines.append("so cash conversion and accruals use the continuing-operations pair when it is held, and a year-over-year "
                 "comparison, revenue included, needs its figures from one filing, or it is not made (ER-001 T4, B5).")
    return result(s, "shown", lines, facts)


SIGNALS = (("cash_conversion", s_cash_conversion), ("accruals", s_accruals), ("receivables_vs_revenue", s_receivables),
           ("one_off_items", s_one_offs), ("non_gaap_measures", s_non_gaap), ("capitalised_costs", s_capitalised),
           ("sbc_share", s_sbc), ("perimeter", s_perimeter))


def signals(data: dict, doc: dict) -> dict:
    ctx = Ctx(data, doc)
    b = ctx.book
    notes = []
    if ctx.chain:
        last = b.latest_end()
        if last and last > ctx.chain[0][1]:
            late = sorted((f for f in b.byid.values() if f["end"] == last), key=lambda f: f["id"])[0]
            notes.append(f"a later period is held (fact {late['id']} ends {last}): this reading is on the latest fiscal "
                         "year, and the latest window needs the TTM roll, which this skill does not build (ER-001 G29).")
        for fy in ctx.chain[:2]:
            for el in sorted({e for sid in ("cash_conversion", "receivables_vs_revenue") for i in sig(data, sid)["inputs"]
                              for e in i["elements"]}):
                f = b.dur.get(el, {}).get(fy)
                if f and (f.get("form") or "").upper().startswith("10-Q"):
                    notes.append(f"an annual figure comes from a 10-Q: fact {f['id']} ({el}, {span(fy)}); a restatement "
                                 "or an error, not established which (rules: annual_from_10q).")
    for win, rivals in b.replaced:
        notes.append(f"fact {win['id']} (filed {win['filed']}) replaced " +
                     ", ".join(f"{r['id']} (filed {r['filed']})" for r in rivals) + f" for {win['element']}, as last restated.")
    if not ctx.lender and str(doc.get("sic") or "").strip() in {str(c) for c in rule(data, "reit_gap")["values"]["codes"]}:
        notes.append("SIC 6798 is not lender-type: a REIT is not a bank and keeps revenue (ER-001 X7); a mortgage REIT "
                     "lends, a gap SIC cannot separate (Research section 11).")
    sic = str(doc.get("sic") or "").strip()
    if ctx.bank is None and sic in {str(c) for c in rule(data, "lender_x7")["values"]["bank_sic_left_out"]}:
        notes.append(f"SIC {sic} is not read as a bank for revenue: 6091 (nondeposit trust facilities) and 6099 (functions "
                     "related to depository banking) are not deposit banking (ER-001 X7); a registrant type or a Call "
                     "Report link decides if the filer is a bank.")
    out = []
    for sid, fn in SIGNALS:
        try:
            out.append(fn(ctx))
        except Conflict as e:
            out.append(result(sig(data, sid), "refused", [f"refused: {e}"]))
    return {"skill": "siglia-earnings-quality", "version": VERSION, "entity": doc.get("entity"),
            "fiscal_years": [[str(a), str(z)] for a, z in ctx.chain], "lender_type": ctx.lender, "bank": ctx.bank,
            "bank_not_decided": ctx.bank_open,
            "facts": {"read": b.read, "superseded_not_read": b.dropped, "other_unit_not_read": b.other_unit,
                      "in_conflict": sum(len(v) for v in b.conflicts.values())},
            "notes": notes, "line": rule(data, "no_line")["text"], "signals": out}


def render(rep: dict) -> str:
    fys = rep["fiscal_years"]
    out = ["siglia-earnings-quality" + (f": \"{rep['entity']}\"" if rep.get("entity") else ""),
           "fiscal years read: " + ("; ".join(f"{a} to {z}" for a, z in fys) if fys else "none (no annual duration held)"),
           "lender-type: " + (f"yes, {rep['lender_type']}" if rep["lender_type"] else "no"),
           f"facts: {rep['facts']['read']} read, {rep['facts']['superseded_not_read']} superseded and not read, "
           f"{rep['facts']['other_unit_not_read']} in another unit and not read, {rep['facts']['in_conflict']} in conflict"]
    out += [f"note: {n}" for n in rep["notes"]]
    out.append(f"line: {rep['line']}")
    for s in rep["signals"]:
        out.append("")
        out.append(f"[{s['id']}] {s['title']}: {s['status'].replace('_', ' ')}")
        out += [f"  {ln}" for ln in s["lines"]]
        out.append(f"  definition: {s['definition']}")
        out.append(f"  source: {s['definition_source']} · register: {', '.join(s['register'])} · eq.py explain {s['id']}")
    return "\n".join(out)


def words_outside_quotes(text: str, never: list) -> list:
    """The never-printed words in TEXT outside a quoted span; caller-supplied names (quoted spans, element names, fact ids)
    are not the skill's words and are left out (ER-001 X8: an issuer's own words are quoted)."""
    bare = QUOTED.sub('""', text)
    bare = CALLER.sub(" ", bare).lower()
    return sorted({w for w in never if w in bare})


# ---------------------------------------------------------------- explain, list, validate

def explain(data: dict, key: str) -> str | None:
    k = key.strip()
    for s in data["signals"]["signals"]:
        if s["id"] == k.lower():
            out = [f"{s['id']}: {s['title']}", f"register: {', '.join(s['register'])} (siglia-fin-concepts)",
                   f"definition: {s['definition']['text']}  [{s['definition']['source']}]",
                   f"formula: {s['formula']['text']}  [{s['formula']['source']}]"]
            out += [f"input {i['role']}: {', '.join(i['elements']) or '(supplied by the caller)'}: {i['text']}  [{i['source']}]"
                    for i in s["inputs"]]
            out.append(f"period: {s['period']['text']}  [{s['period']['source']}]")
            out += [f"rule: {r['text']}  [{r['source']}]" for r in s["rules"]]
            out += [f"pitfall: {p['text']}  [{p['source']}]" for p in s["pitfalls"]]
            if s.get("not_applicable"):
                out.append(f"not applicable: {s['not_applicable']['text']}  [{s['not_applicable']['source']}]")
            nl = rule(data, "no_line")
            out.append(f"line: none. {nl['text']}  [{nl['source']}]")
            return "\n".join(out)
    for r in data["rules"]["rules"] + data["rules"]["evidence"]:
        if r["id"].lower() == k.lower():
            out = [f"{r['id']} ({r.get('kind', 'evidence')}): {r['text']}"]
            if r.get("quote"):
                out.append(f"quote: \"{r['quote']}\"")
            if r.get("values") and r["id"] != "words":
                out.append(f"values: {json.dumps(r['values'])}")
            out.append(f"source: {r['source']}")
            return "\n".join(out)
    for a in data["annex"]["rows"]:
        if a["key"].lower() == k.lower():
            return (f"{a['key']} ({a['part']}, {a['status']}): {a['text']}\n" +
                    (f"correction (Research's, it governs): {a['correction']}\n" if a.get("correction") else "") +
                    f"applied: {a['applied']}\nsource: {a['source']}\nrecall the row whole: kb.py rubric {a['key']}")
    if re.fullmatch(r"\d+\.[\d-]+", k):
        hits = [r for r in data["rules"]["rules"] if re.search(r"CFR " + re.escape(k) + r"(\(|$| |;)", r["source"])]
        if hits:
            return "\n".join(f"{r['id']}: {r['text']}  [{r['source']}]" for r in hits)
    return None


def listing(data: dict) -> str:
    out = ["signals:"] + [f"  {s['id']:<24} {s['title']}" for s in data["signals"]["signals"]]
    out += ["rules:"] + [f"  {r['id']:<24} {r['kind']}" for r in data["rules"]["rules"]]
    out += ["evidence:"] + [f"  {r['id']}" for r in data["rules"]["evidence"]]
    out += ["ER-001 rows (as Research ruled them; GAPS rows unverified):"] + \
           [f"  {a['key']:<6} {a['status']:<34} {a['text'][:80]}" for a in data["annex"]["rows"]]
    return "\n".join(out)


def roots() -> list:
    """"""
    cands = [os.environ.get("EQ_ROOT")]
    for cwd in (os.getcwd(), HERE):
        try:
            g = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel", "--git-common-dir"], capture_output=True,
                               text=True).stdout.split("\n")
        except OSError:
            continue
        if len(g) > 1 and g[0].strip():
            cands += [g[0].strip(), os.path.dirname(os.path.abspath(os.path.join(cwd, g[1].strip())))]
    out = []
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "docs", "research")) and c not in out:
            out.append(c)
    return out


def register_dir(rs: list):
    """siglia-fin-concepts' data folder: EQ_REGISTER, the sibling skill, or the one in a checkout."""
    cands = [os.environ.get("EQ_REGISTER"), os.path.join(HERE, "..", "..", "siglia-fin-concepts", "data")]
    cands += [os.path.join(r, ".claude", "skills", "siglia-fin-concepts", "data") for r in rs]
    return next((os.path.abspath(c) for c in cands if c and os.path.isfile(os.path.join(c, "CF.json"))), None)


def text_rows(obj, path=""):
    """Every dict carrying a 'text' (a factual row), with where it sits."""
    if isinstance(obj, dict):
        if "text" in obj:
            yield path, obj
        for k, v in obj.items():
            if k != "values":
                yield from text_rows(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from text_rows(v, f"{path}[{i}]")


def validate(data: dict) -> tuple[list, list]:
    fails, info = [], []
    never = rule(data, "words")["values"]["never"]
    for need, key in (("annual_duration", "min_days"), ("fiscal_chain", "gap_days"), ("lender_test_1", "ranges"),
                      ("lender_test_3", "codes"), ("reit_gap", "codes"), ("lender_x7", "registrant_types"),
                      ("lender_x7", "bank_sic"), ("lender_x7", "bank_sic_left_out"), ("words", "never")):
        try:
            rule(data, need)["values"][key]
        except (StopIteration, KeyError):
            fails.append(f"rules.json: {need} has no values.{key}, which eq.py reads")
    ids = [s["id"] for s in data["signals"]["signals"]]
    if len(ids) != len(set(ids)) or set(ids) != {sid for sid, _ in SIGNALS}:
        fails.append(f"signals.json: the signal ids {sorted(ids)} are not eq.py's {sorted(sid for sid, _ in SIGNALS)}")
    for s in data["signals"]["signals"]:
        for k in ("title", "register", "definition", "formula", "inputs", "period", "rules", "pitfalls"):
            if not s.get(k):
                fails.append(f"signal {s['id']}: no {k}")
        if s.get("line") is not None:
            fails.append(f"signal {s['id']}: carries a line; none ships until Research rules on thresholds")
        if re.search(r'"(threshold|thresholds|cutoff|floor|ceiling)"\s*:', json.dumps(s)):
            fails.append(f"signal {s['id']}: carries a threshold field; none ships until Research rules")
    for a in data["annex"]["rows"]:
        k, st = a.get("key", ""), a.get("status", "")
        if re.fullmatch(r"G\d+", k):
            ok = st == "ER-001 (unverified)" and f"ER-001 (unverified) GAPS.md {k}" in a.get("source", "")
        else:
            ok = bool(RULED_STATUS.match(st)) and f"ER-001 {k} (ruled " in a.get("source", "")
        if not ok:
            fails.append(f"annex {k}: status {st!r} is neither 'ER-001 ruled <date>: <class>' citing the ruled row nor, "
                         "for a GAPS row, ER-001 (unverified)")
    rows = sources = 0
    parts_all = []
    for f in FILES:
        for where, row in text_rows(data[f]):
            rows += 1
            src = row.get("source")
            if not src or not str(src).strip():
                fails.append(f"{f}.json {where}: a factual row with no source")
                continue
            for part in str(src).split(" ; "):
                sources += 1
                parts_all.append((f, where, part))
                if not any(p.match(part) for p in SOURCE_FORMS):
                    fails.append(f"{f}.json {where}: source {part!r} is not a recognised source form (a siglia-fin-concepts "
                                 "row, a Research note or ruling, a ruled ER-001 row, a CFR section, FASB's taxonomy or "
                                 "the Corpus pack)")
            # a ruling Research sent as a message is cited only beside the note or ruled row of its date that carries it,
            # which the repo checks below find (the 26 Sep gross-margin and capex rulings are in the ruled rubric rows)
            parts = str(src).split(" ; ")
            for part in parts:
                m = re.match(r"^Research ruling (\d{4}-\d{2}-\d{2}) ", part)
                if m and not any(re.match(r"^(Research %s [a-z0-9-]+( §\d+)?|ER-001 [A-Z]{1,2}\d+ \(ruled %s\))$"
                                          % (m.group(1), m.group(1)), q) for q in parts):
                    fails.append(f"{f}.json {where}: {part!r} stands alone: no Research note or ruled ER-001 row of "
                                 f"{m.group(1)} beside it carries the ruling, so nothing checks it")
            for field in ("text", "applied", "title", "correction"):
                bad = words_outside_quotes(str(row.get(field) or ""), never)
                if bad:
                    fails.append(f"{f}.json {where}.{field}: prints {', '.join(bad)}")
    for s in data["signals"]["signals"]:
        bad = words_outside_quotes(s["title"], never)
        if bad:
            fails.append(f"signal {s['id']} title: prints {', '.join(bad)}")
    rs = roots()
    reg = register_dir(rs)
    if not reg:
        info.append("register checks: skipped (no siglia-fin-concepts beside this skill or in a checkout)")
    else:
        have, n = {}, 0
        for f, where, part in parts_all:
            m = re.match(r"^siglia-fin-concepts (([A-Z]{2})-\d{2})$", part)
            if not m:
                continue
            n += 1
            fp = os.path.join(reg, m.group(2) + ".json")
            if fp not in have:
                have[fp] = {e["id"] for e in json.load(open(fp)).get("entries", [])} if os.path.exists(fp) else set()
            if m.group(1) not in have[fp]:
                fails.append(f"{f}.json {where}: register row {m.group(1)} is not in siglia-fin-concepts")
        info.append(f"register checks: {n} rows")
    rulings = sum(1 for _, _, p in parts_all if p.startswith("Research ruling "))
    if not rs:
        info.append("repo checks: skipped (no checkout with the Research notes)")
    else:
        root, nnote, nrow = rs[0], 0, 0
        research = os.path.join(root, "docs", "research")
        ruled = {}
        for f, where, part in parts_all:
            m = re.match(r"^Research (\d{4}-\d{2}-\d{2}) ([a-z0-9-]+)(?: §(\d+))?$", part)
            if m:
                nnote += 1
                base = os.path.join(research, f"{m.group(1)}-{m.group(2)}")
                fp = next((base + x for x in (".md", ".json") if os.path.exists(base + x)), None)
                if not fp:
                    fails.append(f"{f}.json {where}: Research note {m.group(1)} {m.group(2)} is not in the checkout")
                elif m.group(3) and not re.search(r"(?m)^#+ " + m.group(3) + r"\.", open(fp, encoding="utf-8").read()):
                    fails.append(f"{f}.json {where}: section {m.group(3)} is not in Research note {m.group(2)}")
                continue
            m = re.match(r"^ER-001 ([A-Z]{1,2}\d+) \(ruled (\d{4}-\d{2}-\d{2})\)$", part)
            if m:
                nrow += 1
                day = m.group(2)
                if day not in ruled:
                    fp = os.path.join(research, f"{day}-rubric-rows-ruled.json")
                    ruled[day] = ({r["key"]: r for r in json.load(open(fp))["rows"] if r.get("source") == "ER-001"}
                                  if os.path.exists(fp) else None)
                if ruled[day] is None:
                    fails.append(f"{f}.json {where}: Research's ruled rows of {day} are not in the checkout")
                elif m.group(1) not in ruled[day]:
                    fails.append(f"{f}.json {where}: ER-001 {m.group(1)} is not among Research's ruled rows of {day}")
        for a in data["annex"]["rows"]:
            m = RULED_STATUS.match(a.get("status", ""))
            if not m:
                continue
            day = m.group(1)
            if day not in ruled:
                fp = os.path.join(research, f"{day}-rubric-rows-ruled.json")
                ruled[day] = ({r["key"]: r for r in json.load(open(fp))["rows"] if r.get("source") == "ER-001"}
                              if os.path.exists(fp) else None)
            r = (ruled[day] or {}).get(a["key"])
            if not r:
                fails.append(f"annex {a['key']}: not among Research's ruled rows of {day}")
            elif r.get("cls") != m.group(2):
                fails.append(f"annex {a['key']}: class {m.group(2)}, but Research ruled it {r.get('cls')}")
            elif r.get("correction") and not a.get("correction"):
                fails.append(f"annex {a['key']}: Research's correction is not applied (the row has no correction)")
        info.append(f"repo checks: {nnote} Research notes and {nrow} ruled rubric rows against the checkout")
        ecfr = next((os.path.join(r, "data", "siglia-kb", "ecfr") for r in [os.environ.get("EQ_ECFR_ROOT")] + rs
                     if r and os.path.isdir(os.path.join(r, "data", "siglia-kb", "ecfr"))), None)
        if not ecfr:
            info.append("cfr checks: skipped")
        else:
            secs = sorted({(m.group(1), m.group(2)) for _, _, p in parts_all
                           for m in [re.match(r"^(12|17) CFR (\d+\.\d+(?:-\d+)?)", p)] if m})
            for title, sec in secs:
                fp = os.path.join(ecfr, f"t{title}-p{sec.split('.')[0]}.xml")
                if not os.path.exists(fp) or f'N="{sec}"' not in open(fp, encoding="utf-8", errors="replace").read():
                    fails.append(f"{title} CFR {sec} is not in the cached eCFR")
            info.append(f"cfr checks: {len(secs)} sections in the cached eCFR")
    info.insert(0, f"rows: {rows} factual rows carrying {sources} source references; {rulings} cite a Research ruling "
                   "sent as a message, each beside the note or ruled row of its date that carries it")
    return fails, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eq.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("signals")
    p.add_argument("facts")
    p.add_argument("--json", action="store_true")
    sub.add_parser("explain").add_argument("key")
    sub.add_parser("list")
    sub.add_parser("validate")
    a = ap.parse_args(argv)
    data = load()
    if a.cmd == "explain":
        t = explain(data, a.key)
        if t is None:
            print(f"eq: nothing named {a.key!r}; eq.py list shows every signal, rule and ER-001 row")
            return 1
        print(t)
        return 0
    if a.cmd == "list":
        print(listing(data))
        return 0
    if a.cmd == "validate":
        fails, info = validate(data)
        print("\n".join(info))
        print("\n".join(f"FAIL {x}" for x in fails) if fails else "validate: clean")
        return 1 if fails else 0
    try:
        doc = json.load(open(a.facts))
    except (OSError, ValueError) as e:
        print(f"eq: cannot read {a.facts}: {e}", file=sys.stderr)
        return 2
    try:
        rep = signals(data, doc)
    except InputError as e:
        print(f"eq: bad input: {e}", file=sys.stderr)
        return 2
    text = render(rep)
    bad = words_outside_quotes(text, rule(data, "words")["values"]["never"])
    if bad:
        print(f"eq: refused to print: the text holds {', '.join(bad)} outside a quoted issuer span", file=sys.stderr)
        return 3
    print(json.dumps(rep, indent=1, default=str) if a.json else text)
    return 0 if any(s["status"] == "shown" for s in rep["signals"]) else 1


if __name__ == "__main__":
    sys.exit(main())
