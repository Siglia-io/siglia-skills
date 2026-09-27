#!/usr/bin/env python3
"""period.py — fiscal-period arithmetic: the fiscal label of a period end for any year-end (52/53-week years and the
January naming window included), discrete quarters from 10-Q year-to-date facts, a period label checked against a
fact's dates, a direction word checked against both periods, and a lookback window's first day.

Part of the siglia-period-math skill. Every threshold it uses (the duration bands, the year-long and year-over-year
spans, the 45-day year-end tolerance, the 1 Jan-7 Feb naming window, the extra-week lengths) is a row of
data/periods.json with its source; `validate` holds the rows' shape and recomputes every worked example. Read-only and offline: it reads its own data and the input it is given, and writes
nothing. Python 3.9+, standard library only.

  period.py label --fye MM-DD --end YYYY-MM-DD [--start YYYY-MM-DD] [--offset 0|-1] [--weeks52] [--transition-report]
  period.py quarterize FILE|- [--fye MM-DD] [--offset 0|-1] [--non-additive] [--weeks52] [--tol ABS]
  period.py check-label 'Q3 FY2026' --fye MM-DD --end YYYY-MM-DD [--start YYYY-MM-DD] [--offset 0|-1] [--weeks52]
                        [--transition-report]
  (--transition-report, or "transition_report": true or "form": "10-KT"/"10-QT" on a quarterize fact: the fact comes
   from a transition report. Only then is an unbanded duration shorter than 12 months named a transition period.)
  period.py compare --cur START END VALUE [--prior START END VALUE] [--word WORD] [--weeks52] [--tol ABS]
  period.py window --days N [--today YYYY-MM-DD] DATE [DATE ...]
  period.py validate         the reference's shape, and every worked example recomputed
  period.py show [WORDS]     the reference rows holding every word (none: the count per section)
Exit: 0 labelled · MATCH · every fact placed and every check passed · comparable · inside · valid · found
      1 no fiscal quarter · MISMATCH · a check failed or a fact unplaced · not comparable · outside · invalid ·
        nothing found
      2 unreadable input
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("PERIOD_MATH_DATA") or os.path.join(HERE, "..", "data", "periods.json")
SECTIONS = ("windows", "naming", "derivations", "comparisons", "rules", "forms", "examples", "measured")
REF = json.load(open(DATA))
DAY = dt.timedelta(days=1)


class Bad(ValueError):
    """Unreadable input: exit 2."""


def row(section: str, id_: str) -> dict:
    for r in REF.get(section, []):
        if r["id"] == id_:
            return r
    raise KeyError(f"{section}/{id_} is missing from {DATA}")


def win(id_: str) -> tuple:
    r = row("windows", id_)
    return r["min"], r["max"]


def val(section: str, id_: str):
    return row(section, id_)["value"]


def within(d: int, id_: str) -> bool:
    lo, hi = win(id_)
    return lo <= d <= hi


# ── dates and the fiscal calendar ───────────────────────────────────────────────────────────────────────────────────

def parse_date(s: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        raise Bad(f"not a date (YYYY-MM-DD): {s!r}")


def parse_fye(s: str) -> tuple:
    """'MM-DD', '--MM-DD' (dei:CurrentFiscalYearEndDate) or 'MMDD' -> (month, day)."""
    digits = "".join(ch for ch in str(s or "") if ch.isdigit())
    if len(digits) != 4:
        raise Bad(f"not a fiscal year-end (MM-DD): {s!r}")
    m, d = int(digits[:2]), int(digits[2:])
    try:
        dt.date(2024, m, d)                   # a leap year, so 02-29 is a real year-end
    except ValueError:
        raise Bad(f"not a fiscal year-end (MM-DD): {s!r}")
    return m, d


def fye_in(year: int, cal: tuple) -> dt.date:
    m, d = cal
    return dt.date(year, m, min(d, 28) if m == 2 else d)


def closing_fye(end: dt.date, cal: tuple) -> dt.date:
    """The year-end that closes a period ending `end`: the first year-end on or after `end` less the tolerance, on
    either side of MM-DD, starting from the PREVIOUS calendar year, so a late-December 52/53-week year that ends in
    early January closes on the December before it (naming/late_december_into_january)."""
    tol = dt.timedelta(days=val("windows", "fy_tolerance_days"))
    fye = fye_in(end.year - 1, cal)
    while fye < end - tol:
        fye = fye_in(fye.year + 1, cal)
    return fye


def quarter_of(end: dt.date, cal: tuple):
    back = (closing_fye(end, cal) - end).days
    idx = round(back / val("windows", "quarter_step_days"))
    if idx < 0 or idx > 3:
        return None
    return f"Q{4 - idx}"


def fiscal_year_of(end: dt.date, cal: tuple, offset: int = 0) -> int:
    return closing_fye(end, cal).year + offset


def in_naming_window(cal: tuple) -> bool:
    lo, hi = val("naming", "fy_naming_window")
    return tuple(lo) <= tuple(cal) <= tuple(hi)


def whole_weeks(start: dt.date, end: dt.date):
    """The duration in weeks, counted inclusive (end - start + 1 days), when that is a whole number; else None."""
    n = (end - start).days + 1
    return n // 7 if n % 7 == 0 else None


def classify(start, end: dt.date, weeks52: bool = False) -> str:
    """instant | quarter | annual | ytd | unbanded, by the day bands (windows/*). A year is 52 or 53 weeks
    (windows/annual): a duration outside every band is unbanded, never a fiscal year (naming/unbanded). With
    weeks52, a duration the day bands leave unbanded is a quarter when it is a whole 12-17 weeks, and a
    year-to-date stub when it is a whole 24-29 or 36-41 weeks (windows/weeks52_*)."""
    if start is None:
        return "instant"
    d = (end - start).days
    if within(d, "quarter"):
        return "quarter"
    if within(d, "annual"):
        return "annual"
    if within(d, "ytd_6m") or within(d, "ytd_9m"):
        return "ytd"
    w = whole_weeks(start, end) if weeks52 else None
    if w is not None and within(w, "weeks52_quarter"):
        return "quarter"
    if w is not None and (within(w, "weeks52_ytd_6m") or within(w, "weeks52_ytd_9m")):
        return "ytd"
    return "unbanded"


def twelve_months_or_more(start: dt.date, end: dt.date) -> bool:
    """The duration covers 12 or more months: the day after its end is on or after the start's day one year later
    (a 29 February start counts from 28 February). No transition period is that long (naming/transition_period)."""
    try:
        later = start.replace(year=start.year + 1)
    except ValueError:
        later = start.replace(year=start.year + 1, day=28)
    return end + DAY >= later


def kind_of(start, end: dt.date, weeks52: bool = False, report: bool = False) -> str:
    """classify(), except that an unbanded duration from a transition report (form 10-KT or 10-QT, or
    dei:DocumentTransitionReport true) that covers less than 12 months is a 'transition' period. A banded duration
    keeps its band whatever the report, since a transition report also carries prior years and comparable periods
    (naming/transition_period)."""
    k = classify(start, end, weeks52) if start is not None else "instant"
    if k == "unbanded" and report and not twelve_months_or_more(start, end):
        return "transition"
    return k


def ytd_months(start: dt.date, end: dt.date, weeks52: bool = False) -> int:
    """6 or 9: which year-to-date stub a 'ytd' duration is."""
    w = whole_weeks(start, end)
    six = within((end - start).days, "ytd_6m") or (weeks52 and w is not None and within(w, "weeks52_ytd_6m"))
    return 6 if six else 9


def period_label(start, end: dt.date, cal: tuple, offset: int = 0, weeks52: bool = False,
                 report: bool = False) -> str:
    """The label a context earns: 'Q1 FY2025', 'FY2025', 'YTD to Q3 FY2025', 'unbanded duration s–e (N days)',
    'transition period s–e' (from a transition report only), 'as of d (Q1 FY2025)'."""
    kind = kind_of(start, end, weeks52, report)
    q = quarter_of(end, cal)
    fy = fiscal_year_of(end, cal, offset)
    fiscal = f"{q} FY{fy}" if q else None
    if kind == "instant":
        return f"as of {end.isoformat()}" + (f" ({fiscal})" if fiscal else "")
    span_ = f"{start.isoformat()}–{end.isoformat()}"
    if kind == "quarter":
        return fiscal or f"quarter {span_}"
    if kind == "annual":
        return f"FY{fy}"
    if kind == "ytd":
        return f"YTD to {fiscal}" if fiscal else f"year-to-date {span_}"
    if kind == "transition":
        return f"transition period {span_}"
    return f"unbanded duration {span_} ({(end - start).days} days)"


def calendar_label(end: dt.date) -> str:
    return f"CY{end.year} Q{(end.month - 1) // 3 + 1}"


def check_offset(offset, cal: tuple):
    """The naming offset as given, or None. Only 0 and -1 exist (naming/naming_offset_rule)."""
    if offset is None:
        return None
    if offset not in (0, -1):
        raise Bad(f"--offset is 0 or -1 (naming/naming_offset_rule), not {offset}")
    return offset


def offset_warning(offset, cal: tuple):
    """Words for an --offset -1 outside the naming window, else None. Outside it this tool assumes the end-year rule
    (offset 0); nobody measured that, so an offset the caller took from the issuer's 10-Ks is used, with a warning."""
    if not offset or in_naming_window(cal):
        return None
    lo, hi = val("naming", "fy_naming_window")
    return (f"warning: --offset {offset} on a year-end outside {lo[0]:02d}-{lo[1]:02d}..{hi[0]:02d}-{hi[1]:02d}; "
            "this tool assumes the end-year rule (offset 0) there, an assumption never measured "
            "(naming/end_year_rule), so the offset is used as given: check it against the issuer's 10-K "
            "DocumentFiscalYearFocus")


def year_note(cal: tuple, rule_year: int) -> str:
    return (f"year unsettled: a year-end between 01-01 and 02-07 is named two ways (naming/fy_naming_window). "
            f"FY{rule_year} by the end-year rule (Nvidia); FY{rule_year - 1} by the calendar year it mostly covers "
            "(Kelly, Target, Home Depot, Lowe's). Settle it with --offset 0 or -1 from the issuer's recent 10-K "
            "DocumentFiscalYearFocus (naming/naming_offset_rule); unsettled, print the quarter alone "
            "(naming/quarter_only)")


KIND_WORD = {"quarter": "quarter", "annual": "year", "ytd": "year-to-date stub", "transition": "transition period",
             "unbanded": "unbanded duration"}


def a_(word: str) -> str:
    return ("an " if word[:1] in "aeiou" else "a ") + word


def weeks_alt(start, end: dt.date, cal: tuple, offset: int):
    """(label, words) when the day bands leave a duration unbanded and, as whole weeks, it is a 52/53-week year's
    quarter or year-to-date stub; else None. Only --weeks52 can say the filer keeps such a year."""
    if start is None or classify(start, end) != "unbanded" or classify(start, end, True) == "unbanded":
        return None
    lab = period_label(start, end, cal, offset, weeks52=True)
    return lab, (f"{(end - start).days} days is {whole_weeks(start, end)} whole weeks: if the filer keeps a 52/53-week "
                 f"year it is {lab}, which the day bands miss (windows/weeks52_*); pass --weeks52")


SX_3_06 = ("a 9-12 month period satisfies a one-year filing requirement only where 17 CFR 210.3-06(a) says so: the "
           "issuer changed its fiscal year; statements are required for a significant business acquisition (3-05, "
           "3-14, 8-04, 8-06) and the 9-12 month statements pertain to the business being acquired; or the Commission "
           "permits it (3-13, 8-01(e)). Registered investment companies are excepted. That is a filing rule, not a "
           "label: this tool never names such a period FYyyyy")


def stub_note(start, end: dt.date):
    """Words for a year-long unbanded duration (windows/year_long): not a fiscal year, never FYyyyy."""
    d = (end - start).days
    lo, hi = win("annual")
    if classify(start, end) != "unbanded" or not within(d, "year_long"):
        return None
    return (f"{d} days is {'shorter' if d < lo else 'longer'} than a 52- or 53-week year ({lo}-{hi} days, "
            "windows/annual): not a fiscal year, never FYyyyy" + ("; " + SX_3_06 if d < lo else ""))


def unbanded_note(start, end: dt.date, report: bool) -> str:
    """What an unbanded duration is, with and without the transition-report signal (naming/unbanded,
    naming/transition_period)."""
    if twelve_months_or_more(start, end) and report:
        return ("from a transition report, but 12 months or more: never a transition period, whatever the report "
                "says (a transition report never covers 12 or more months, 17 CFR 240.13a-10(a)); an unbanded "
                "duration, never differenced or summed (derivations/unbanded_never_differenced)")
    if twelve_months_or_more(start, end):
        return ("outside every band and 12 months or more: by its dates it may be a first period from inception or a "
                "predecessor or successor period, never a transition period (none covers 12 or more months); never "
                "differenced or summed (derivations/unbanded_never_differenced)")
    if report:
        return ("from a transition report: the transition period that results when an issuer changes its fiscal "
                "closing date (17 CFR 240.13a-10(a)); never differenced or summed into a TTM "
                "(derivations/unbanded_never_differenced)")
    return ("outside every band, with no transition-report signal: by its dates it may be a first period from "
            "inception, a predecessor or successor period, or a transition period (which can sit in an ordinary 10-K "
            "or 10-Q, 17 CFR 240.13a-10(d)); never differenced or summed (derivations/unbanded_never_differenced). "
            "Pass --transition-report for a fact from a 10-KT or 10-QT, or with dei:DocumentTransitionReport true")


# ── label ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def cmd_label(a) -> int:
    cal, end = parse_fye(a.fye), parse_date(a.end)
    start = parse_date(a.start) if a.start else None
    if start and start > end:
        raise Bad("--start is after --end")
    offset = check_offset(a.offset, cal)
    off = offset or 0
    unsettled = in_naming_window(cal) and offset is None
    fye = closing_fye(end, cal)
    q = quarter_of(end, cal)
    rule_year = fiscal_year_of(end, cal)
    kind = kind_of(start, end, a.weeks52, a.transition_report) if start else None
    twelve = kind == "annual" and q not in (None, "Q4")
    if twelve:
        lab = f"twelve months to {q} FY{fiscal_year_of(end, cal, off)}"
    elif start:
        lab = period_label(start, end, cal, off, a.weeks52, a.transition_report)
    else:
        lab = f"{q} FY{fiscal_year_of(end, cal, off)}" if q else None
    if lab is None:
        print(f"no fiscal quarter: {end} is {(fye - end).days} days before the year-end {fye}, not near a quarter end "
              f"(round(days / {val('windows', 'quarter_step_days')}) must be 0-3)")
        return 1
    if unsettled:
        lab = re.sub(r"FY\d{4}", "FY?", lab)
    print(lab)
    gap = (fye - end).days
    print(f"  closes the fiscal year ending {fye} (" + (f"{gap} days after this end" if gap >= 0 else
                                                          f"{-gap} days before this end, inside the tolerance")
          + f"; year-end {a.fye}" + (f", named with offset {offset}" if offset else "") + ")")
    warn = offset_warning(offset, cal)
    if warn:
        print("  " + warn)
    if unsettled:
        print("  " + year_note(cal, rule_year))
    alt = None
    if start:
        d = (end - start).days
        print(f"  duration: {d} days (end - start): {kind}")
        alt = None if a.weeks52 else weeks_alt(start, end, cal, off)
        if alt:
            print("  " + (re.sub(r"FY\d{4}", "FY?", alt[1]) if unsettled else alt[1]))
        stub = stub_note(start, end)
        if stub:
            print("  " + stub)
        if kind in ("unbanded", "transition"):
            print("  " + unbanded_note(start, end, a.transition_report))
        elif a.transition_report:
            print(f"  --transition-report names only an unbanded duration: this {KIND_WORD[kind]} keeps its band (a "
                  "transition report also carries prior years and comparable periods; naming/transition_period)")
        if twelve:
            print(f"  a year-long duration ending at {q}, not at the year-end: the cumulative twelve months a 10-Q may "
                  "present (17 CFR 210.10-01(c)(2)-(3)), not a fiscal year")
        if kind == "annual" and not twelve and d >= val("windows", "fifty_three_weeks"):
            print(f"  a 53-week fiscal year ({d} days, as its dates state; windows/fifty_three_weeks)")
        if a.weeks52:
            inclusive = d + 1
            if inclusive % 7:
                print(f"  not a whole number of weeks ({inclusive} days counted inclusive)")
            else:
                w = inclusive // 7
                print(f"  {w} weeks ({inclusive} days counted inclusive)"
                      + ("; the extra week adds about 1/52 (~1.9%) to the year's flows (QF-31)" if w == 53 else "")
                      + ("; the extra week adds about 1/13 (~7.7%) over a 13-week quarter (QF-31)" if w == 14 else "")
                      + ("; the extra week adds about 1/16 over a 16-week quarter (QF-31)" if w == 17 else ""))
        if kind == "ytd":
            print("  a year-to-date stub, not a quarter: difference it (quarterize); 10-Q cash flows are required year "
                  "to date, with no quarter-only statement (17 CFR 210.10-01(c)(3); 210.8-03)")
    if a.weeks52:
        print(f"  52/53-week: the end is a {end.strftime('%A')}; the year ends on the same weekday every year, the last one "
              "of a month or the one nearest month-end, never more than three days past it (26 CFR 1.441-2(a), a tax "
              f"rule read here by analogy; QF-31), so ends drift around {a.fye}; this tool closes a period "
              f"on the first year-end on or after its end less {val('windows', 'fy_tolerance_days')} days, either side of "
              f"{a.fye} (naming/late_december_into_january)")
    elif (end + DAY).day != 1 and not alt:
        print("  the end is not a month end: if the filer keeps a 52/53-week year, pass --weeks52")
    return 0


# ── quarterize ────────────────────────────────────────────────────────────────────────────────────────────────────

def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.10g}"


def span(f: dict) -> str:
    return f"{f['start']}..{f['end']}"


def name(f: dict, weeks52: bool = False) -> str:
    d = (f["end"] - f["start"]).days
    k = classify(f["start"], f["end"], weeks52)
    if k == "quarter":
        return "3M" if within(d, "quarter") else f"{whole_weeks(f['start'], f['end'])}-week quarter"
    if k == "annual":
        return "FY"
    if k == "ytd":
        return f"{ytd_months(f['start'], f['end'], weeks52)}M YTD"
    return f"{d}-day"


def quarter_gap(days: int, weeks52: bool = False) -> bool:
    """Two ends this far apart difference into a quarter: the quarter band, or with weeks52 a whole 12-17 weeks (the
    derived quarter runs from the shorter end + 1 day, so its inclusive length is the gap)."""
    return within(days, "quarter") or (weeks52 and days % 7 == 0 and within(days // 7, "weeks52_quarter"))


def near(x: float, y: float, tol: float) -> bool:
    """|x - y| <= tol + 1e-9 * max(1, |x|, |y|): slack relative to the values (windows/float_slack)."""
    return abs(x - y) <= tol + val("windows", "float_slack") * max(1.0, abs(x), abs(y))


#: the EDGAR form types of a transition report (naming/transition_period)
TRANSITION_FORMS = ("10-KT", "10-KT/A", "10-QT", "10-QT/A")


def read_facts(path: str) -> list:
    try:
        raw = json.load(sys.stdin if path == "-" else open(path))
    except (OSError, ValueError) as e:
        raise Bad(f"cannot read {path}: {e}")
    if isinstance(raw, dict):
        raw = raw.get("facts")
    if not isinstance(raw, list) or not raw:
        raise Bad("the input is a JSON list of {start, end, value}")
    out = []
    for i, f in enumerate(raw):
        if not isinstance(f, dict) or "end" not in f or "value" not in f:
            raise Bad(f"fact {i + 1}: needs end and value (and start, for a duration)")
        v = f["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise Bad(f"fact {i + 1}: value is not a number: {v!r}")
        start = parse_date(f["start"]) if f.get("start") else None
        end = parse_date(f["end"])
        if start and start > end:
            raise Bad(f"fact {i + 1}: start after end")
        report = f.get("transition_report") is True or str(f.get("form") or "").strip().upper() in TRANSITION_FORMS
        out.append({"n": i, "start": start, "end": end, "value": float(v), "id": f.get("id") or f"#{i + 1}",
                    "report": report})
    return out


def quarterize(facts: list, additive: bool = True, tol: float = 0.0, weeks52: bool = False) -> dict:
    """Discrete quarters from quarters, year-to-date stubs and years, each with its inputs; plus the checks: a reported
    quarter against its derivation, four reported quarters against the year, and every fact placed or named. Only a
    quarter, a year-to-date stub or a year is differenced: an unbanded duration, a transition period included, never
    is (derivations/unbanded_never_differenced)."""
    def kind(f):
        return kind_of(f["start"], f["end"], weeks52, f.get("report", False))
    durations = [f for f in facts if f["start"] is not None]
    by_end = {}
    for f in sorted((f for f in durations if kind(f) == "quarter"), key=lambda f: f["end"]):
        by_end[f["end"]] = dict(f, derived=False, formula="reported", inputs=[f])
    checks, used = [], set()
    if additive:
        chain = [f for f in durations if kind(f) not in ("unbanded", "transition")]
        by_start: dict = {}
        for f in chain:
            by_start.setdefault(f["start"], []).append(f)
        for start, group in by_start.items():
            group = sorted({f["end"]: f for f in group}.values(), key=lambda f: f["end"])
            for a, b in zip(group, group[1:]):
                if not quarter_gap((b["end"] - a["end"]).days, weeks52):
                    continue
                value = b["value"] - a["value"]
                formula = (f"{name(b, weeks52)} {fmt(b['value'])} ({span(b)}) - {name(a, weeks52)} {fmt(a['value'])} "
                           f"({span(a)})")
                have = by_end.get(b["end"])
                if have is not None:
                    if not have["derived"] and have["start"] == a["end"] + DAY:
                        ok = near(have["value"], value, tol)
                        used.update((a["n"], b["n"]))
                        checks.append((ok, f"{'agree' if ok else 'DISAGREE'}: reported {fmt(have['value'])} for "
                                           f"{span(have)}; {formula} = {fmt(value)}"))
                    continue
                by_end[b["end"]] = {"n": None, "start": a["end"] + DAY, "end": b["end"], "value": value, "derived": True,
                                    "formula": formula, "inputs": [b, a],
                                    "ordinal": {"6M YTD": "Q2", "9M YTD": "Q3", "FY": "Q4"}.get(name(b, weeks52))}
        for fy in (f for f in durations if kind(f) == "annual"):
            inside = sorted((q for q in by_end.values() if fy["start"] <= q["start"] and q["end"] < fy["end"]),
                            key=lambda q: q["end"])
            have = by_end.get(fy["end"])
            if have is not None:
                if not have["derived"] and len(inside) == 3:
                    total = sum(q["value"] for q in inside) + have["value"]
                    ok = near(total, fy["value"], tol)
                    used.add(fy["n"])
                    checks.append((ok, f"{'agree' if ok else 'DISAGREE'}: four reported quarters sum to {fmt(total)}; "
                                       f"FY {fmt(fy['value'])} ({span(fy)})"))
                continue
            if len(inside) != 3:
                continue
            by_end[fy["end"]] = {"n": None, "start": inside[-1]["end"] + DAY, "end": fy["end"],
                                 "value": fy["value"] - sum(q["value"] for q in inside), "derived": True,
                                 "formula": f"FY {fmt(fy['value'])} ({span(fy)}) - (Q1 + Q2 + Q3: "
                                            + " + ".join(fmt(q["value"]) for q in inside) + ")",
                                 "inputs": [fy] + inside, "ordinal": "Q4"}
    series = sorted(by_end.values(), key=lambda q: q["end"])
    for q in series:
        used.update(i["n"] for i in q["inputs"] if i.get("n") is not None)
    placed = {q["end"] for q in series}
    excluded = []
    for f in facts:
        if f["start"] is None:
            excluded.append((f, "an instant (no start date): not a duration; never summed or differenced"))
            continue
        k = kind(f)
        if f["n"] in used or (k == "annual" and f["end"] in placed):
            continue
        if k == "quarter":
            reason = "another reported quarter ends on the same date; the later one is kept"
        elif k == "ytd" and not additive:
            reason = "year-to-date stub of a non-additive metric; never differenced"
        elif k in ("unbanded", "transition"):
            reason = (("transition period (an unbanded duration from a transition report)" if k == "transition" else
                       "unbanded duration (neither a quarter, a year-to-date stub nor a 52/53-week year)")
                      + ": never differenced, excluded from TTM")
            stub = stub_note(f["start"], f["end"])
            if stub:
                reason += "; " + stub.split(": ")[0]
            if f.get("report") and k == "unbanded" and twelve_months_or_more(f["start"], f["end"]):
                reason += ("; from a transition report, but 12 months or more, so never a transition period (17 CFR "
                           "240.13a-10(a))")
            if not weeks52 and classify(f["start"], f["end"], True) != "unbanded":
                reason += (f"; {(f['end'] - f['start']).days} days is {whole_weeks(f['start'], f['end'])} whole weeks, a "
                           f"52/53-week year's {KIND_WORD[classify(f['start'], f['end'], True)]}: pass --weeks52")
            mates = [g for g in durations if g is not f and g["start"] == f["start"] and
                     quarter_gap(abs((g["end"] - f["end"]).days))]
            if additive and mates:
                reason += (f"; it shares its start with {mates[0]['id']} ({span(mates[0])}), ends "
                           f"{abs((mates[0]['end'] - f['end']).days)} days apart, and is still never differenced "
                           "against it (derivations/unbanded_never_differenced)")
        else:
            reason = {"annual": "annual duration without three quarters inside it",
                      "ytd": "year-to-date stub with no shorter stub to difference against"}[k]
        excluded.append((f, reason))
    return {"series": series, "checks": checks, "excluded": excluded}


def ttm_of(series: list):
    """(value, last four) when the last four quarters make a trailing year, else (None, why)."""
    if len(series) < 4:
        return None, f"need 4 quarters, have {len(series)}"
    last4 = series[-4:]
    for a, b in zip(last4, last4[1:]):
        if not within((b["start"] - a["end"]).days, "ttm_gap"):
            return None, f"quarters not contiguous around {a['end']}"
    s = (last4[-1]["end"] - last4[0]["start"]).days
    if not within(s, "ttm_span"):
        return None, f"the last four quarters span {s} days; not a trailing year"
    return sum(q["value"] for q in last4), last4


def cmd_quarterize(a) -> int:
    facts = read_facts(a.file)
    cal = parse_fye(a.fye) if a.fye else None
    if a.offset is not None and not cal:
        raise Bad("--offset needs --fye")
    offset = check_offset(a.offset, cal) if cal else None
    warn = offset_warning(offset, cal) if cal else None
    if warn:
        print(warn)
    got = quarterize(facts, additive=not a.non_additive, tol=a.tol, weeks52=a.weeks52)
    series, fails = got["series"], 0
    print("quarters, oldest first (days = end - start):")
    for q in series:
        d = (q["end"] - q["start"]).days
        if cal:
            lab = period_label(q["start"], q["end"], cal, offset or 0, a.weeks52) \
                if classify(q["start"], q["end"], a.weeks52) == "quarter" \
                else f"{quarter_of(q['end'], cal) or '-'} FY{fiscal_year_of(q['end'], cal, offset or 0)}"
            if in_naming_window(cal) and offset is None:
                lab = re.sub(r"FY\d{4}", "FY?", lab)
        else:
            lab = q.get("ordinal") or ("3M" if not q["derived"] else "-")
        how = ("derived: " + q["formula"]) if q["derived"] else "reported"
        print(f"  {lab:<10} {span(q)}  {d:>3} d  {fmt(q['value']):>14}  {how}")
    print("checks:")
    for ok, text in got["checks"]:
        print(f"  {'ok  ' if ok else 'FAIL'} {text}")
        fails += 0 if ok else 1
    lo, hi = win("quarter")
    weekly = [q for q in series if a.weeks52 and not within((q["end"] - q["start"]).days, "quarter")
              and within(whole_weeks(q["start"], q["end"]) or 0, "weeks52_quarter")]
    bad = [q for q in series if not within((q["end"] - q["start"]).days, "quarter") and q not in weekly]
    for q in bad:
        print(f"  FAIL {span(q)} is {(q['end'] - q['start']).days} days: not a quarter ({lo}-{hi} days, windows/quarter)")
    for q in weekly:
        print(f"  ok   {span(q)} is {whole_weeks(q['start'], q['end'])} whole weeks ({(q['end'] - q['start']).days} days): "
              f"a 52/53-week quarter (--weeks52, windows/weeks52_quarter), outside the {lo}-{hi} day band")
    fails += len(bad)
    if series and not bad:
        print(f"  ok   every quarter is a quarterly duration ({lo}-{hi} days, windows/quarter)"
              + (" or a whole-week 52/53-week quarter" if weekly else ""))
    for x, y in zip(series, series[1:]):
        gap = (y["start"] - x["end"]).days
        if gap != 1:
            print(f"  note {gap - 1} days uncovered between {x['end']} and {y['start']}" if gap > 1
                  else f"  note {span(x)} and {span(y)} overlap")
    if got["excluded"]:
        print("unplaced:")
        for f, why in got["excluded"]:
            print(f"  FAIL {f['id']} {f['start'] or '-'}..{f['end']} {fmt(f['value'])}: {why}")
        fails += len(got["excluded"])
    if a.non_additive:
        print("TTM: not formed (non-additive: never summed)")
    else:
        v, last4 = ttm_of(series)
        print(f"TTM to {last4[-1]['end']}: {fmt(v)} = the sum of the last four quarters ({last4[0]['start']}..{last4[-1]['end']})"
              if v is not None else f"TTM: not formed ({last4})")
    nd = sum(1 for q in series if q["derived"])
    print(f"quarterize: {len(series)} quarters ({len(series) - nd} reported, {nd} derived); {fails} failed")
    return 1 if fails or not series else 0


# ── check-label ───────────────────────────────────────────────────────────────────────────────────────────────────

_Y4 = r"(?:19|20)\d\d"
#: the claim-label grammar: a quarter with a year, in the forms filers and analysts write (forms/claim_quarter_forms)
QUARTER_RX = re.compile(rf"""
    (?<![A-Za-z0-9])(?P<cal>calendar\s+(?:year\s+)?)?
    (?:
        (?:fiscal\s+)?Q(?P<a_q>\d)(?!\d)[\s-]*(?:of\s+)?
            (?:(?:fiscal\s+(?:year\s+)?|FY\s?)(?P<a_fy>{_Y4}|\d\d)|(?P<a_y>{_Y4})|['’](?P<a_yy>\d\d))(?!\d)
      | (?:FY\s?|fiscal\s+(?:year\s+)?)?(?P<b_y>{_Y4})[\s-]?Q(?P<b_q>\d)(?!\d)
      | FY\s?(?P<c_y>\d\d)[\s-]?Q(?P<c_q>\d)(?!\d)
      | (?P<d_q>\d)Q\s?['’]?(?P<d_y>{_Y4}|\d\d)(?!\d)
      | (?P<e_o>first|second|third|fourth)[\s-]quarter\s+(?:of\s+)?
            (?:(?:fiscal\s+(?:year\s+)?|FY\s?)(?P<e_fy>{_Y4}|\d\d)|(?P<e_y>{_Y4}))(?!\d)
      | fiscal\s+(?:year\s+)?(?P<f_y>{_Y4})\s+(?P<f_o>first|second|third|fourth)[\s-]quarter
    )""", re.I | re.X)
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
YTD_RX = re.compile(r"^(?:YTD|year[-\s]to[-\s]date)\s+to\s+Q([1-4])\s+FY\s?(\d{4})$", re.I)
QONLY_RX = re.compile(r"^(?:fiscal\s+)?Q([1-4])$", re.I)
ANNUAL_RX = re.compile(rf"^(?:(?P<cy>CY|calendar(?:\s+year)?)|FY|fiscal(?:\s+year)?)?\s*'?\s*(?P<y>{_Y4})$"
                       r"|^(?:(?P<cy2>CY)|FY)\s*'?(?P<yy>\d\d)$", re.I)


def two_digit(s: str) -> int:
    n = int(s)
    return n if len(s) == 4 else (1900 + n if n >= val("forms", "yy_pivot") else 2000 + n)


def parse_label(text: str) -> dict:
    """{kind: quarter|annual|ytd, q, year (None: the quarter alone), calendar}."""
    t = " ".join(str(text or "").split())
    m = YTD_RX.match(t)
    if m:
        return {"kind": "ytd", "q": int(m.group(1)), "year": int(m.group(2)), "calendar": False}
    m = QONLY_RX.match(t)
    if m:
        return {"kind": "quarter", "q": int(m.group(1)), "year": None, "calendar": False}
    hits = list(QUARTER_RX.finditer(t))
    if len(hits) > 1:
        raise Bad(f"{text!r} names {len(hits)} quarter labels; check one at a time")
    if hits:
        g = hits[0].groupdict()
        if g["a_q"]:
            q, y = int(g["a_q"]), g["a_fy"] or g["a_y"] or g["a_yy"]
        elif g["b_q"]:
            q, y = int(g["b_q"]), g["b_y"]
        elif g["c_q"]:
            q, y = int(g["c_q"]), g["c_y"]
        elif g["d_q"]:
            q, y = int(g["d_q"]), g["d_y"]
        elif g["e_o"]:
            q, y = ORDINAL[g["e_o"].lower()], g["e_fy"] or g["e_y"]
        else:
            q, y = ORDINAL[g["f_o"].lower()], g["f_y"]
        return {"kind": "quarter", "q": q, "year": two_digit(y), "calendar": bool(g["cal"])}
    m = ANNUAL_RX.match(t)
    if m:
        return {"kind": "annual", "q": None, "year": two_digit(m.group("y") or m.group("yy")),
                "calendar": bool(m.group("cy") or m.group("cy2"))}
    raise Bad(f"not a period label this skill reads: {text!r} (a quarter with a year, 'Q3', 'FY2025' or 'YTD to Q3 FY2025')")


def kind_words(kind: str, start, end: dt.date) -> str:
    w = {"quarter": "a quarter", "annual": "a year-long duration", "ytd": "a year-to-date stub",
         "transition": "a transition period", "unbanded": "an unbanded duration"}[kind]
    return f"{w} ({(end - start).days} days)"


def cmd_check_label(a) -> int:
    lab = parse_label(a.label)
    cal, end = parse_fye(a.fye), parse_date(a.end)
    start = parse_date(a.start) if a.start else None
    if start and start > end:
        raise Bad("--start is after --end")
    offset = check_offset(a.offset, cal)
    off = offset or 0
    unsettled = in_naming_window(cal) and offset is None
    kind = kind_of(start, end, a.weeks52, a.transition_report) if start else None
    q_true = quarter_of(end, cal)
    fy_rule = fiscal_year_of(end, cal)
    fy_true = fy_rule + off
    years = {fy_rule, fy_rule - 1} if unsettled else {fy_true}
    twelve = kind == "annual" and q_true not in (None, "Q4")
    if twelve:
        right = f"twelve months to {q_true} FY{fy_true} (not a fiscal year)"
    else:
        right = (period_label(start, end, cal, off, a.weeks52, a.transition_report) if start else
                 (f"{q_true} FY{fy_true}" if q_true else None))
    alt = None if a.weeks52 else weeks_alt(start, end, cal, off)
    if right and unsettled:
        right = re.sub(r"FY\d{4}", f"FY{fy_rule} or FY{fy_rule - 1}", right)
    said = a.label.strip()
    why, quarter_only = None, False
    if lab["calendar"]:
        right_cal = calendar_label(end)
        if kind and kind != "quarter":
            why = f"a calendar quarter label on {kind_words(kind, start, end)}"
        elif lab["kind"] == "quarter" and (lab["q"], lab["year"]) != ((end.month - 1) // 3 + 1, end.year):
            why = f"the calendar quarter of {end} is {right_cal}"
        elif lab["kind"] == "annual" and lab["year"] != end.year:
            why = f"the calendar year of {end} is CY{end.year}"
        if why is None:
            print(f"MATCH  {said!r} is the calendar period of {end} ({right_cal}); a calendar label is not a fiscal one "
                  f"(fiscal: {right})")
            return 0
        print(f"MISMATCH  {said!r}: {why}")
        print(f"  right label: {right_cal} (calendar) / {right} (fiscal)")
        return 1
    if lab["q"] is not None and not 1 <= lab["q"] <= 4:
        why = f"Q{lab['q']} is not a quarter"
    elif lab["kind"] == "ytd":
        if kind and kind != "ytd":
            why = f"the fact is {kind_words(kind, start, end)}, not a year-to-date stub"
        elif lab["q"] != (int(q_true[1]) if q_true else None) or lab["year"] not in years:
            why = f"the stub ends at {end}, which closes {q_true} FY{fy_true if not unsettled else '?'}"
    elif lab["kind"] == "annual":
        if kind and kind != "annual":
            why = (f"the fact is {kind_words(kind, start, end)}, not a fiscal year"
                   + ("; a 10-Q's quarter or year-to-date is never the year" if kind in ("quarter", "ytd") else "")
                   + ("; " + stub_note(start, end) if kind in ("unbanded", "transition") and stub_note(start, end)
                      else ""))
        elif twelve:
            why = (f"a year-long duration ending at {q_true}, not at the year-end ({closing_fye(end, cal)}): the cumulative "
                   "twelve months a 10-Q may present (17 CFR 210.10-01(c)(2)-(3)), not a fiscal year")
        elif q_true != "Q4":
            why = f"{end} does not close a fiscal year ({q_true or 'no quarter'}; the year ends {closing_fye(end, cal)})"
        elif lab["year"] not in years:
            why = f"the year ending {closing_fye(end, cal)} is FY{fy_true}" if not unsettled else \
                f"the year ending {closing_fye(end, cal)} is FY{fy_rule} or FY{fy_rule - 1}, not FY{lab['year']}"
    else:
        if kind == "ytd":
            d = (end - start).days
            why = (f"the fact is a {'six' if ytd_months(start, end, a.weeks52) == 6 else 'nine'}-month year-to-date stub "
                   f"({d} days), not the quarter: a 10-Q gives the quarter and the year to date side by side "
                   "(17 CFR 210.10-01(c)(2)) and cash flows for the year to date, with no quarter-only statement "
                   "((c)(3); 210.8-03); difference it (quarterize)")
        elif kind and kind != "quarter":
            why = f"the fact is {kind_words(kind, start, end)}, not a quarter" + \
                  ("; the cumulative twelve months a 10-Q may present, not a fiscal year" if twelve else
                   "; Q4 is derived: FY - 9M YTD" if kind == "annual" else "")
        elif q_true is None:
            why = f"{end} closes no fiscal quarter of a year ending {a.fye}"
        elif lab["q"] != int(q_true[1]):
            why = f"{end} closes {q_true} of the fiscal year ending {closing_fye(end, cal)}, not Q{lab['q']}"
        elif lab["year"] is None:
            quarter_only = True
        elif lab["year"] not in years:
            why = (f"the quarter is right and the year is not: FY{fy_true}" if not unsettled else
                   f"the quarter is right and the year is neither FY{fy_rule} (end-year rule) nor FY{fy_rule - 1}")
            if not unsettled and in_naming_window(cal) and lab["year"] in (fy_rule, fy_rule - 1):
                why += f" (offset {offset} names it FY{fy_true}; naming/fy_naming_window)"
        elif unsettled:
            quarter_only = True
    warn = offset_warning(offset, cal)
    if why:
        if alt:
            why += "; but " + alt[1]
        print(f"MISMATCH  {said!r}: {why}")
        print(f"  right label: {right or 'none (no fiscal quarter ends here)'}"
              + (f" by the day bands; {alt[0]} if the filer keeps a 52/53-week year (re-run with --weeks52)"
                 if alt else ""))
        if unsettled:
            print("  " + year_note(cal, fy_rule))
        if warn:
            print("  " + warn)
        return 1
    if quarter_only:
        print(f"MATCH (quarter only)  {said!r}: {end} closes {q_true}"
              + (f"; {year_note(cal, fy_rule)}" if unsettled else "; no year given"))
    else:
        print(f"MATCH  {said!r} = {right} (the period ending {end}; year-end {a.fye}"
              + (f", offset {offset}" if offset else "") + ")")
    if warn:
        print("  " + warn)
    return 0


# ── compare: a direction word needs both periods ─────────────────────────────────────────────────────────────────

WORDS = {
    "up": ("increased", "increase", "increases", "rose", "rise", "rises", "grew", "grow", "grows", "higher", "up"),
    "down": ("decreased", "decrease", "decreases", "fell", "fall", "falls", "declined", "decline", "declines",
             "lower", "down", "dropped", "drop"),
    "narrowed": ("narrowed", "narrow", "narrows", "narrowing"),
    "widened": ("widened", "widen", "widens", "widening"),
    "unchanged": ("unchanged", "flat"),
    "turned": ("turned", "swung", "reversed"),
    "judgement": ("improved", "improve", "improves", "worsened", "worsen", "worsens", "deteriorated", "deteriorate"),
}
RIGHT = {"up": "increased", "down": "decreased", "narrowed": "narrowed", "widened": "widened", "unchanged": "unchanged"}


def word_class(w: str) -> str:
    t = w.strip().lower()
    for k, ws in WORDS.items():
        if t in ws:
            return k
    raise Bad(f"not a direction word this skill reads: {w!r} ({', '.join(RIGHT.values())}, turned, or a synonym)")


def leg(parts, what: str) -> dict:
    if parts is None:
        return None
    s, e, v = parts
    start = None if s in ("-", "") else parse_date(s)
    end = parse_date(e)
    if start and start > end:
        raise Bad(f"{what}: start after end")
    try:
        value = float(v)
    except ValueError:
        raise Bad(f"{what}: not a number: {v!r}")
    return {"start": start, "end": end, "value": value}


def direction(cur: float, prior: float, tol: float) -> tuple:
    """(class, phrase) of the change from prior to cur (comparisons/*)."""
    if near(cur, prior, tol):
        return "unchanged", "unchanged"
    if cur < 0 and prior < 0:
        return ("narrowed", "the loss narrowed") if abs(cur) < abs(prior) else ("widened", "the loss widened")
    if prior < 0 and cur == 0:
        return "narrowed", "the loss narrowed to zero (break-even)"
    if prior < 0 < cur:
        return "turned", "turned from a loss to a profit"
    if cur < 0 <= prior:
        return "turned", "turned to a loss"
    return ("up", "increased") if cur > prior else ("down", "decreased")


def cmd_compare(a) -> int:
    cur, prior = leg(a.cur, "--cur"), leg(a.prior, "--prior")
    if prior is None:
        print("could not establish: a direction word needs both periods; load the prior period's fact of the same "
              "concept and pass --prior (comparisons/both_periods)")
        return 1
    k_cur, k_prior = (classify(x["start"], x["end"], a.weeks52) for x in (cur, prior))
    lab = {"instant": "a balance", **{k: a_(v) for k, v in KIND_WORD.items()}}
    if prior["end"] == cur["end"] and prior["start"] != cur["start"]:
        print(f"{fmt(prior['value'])} ({prior['start'] or 'as of'}..{prior['end']}) and {fmt(cur['value'])} "
              f"({cur['start'] or 'as of'}..{cur['end']}): no direction")
        print(f"  FAIL not like for like: {lab[k_prior]} and {lab[k_cur]} sharing the end {cur['end']}: two periods "
              "that end on one date are never compared, as a year or a year-to-date stub with the quarter that shares "
              "its end (comparisons/like_for_like)")
        return 1
    if prior["end"] >= cur["end"]:
        raise Bad("--prior must end before --cur")
    problems, notes = [], []
    if k_cur != k_prior:
        problems.append(f"not like for like: {lab[k_cur]} against {lab[k_prior]} (comparisons/like_for_like)")
    elif k_cur == "ytd" and ytd_months(cur["start"], cur["end"], a.weeks52) != ytd_months(prior["start"], prior["end"], a.weeks52):
        problems.append("not like for like: a six-month stub against a nine-month one (comparisons/like_for_like)")
    elif k_cur == "unbanded":
        problems.append("an unbanded duration (a transition period included) is compared with nothing "
                        "(comparisons/like_for_like)")
    if cur["start"] is not None and cur["start"] <= prior["end"]:
        problems.append(f"the periods overlap ({prior['end']} is on or after {cur['start']})")
    gap = (cur["end"] - prior["end"]).days
    if not problems:
        if within(gap, "yoy_gap"):
            notes.append(f"year over year: the ends are {gap} days apart (windows/yoy_gap)")
        elif k_cur == "quarter" and within(gap, "quarter"):
            notes.append(f"sequential: the ends are {gap} days apart (seasonal effects stay in; QF-28)")
        else:
            notes.append(f"the ends are {gap} days apart: neither a year-over-year nor a sequential comparison")
        for x, nm in ((cur, "--cur"), (prior, "--prior")):
            if x["start"] is None:
                continue
            w = whole_weeks(x["start"], x["end"])
            if w in val("comparisons", "extra_week"):
                notes.append(f"{nm} is {w} whole weeks: say so beside the change (comparisons/extra_week, QF-31)")
    cls, phrase = direction(cur["value"], prior["value"], a.tol)
    change = cur["value"] - prior["value"]
    pct = (f"{change / prior['value'] * 100:+.1f}%" if prior["value"] > 0 else
           "no percent change on a negative or zero base (comparisons/negative_base)")
    print(f"{fmt(prior['value'])} ({prior['start'] or 'as of'}..{prior['end']}) -> {fmt(cur['value'])} "
          f"({cur['start'] or 'as of'}..{cur['end']}): {phrase}; change {fmt(change)}, {pct}")
    for n in notes:
        print("  " + n)
    for p in problems:
        print("  FAIL " + p)
    if problems:
        return 1
    if not a.word:
        return 0
    said = word_class(a.word)
    if said == cls:
        print(f"MATCH  {a.word!r}")
        return 0
    if said == "judgement":
        why = ("a loss is 'narrowed' or 'widened', never 'improved' or 'worsened' (comparisons/loss_words)"
               if cls in ("narrowed", "widened") else
               "a judgement, not a direction: state the direction (comparisons/judgement_words)")
    elif cls == "narrowed" and cur["value"] == 0:
        why = ("a loss that reaches zero is break-even, not a profit: the loss 'narrowed' to zero "
               "(comparisons/loss_words, comparisons/sign_change)")
    elif cls in ("narrowed", "widened"):
        why = "both periods are losses: a loss 'narrowed' or 'widened' (comparisons/loss_words)"
    elif cls == "turned":
        why = "the sign changed: name the turn, never a plain rise or fall (comparisons/sign_change)"
    elif cls == "unchanged":
        why = "equal values read 'unchanged' (comparisons/loss_words)"
    else:
        why = f"the value {'rose' if cls == 'up' else 'fell'}"
    print(f"MISMATCH  {a.word!r}: {why}")
    print(f"  right: {phrase}")
    return 1


# ── window ────────────────────────────────────────────────────────────────────────────────────────────────────────

def cmd_window(a) -> int:
    if a.days < 0:
        raise Bad("--days is a whole number of days, 0 or more")
    today = parse_date(a.today) if a.today else dt.date.today()
    since = today - dt.timedelta(days=a.days)
    dates = [parse_date(d) for d in a.dates]
    print(f"window: on or after {since} ({a.days} days before {today}; its first day is inside)")
    out = 0
    for d in dates:
        if d > today:
            print(f"  AFTER    {d}: after {today}")
            out = 1
        elif d >= since:
            print(f"  inside   {d}")
        else:
            print(f"  OUTSIDE  {d}: {(since - d).days} days before the window starts")
            out = 1
    return out


# ── validate and show ─────────────────────────────────────────────────────────────────────────────────────────────

def example_problems(r: dict) -> list:
    """An example row recomputed: its label (with its offset), and its end-year-rule label or year."""
    out = []
    if not r.get("fye") or not r.get("end"):
        return out
    cal, end = parse_fye(r["fye"]), parse_date(r["end"])
    start = parse_date(r["start"]) if r.get("start") else None
    off = r.get("offset", 0)
    wk = bool(r.get("weeks52"))
    rep = r.get("transition_report") is True
    if "label" in r:
        k = kind_of(start, end, wk, rep) if start else None
        q = quarter_of(end, cal)
        if k == "annual" and q not in (None, "Q4"):
            got = f"twelve months to {q} FY{fiscal_year_of(end, cal, off)}"
        elif start:
            got = period_label(start, end, cal, off, wk, rep)
        else:
            got = f"{q} FY{fiscal_year_of(end, cal, off)}" if q else None
        if got != r["label"]:
            out.append(f"examples/{r['id']}: recomputed {got!r}, the row says {r['label']!r}")
    if "rule_label" in r:
        got = period_label(start, end, cal, 0, wk) if start else f"{quarter_of(end, cal)} FY{fiscal_year_of(end, cal)}"
        if got != r["rule_label"]:
            out.append(f"examples/{r['id']}: end-year rule recomputed {got!r}, the row says {r['rule_label']!r}")
    if "rule_year" in r and fiscal_year_of(end, cal) != r["rule_year"]:
        out.append(f"examples/{r['id']}: end-year rule year {fiscal_year_of(end, cal)}, the row says {r['rule_year']}")
    return out


def cmd_validate(a) -> int:
    problems, n, n_ex = [], 0, 0
    for sec in SECTIONS:
        rows = REF.get(sec)
        if not isinstance(rows, list) or not rows:
            problems.append(f"{sec}: no rows")
            continue
        ids = [r.get("id") for r in rows]
        if len(ids) != len(set(ids)):
            problems.append(f"{sec}: a duplicate id")
        for r in rows:
            n += 1
            for k in ("id", "what", "source"):
                if not str(r.get(k) or "").strip():
                    problems.append(f"{sec}/{r.get('id')}: no {k}")
            if "min" in r and not r["min"] <= r["max"]:
                problems.append(f"{sec}/{r['id']}: min above max")
            if "quote" in r and "CFR" not in r.get("source", ""):
                problems.append(f"{sec}/{r['id']}: a quote whose source names no CFR section")
            for c in re.findall(r"\d+ CFR ([\w.-]+)", r.get("source", "")):
                if not re.fullmatch(r"\d+\.\d+[a-z]?(?:-\d+)?", c):
                    problems.append(f"{sec}/{r['id']}: not a CFR section: {c}")
    for r in REF.get("examples", []):
        try:
            p = example_problems(r)
        except (Bad, KeyError) as e:
            p = [f"examples/{r.get('id')}: {e}"]
        n_ex += 1 if r.get("fye") and r.get("end") else 0
        problems += p
    print(f"validate: {n} rows in {len(SECTIONS)} sections; {n_ex} examples recomputed; "
          + ("valid" if not problems else f"{len(problems)} problems"))
    for p in problems:
        print(f"  INVALID {p}")
    return 1 if problems else 0


def cmd_show(a) -> int:
    if not a.words:
        for sec in SECTIONS:
            print(f"{sec}: {len(REF.get(sec, []))} rows")
        return 0
    ws = [w.lower() for w in a.words]
    hits = [(sec, r) for sec in SECTIONS for r in REF.get(sec, [])
            if all(w in json.dumps(r, ensure_ascii=False).lower() for w in ws)]
    for sec, r in hits:
        v = f"{r['min']}-{r['max']}" if "min" in r else (json.dumps(r["value"]) if "value" in r else "")
        print(f"{sec}/{r['id']}" + (f" = {v}" if v else "") + f"\n  {r['what']}\n  source: {r['source']}")
    if not hits:
        print("period: no row holds " + " ".join(a.words))
    return 0 if hits else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="period.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    for n in ("label", "check-label"):
        s = sub.add_parser(n)
        if n == "check-label":
            s.add_argument("label")
        s.add_argument("--fye", required=True)
        s.add_argument("--end", required=True)
        s.add_argument("--start")
        s.add_argument("--offset", type=int)
        s.add_argument("--weeks52", action="store_true")
        s.add_argument("--transition-report", action="store_true",
                       help="the fact is from a transition report (form 10-KT or 10-QT, or dei:DocumentTransitionReport "
                            "true): an unbanded duration shorter than 12 months is then a transition period")
    q = sub.add_parser("quarterize")
    q.add_argument("file")
    q.add_argument("--fye")
    q.add_argument("--offset", type=int)
    q.add_argument("--non-additive", action="store_true")
    q.add_argument("--weeks52", action="store_true")
    q.add_argument("--tol", type=float, default=0.0)
    c = sub.add_parser("compare")
    c.add_argument("--cur", nargs=3, metavar=("START", "END", "VALUE"), required=True)
    c.add_argument("--prior", nargs=3, metavar=("START", "END", "VALUE"))
    c.add_argument("--word")
    c.add_argument("--weeks52", action="store_true")
    c.add_argument("--tol", type=float, default=0.0)
    w = sub.add_parser("window")
    w.add_argument("--days", type=int, required=True)
    w.add_argument("--today")
    w.add_argument("dates", nargs="+")
    sub.add_parser("validate")
    s = sub.add_parser("show")
    s.add_argument("words", nargs="*")
    a = ap.parse_args(argv)
    try:
        return {"label": cmd_label, "quarterize": cmd_quarterize, "check-label": cmd_check_label,
                "compare": cmd_compare, "window": cmd_window, "validate": cmd_validate, "show": cmd_show}[a.cmd](a)
    except Bad as e:
        print(f"period: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
