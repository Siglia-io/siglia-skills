#!/usr/bin/env python3
"""ties.py - do a filer's statements tie on its held XBRL facts, before a number derived from them is trusted or cited.

Part of the siglia-statement-ties skill. The identities, the us-gaap elements each reads (with the sign FASB's balance
attribute gives a movement) and the constants are data/ties.json, every row with its source. Read-only and offline: it
reads the facts file and its data, nothing else.

  ties.py check FACTS.json [--period YYYY-MM-DD] [--json]   every applicable tie: TIES, BREAK (gap, elements, context
                                                             ids, a class) or ABSENT (what is missing, bounded to the
                                                             facts read)
  ties.py explain [TIE]                                      the identity, its elements and traps, each with its source
FACTS.json: a whole companyfacts file ({"facts": {taxonomy: {tag: {"units": {unit: [rows]}}}}}; each row takes its tag
and unit from its parent keys), a list of facts, or {"facts": [...]}. A fact: tag (us-gaap:Assets or Assets), start
(absent for an instant), end, value (or val, value_numeric), unit (default USD), and optionally context (its contextRef),
dims {axis: member} or segments "Axis=Member;...", decimals, filed and accn (the latest filed wins).
Exit: check 0 every checked tie ties · 1 a BREAK · 2 the facts file or --period unreadable · 3 no tie applicable
      explain 0 found · 1 no such tie
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("TIES_DATA") or os.path.join(HERE, "..", "data", "ties.json")
ORDER = ("balance_totals", "balance_parts", "cash_roll", "cash_sections", "net_income", "retained_earnings",
         "equity_roll", "segment_sum", "ytd_quarter")
ROLLS = ("cash_roll", "retained_earnings", "equity_roll")    # the relative tolerance is on the movements
SCALE = Decimal(1000)


class Bad(Exception):
    """The facts file cannot be read as facts."""


class Conflict(Exception):
    """Two values for one fact and no filed date to choose between them."""


def load() -> tuple:
    d = json.load(open(DATA))
    return d, {r["id"]: r["value"] for r in d["constants"]}


# ── reading the facts ──────────────────────────────────────────────────────────────────────────────────────────────────
def norm_tag(t) -> str:
    """us-gaap:Assets, us-gaap_Assets and Assets are one tag. A custom or other-taxonomy tag keeps its prefix, so it
    matches no element here."""
    t = str(t).strip()
    for p in ("us-gaap:", "us-gaap_"):
        if t.startswith(p):
            return t[len(p):]
    return t


def norm_name(s, suffix: str) -> str:
    s = str(s).strip()
    s = s.split(":", 1)[1] if ":" in s else s
    for p in ("us-gaap_", "srt_"):
        if s.startswith(p):
            s = s[len(p):]
    return s[:-len(suffix)] if s.endswith(suffix) and len(s) > len(suffix) else s


def _date(v, what: str, i: int):
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise Bad(f"fact {i}: {what} {v!r} is not YYYY-MM-DD")


def _pick(f: dict, *keys):
    return next((f[k] for k in keys if k in f and f[k] not in (None, "")), None)


def parse_dims(f: dict, i: int, alias: dict) -> tuple:
    pairs = []
    raw = f.get("dims") or f.get("dimensions") or {}
    if not isinstance(raw, dict):
        raise Bad(f"fact {i}: dims must be an object {{axis: member}}")
    pairs += list(raw.items())
    seg = f.get("segments") or ""
    for part in (p for p in str(seg).split(";") if p.strip()):
        if "=" not in part:
            raise Bad(f"fact {i}: segments {seg!r} is not Axis=Member;...")
        a, m = part.split("=", 1)
        pairs.append((a, m))
    out = {}
    for a, m in pairs:
        a = norm_name(a, "Axis")
        out[alias.get(a, a)] = norm_name(m, "Member")
    return tuple(sorted(out.items()))


def companyfacts(tree: dict, path: str) -> list:
    """A companyfacts file's facts, {taxonomy: {tag: {"units": {unit: [rows]}}}}, as flat rows. A row ({start, end, val,
    accn, fy, fp, form, filed, frame}) holds no tag and no unit: both are its parent keys, so each row takes them here."""
    flat = []
    for tax, tags in tree.items():
        if not isinstance(tags, dict):
            raise Bad(f"{path}: companyfacts facts[{tax!r}] is not an object of tags")
        for name, body in tags.items():
            units = body.get("units") if isinstance(body, dict) else None
            if not isinstance(units, dict):
                raise Bad(f"{path}: companyfacts {tax}:{name} has no units object")
            for unit, rows in units.items():
                if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                    raise Bad(f"{path}: companyfacts {tax}:{name} {unit} is not a list of rows")
                flat += [dict(r, tag=f"{tax}:{name}", unit=unit) for r in rows]
    return flat


def read_facts(path: str, const: dict) -> tuple:
    """(facts, shape): shape is "companyfacts" for a whole companyfacts file, else "list"."""
    try:
        raw = json.load(open(path))
    except (OSError, ValueError) as e:
        raise Bad(f"{path}: {e}")
    facts = raw.get("facts") if isinstance(raw, dict) else raw
    shape = "list"
    if isinstance(facts, dict):
        facts, shape = companyfacts(facts, path), "companyfacts"
    if not isinstance(facts, list):
        raise Bad(f"{path}: expected a companyfacts file, a list of facts or {{\"facts\": [...]}}")
    alias = {norm_name(k, "Axis"): norm_name(v, "Axis") for k, v in const["fsds_axis_alias"].items()}
    out = []
    for i, f in enumerate(facts):
        if not isinstance(f, dict):
            raise Bad(f"fact {i}: not an object")
        tag, end = _pick(f, "tag", "concept", "name"), _pick(f, "end", "period_end", "instant", "date")
        val = _pick(f, "value", "val", "value_numeric")
        if tag is None or end is None or val is None:
            raise Bad(f"fact {i}: needs tag, end and value" + (
                " (a companyfacts row carries no tag or unit: both are its parent keys, so pass the whole companyfacts "
                "file, or add tag and unit to each row)" if tag is None and "val" in f else ""))
        try:
            value = Decimal(str(val))
        except InvalidOperation:
            raise Bad(f"fact {i}: value {val!r} is not a number")
        if not value.is_finite():
            raise Bad(f"fact {i}: value {val!r} is not a number")
        dec = _pick(f, "decimals")
        if dec is not None and str(dec).upper() != "INF":
            try:
                dec = int(dec)
            except ValueError:
                raise Bad(f"fact {i}: decimals {dec!r} is not a whole number or INF")
        else:
            dec = None
        start = _date(_pick(f, "start", "period_start"), "start", i)
        endd = _date(end, "end", i)
        if start is not None and start > endd:
            raise Bad(f"fact {i}: start {start} is after end {endd}")
        ctx = _pick(f, "context", "contextRef", "context_ref", "context_id")
        out.append({"tag": norm_tag(tag), "start": start, "end": endd, "value": value,
                    "unit": str(_pick(f, "unit", "uom", "units") or "USD"), "dims": parse_dims(f, i, alias),
                    "filed": _date(_pick(f, "filed"), "filed", i),
                    "accn": str(_pick(f, "accn", "accession", "accession_number") or ""),
                    "decimals": dec, "context": str(ctx) if ctx is not None else ""})
    return out, shape


def fkey(f: dict) -> tuple:
    return (f["tag"], f["start"], f["end"], f["unit"], f["dims"])


def q(tag: str) -> str:
    """A tag as printed: us-gaap elements with their prefix; a filer's own element keeps its own."""
    return tag if ":" in tag else "us-gaap:" + tag


def cid(f: dict) -> str:
    """The fact's context id: its own contextRef when the facts carry one. A companyfacts row has none, so its id here
    is the accession and the period (and any dimensions), which name the filing and the context uniquely."""
    if f.get("context"):
        return f["context"]
    p = f"{f['start']}--{f['end']}" if f["start"] else f"{f['end']}"
    return f"{f['accn'] or 'no-accn'}|{p}" + "".join(f"[{a}={m}]" for a, m in f["dims"])


class Store:
    """One value per (tag, start, end, unit, dims). Repeats with one value are one fact. Different values: the latest
    filed wins; with no filed date to choose by, the fact is a conflict and is never guessed."""

    def __init__(self, facts: list):
        groups: dict = {}
        for f in facts:
            groups.setdefault((f["tag"], f["start"], f["end"], f["unit"], f["dims"]), []).append(f)
        self.one: dict = {}
        self.conflict: dict = {}
        self.accns: dict = {k: {f["accn"] for f in fs if f["accn"]} for k, fs in groups.items()}
        for k, fs in groups.items():
            if len({f["value"] for f in fs}) == 1:
                self.one[k] = max(fs, key=lambda f: (f["filed"] or dt.date.min, f["accn"]))
                continue
            if all(f["filed"] for f in fs):
                best = max(fs, key=lambda f: (f["filed"], f["accn"]))
                if all(f["value"] == best["value"] for f in fs if (f["filed"], f["accn"]) == (best["filed"], best["accn"])):
                    self.one[k] = best
                    continue
            self.conflict[k] = fs

    def get(self, tag: str, start, end, unit: str, dims: tuple = ()):
        k = (tag, start, end, unit, dims)
        if k in self.conflict:
            vals = sorted({str(f["value"]) for f in self.conflict[k]})
            raise Conflict(f"{len(self.conflict[k])} values for us-gaap:{tag} at {end} ({', '.join(vals)}) and no filed "
                           f"date to choose by")
        return self.one.get(k)

    def keys(self):
        return list(self.one) + list(self.conflict)

    def carriers(self, facts: list) -> set:
        """The filings that carry every one of these facts (each with this value or another)."""
        sets = [self.accns.get(fkey(f), set()) for f in facts]
        return set.intersection(*sets) if sets else set()

    def first(self, tags, start, end, unit, dims: tuple = ()):
        for t in tags:
            f = self.get(t, start, end, unit, dims)
            if f is not None:
                return f
        return None


# ── the ties ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def erows(data: dict, tie: str, role: str, basis=None) -> list:
    rows = [e for e in data["elements"] if tie in e["tie"].split() and e["role"] == role
            and (basis is None or e.get("basis") == basis)]
    return sorted(rows, key=lambda e: e["order"])


def els(data: dict, tie: str, role: str, basis=None) -> list:
    return [local(e["element"]) for e in erows(data, tie, role, basis)]


def local(element: str) -> str:
    """us-gaap:Assets -> Assets (the data's elements are prefixed; the facts' tags are not)."""
    return element.split(":", 1)[1]


def tol(const: dict, *vals) -> Decimal:
    return max(Decimal(str(const["tolerance_abs"])), Decimal(str(const["tolerance_rel"])) * max(abs(v) for v in vals))


def row(tie: str, end, unit: str, start=None, variant: str = "") -> dict:
    return {"tie": tie, "variant": variant, "start": start, "end": end, "unit": unit, "status": "ABSENT", "left": None,
            "right": [], "gap": None, "tolerance": None, "facts": [], "note": "", "hint": "", "class": "", "filing": "", "_terms": []}


def absent(r: dict, what: str) -> dict:
    r["status"], r["note"] = "ABSENT", "could not establish: " + what
    return r


def val(x) -> Decimal:
    return x["value"] if isinstance(x, dict) else x


def settle(r: dict, const: dict, left: tuple, right: list, extra: tuple = (), base=None) -> dict:
    """left = (label, fact or value); right = [(label, fact or value, +1 or -1), ...]. TIES when |left - sum(right)| is
    within the tolerance of the larger side (of `base` when given: a roll-forward's movements, never its balance), or
    within the inputs' own rounding when their decimals are given (QF-41)."""
    lv = val(left[1])
    rv = sum((c * val(x) for _, x, c in right), Decimal(0))
    r["left"] = (left[0], lv)
    r["right"] = [(lab, val(x), c) for lab, x, c in right]
    r["_terms"] = [(left[1], 0)] + [(x, c) for _, x, c in right]
    r["gap"] = lv - rv
    facts = [x for x in [left[1]] + [x for _, x, _ in right] + list(extra) if isinstance(x, dict)]
    half = Decimal(str(const["rounding"]))
    rounding = sum((half * Decimal(10) ** -f["decimals"] for f in facts if f.get("decimals") is not None), Decimal(0))
    r["tolerance"] = max(tol(const, lv, rv) if base is None else tol(const, base), rounding)
    r["status"] = "TIES" if abs(r["gap"]) <= r["tolerance"] else "BREAK"
    seen = {}
    for f in facts:
        seen.setdefault((f["tag"], cid(f)), f)
    r["facts"] = list(seen.values())
    return r


def movements(terms: list, beg: dict, end_bal: dict) -> Decimal:
    """What a roll-forward's relative tolerance is taken on: the larger of the movements read (sum of their sizes) and
    closing less opening. Never the balance: 0.5% of a balance lets a movement smaller than that go missing unseen."""
    return max(sum((abs(val(x)) for _, x, _ in terms), Decimal(0)), abs(end_bal["value"] - beg["value"]))


def balance(store: Store, data: dict, const: dict) -> list:
    a_t, lse_t = els(data, "balance_totals", "total assets")[0], els(data, "balance_totals", "total liabilities and equity")[0]
    dates = sorted({(k[2], k[3]) for k in store.keys() if k[0] in (a_t, lse_t) and k[1] is None and k[4] == ()})
    out = []
    for d, u in dates:
        r = row("balance_totals", d, u)
        try:
            a, lse = store.get(a_t, None, d, u), store.get(lse_t, None, d, u)
            if a is None or lse is None:
                absent(r, f"us-gaap:{a_t if a is None else lse_t} is not among the facts read at {d}")
            else:
                settle(r, const, ("Assets", a), [("LiabilitiesAndStockholdersEquity", lse, 1)])
        except Conflict as e:
            absent(r, str(e))
        out.append(r)
        out.append(balance_parts(store, data, const, d, u, a_t, lse_t))
    return out


def balance_parts(store: Store, data: dict, const: dict, d, u: str, a_t: str, lse_t: str) -> dict:
    r = row("balance_parts", d, u)
    try:
        left = store.get(a_t, None, d, u) or store.get(lse_t, None, d, u)
        liab = store.first(els(data, "balance_parts", "liabilities"), None, d, u)
        eq_incl, eq_par, mi = (store.get(t, None, d, u) for t in els(data, "balance_parts", "equity"))
        t_incl, t_par, t_rnci = (store.get(t, None, d, u) for t in els(data, "balance_parts", "temporary equity"))
        right: list = []
        if eq_incl is not None:
            right.append(("equity incl. NCI", eq_incl, 1))
        elif eq_par is not None:
            right.append(("parent equity", eq_par, 1))
            if mi is not None:
                right.append(("noncontrolling interest", mi, 1))
        else:
            return absent(r, f"no equity total (us-gaap:StockholdersEquity or the including-NCI total) is among the facts "
                             f"read at {d}")
        if t_incl is not None:
            right.append(("temporary equity incl. NCI", t_incl, 1))
        else:
            right += [(lab, f, 1) for lab, f in (("temporary equity", t_par), ("redeemable NCI", t_rnci)) if f is not None]
        if liab is None:
            implied = left["value"] - sum((f["value"] for _, f, _ in right), Decimal(0))
            return absent(r, f"us-gaap:Liabilities is not among the facts read at {d} (LS-10: many filers do not tag "
                             f"it); implied liabilities (us-gaap:{left['tag']} less equity and temporary equity) "
                             f"{fmt(implied)}")
        settle(r, const, (left["tag"], left), [("Liabilities", liab, 1)] + right)
        if r["status"] == "BREAK" and t_incl is None and t_par is None and t_rnci is None:
            r["hint"] = "no temporary equity tagged: a gap here can be redeemable stock tagged under a filer's own element"
    except Conflict as e:
        absent(r, str(e))
    return r


def opening(store: Store, tag: str, start, unit: str, days: int):
    """The latest balance 0..days before the duration's start (a 52/53-week year ends a few days off the calendar)."""
    cands = [k for k in store.keys() if k[0] == tag and k[1] is None and k[3] == unit and k[4] == ()
             and 0 <= (start - k[2]).days <= days]
    for k in sorted(cands, key=lambda k: k[2], reverse=True):
        return store.get(*k)
    return None


def balances(store: Store, data: dict, basis: str, s, e, u: str, days: int) -> tuple:
    """(opening, closing) on one balance element, the first of the basis's chain tagged at both ends."""
    for t in els(data, "cash_roll", "balance", basis):
        end_bal = store.get(t, None, e, u)
        beg_bal = opening(store, t, s, u, days)
        if end_bal is not None and beg_bal is not None:
            return beg_bal, end_bal
    return None, None


def cash(store: Store, data: dict, const: dict) -> list:
    out = []
    bases = ("restricted", "cash only")
    days = int(const["opening_balance_days"])
    changes = {b: (els(data, "cash_roll", "change including FX", b), els(data, "cash_roll", "change excluding FX", b),
                   els(data, "cash_roll", "fx", b)) for b in bases}
    all_change = {t for b in bases for t in changes[b][0] + changes[b][1]}
    cfo_t, cfi_t, cff_t = (els(data, "cash_sections", x)[0] for x in ("CFO", "CFI", "CFF"))
    durs = sorted({(k[1], k[2], k[3]) for k in store.keys() if k[1] is not None and k[4] == () and k[0] in all_change})
    for s, e, u in durs:                                     # cash_roll: opening + change = closing
        for b in bases:
            incl, excl, fx = changes[b]
            r = row("cash_roll", e, u, s, b)
            try:
                ci, ce = store.first(incl, s, e, u), store.first(excl, s, e, u)
                if ci is None and ce is None:
                    continue
                beg, end_bal = balances(store, data, b, s, e, u, days)
                if beg is None:
                    absent(r, f"no {b} balance is among the facts read at both {s} (0-{days} days before) and {e} on one "
                              f"element; the two bases are never mixed (CF-30)")
                else:
                    right = [("opening " + beg["tag"], beg, 1)]
                    if ci is not None:
                        right.append(("change", ci, 1))
                    else:
                        right.append(("change excl. FX", ce, 1))
                        x = store.first(fx, s, e, u)
                        if x is not None:
                            right.append(("FX effect", x, 1))
                    settle(r, const, ("closing " + end_bal["tag"], end_bal), right,
                           base=movements(right[1:], beg, end_bal))
                    if ci is None and len(right) == 2:
                        r["note"] = "FX effect not tagged (counted as 0)"
            except Conflict as ex:
                absent(r, str(ex))
            out.append(r)
    for s, e, u in sorted({(k[1], k[2], k[3]) for k in store.keys() if k[0] == cfo_t and k[1] is not None and k[4] == ()}):
        r = row("cash_sections", e, u, s)                    # cash_sections: CFO + CFI + CFF (+ FX) = change
        try:
            cfo, cfi, cff = (store.get(t, s, e, u) for t in (cfo_t, cfi_t, cff_t))
            missing = [t for t, f in ((cfo_t, cfo), (cfi_t, cfi), (cff_t, cff)) if f is None]
            if missing:
                out.append(absent(r, "not among the facts read over the duration: "
                                     + ", ".join("us-gaap:" + t for t in missing)))
                continue
            parts = [("CFO", cfo, 1), ("CFI", cfi, 1), ("CFF", cff, 1)]
            left, x, extra = None, None, ()
            for b in bases:
                incl, excl, fx = changes[b]
                ci, ce = store.first(incl, s, e, u), store.first(excl, s, e, u)
                if ci is not None or ce is not None:
                    left = ("change", ci) if ci is not None else ("change excl. FX", ce)
                    x = store.first(fx, s, e, u) if ci is not None else None
                    break
            if left is None:                                 # no change element: closing - opening, one basis
                for b in bases:
                    beg, end_bal = balances(store, data, b, s, e, u, days)
                    if beg is not None:
                        left = ("closing - opening " + end_bal["tag"], end_bal["value"] - beg["value"])
                        x, extra = store.first(changes[b][2], s, e, u), (beg, end_bal)
                        break
            if left is None:
                out.append(absent(r, "no net change in cash is among the facts read, and no opening and closing balance "
                                     "on one basis"))
                continue
            if x is not None:
                parts.append(("FX effect", x, 1))
            settle(r, const, left, parts, extra)
        except Conflict as ex:
            absent(r, str(ex))
        out.append(r)
    return out


def income(store: Store, data: dict, const: dict) -> list:
    """net_income: over each cash-flow duration, the consolidated net income the cash-flow statement starts from
    (ProfitLoss) = the income statement's net income attributable to the parent + the noncontrolling interests' share."""
    cfo_t = els(data, "cash_sections", "CFO")[0]
    cf_t = els(data, "net_income", "cash-flow net income")
    ni_t = els(data, "net_income", "parent net income")[0]
    nci = erows(data, "net_income", "noncontrolling share")
    nci_total = [e["element"].split(":", 1)[1] for e in nci if e["order"] == 1]
    nci_parts = [e["element"].split(":", 1)[1] for e in nci if e["order"] == 2]
    nci_cont = [e["element"].split(":", 1)[1] for e in nci if e["order"] == 3]
    out = []
    cf_durations = sorted({(k[1], k[2], k[3]) for k in store.keys() if k[0] == cfo_t and k[1] is not None and k[4] == ()})
    for s, e, u in cf_durations:
        r = row("net_income", e, u, s)
        try:
            pl, ni = store.first(cf_t, s, e, u), store.get(ni_t, s, e, u)
            share = [f for f in (store.first(nci_total, s, e, u),) if f is not None] or \
                    [f for f in (store.get(t, s, e, u) for t in nci_parts) if f is not None]
            cont = not share and bool([f for f in (store.first(nci_cont, s, e, u),) if f is not None])
            if cont:                                         # the labelled fallback: continuing operations only
                share = [store.first(nci_cont, s, e, u)]
            if pl is None and ni is None:
                out.append(absent(r, f"neither us-gaap:{cf_t[0]} nor us-gaap:{ni_t} is among the facts read over the "
                                     f"cash-flow duration {s}..{e}"))
                continue
            if pl is not None and ni is not None:
                settle(r, const, ("cash-flow opening " + pl["tag"], pl),
                       [(ni_t, ni, 1)] + [(f["tag"], f, 1) for f in share])
                if not share:
                    r["note"] = "no noncontrolling share tagged (counted as 0)"
                elif cont:
                    r["note"] = (f"the noncontrolling share read is continuing operations only (us-gaap:{share[0]['tag']}; "
                                 f"neither the total nor its redeemable and nonredeemable parts is tagged): a "
                                 f"noncontrolling share of discontinued operations is not in it")
            elif share:
                have = pl or ni
                miss = ni_t if ni is None else cf_t[0]
                out.append(absent(r, f"us-gaap:{miss} is not among the facts read over {s}..{e}, while a noncontrolling "
                                     f"share (us-gaap:{share[0]['tag']}) and us-gaap:{have['tag']} are"))
                continue
            else:                                            # one element, one fact, carried by both statements
                one = pl or ni
                out.append(absent(r, f"one fact carries both statements' net income in this context (us-gaap:"
                                     f"{one['tag']} {fmt(one['value'])} over {s}..{e}); the facts cannot separate the "
                                     f"income statement from the cash-flow statement (one element in one context is "
                                     f"one fact), so this tie cannot fail here and is not counted as tying"))
                continue
        except Conflict as ex:
            absent(r, str(ex))
        out.append(r)
    return out


def groups_of(data: dict, tie: str) -> list:
    """The movement groups of a roll-forward, in order: [(group, [element rows in chain order])]."""
    g: dict = {}
    for e in erows(data, tie, "movement"):
        g.setdefault(e["group"], []).append(e)
    return sorted(g.items(), key=lambda kv: min(e["seq"] for e in kv[1]))


def roll(store: Store, data: dict, const: dict, tie: str) -> list:
    """retained_earnings / equity_roll: opening balance + the movements read = closing balance, over each duration its
    anchor (the net income) is tagged for. Each group reads the first element of its chain that is tagged; a movement is
    added or subtracted by the sign its element row carries (FASB's balance attribute: credit adds, debit subtracts). An
    element row's net_out names the parts inside it that leave this balance unchanged (stock and PIK dividends inside an
    all-forms dividend, for total equity), taken back out when tagged. The relative tolerance is taken on the movements,
    never the balance. No closing balance at the end: ABSENT, naming a balance of the same date this roll does not read."""
    bal = els(data, tie, "balance")
    unread = erows(data, tie, "unread balance")
    groups = groups_of(data, tie)
    anchor = [e["element"].split(":", 1)[1] for e in groups[0][1]]
    days = int(const["opening_balance_days"])
    out = []
    durs = sorted({(k[1], k[2], k[3]) for k in store.keys() if k[0] in anchor and k[1] is not None and k[4] == ()})
    for s, e, u in durs:
        r = row(tie, e, u, s)
        try:
            end_bal = beg = None
            for t in bal:
                eb = store.get(t, None, e, u)
                if eb is None:
                    continue
                end_bal, beg = eb, opening(store, t, s, u, days)
                if beg is not None:
                    break
            if end_bal is None:
                other = next(((x, f) for x, f in ((x, store.get(x["element"].split(":", 1)[1], None, e, u))
                                                  for x in unread) if f is not None), None)
                out.append(absent(r, f"us-gaap:{bal[0]} is not among the facts read at {e}" + (
                    f"; {other[0]['element']} is ({fmt(other[1]['value'])}), which this roll does not read: "
                    f"{other[0]['why']}" if other else "")))
                continue
            if beg is None:
                out.append(absent(r, f"no opening us-gaap:{end_bal['tag']} is among the facts read 0-{days} days before "
                                     f"{s}"))
                continue
            terms, missing, used, notes = [("opening " + beg["tag"], beg, 1)], [], set(), []
            netted, allforms, credit = set(), [], None
            for name, chain in groups:
                head = chain[0]
                if any(local(x) in used for x in head.get("unless", [])):
                    continue
                if "with" in head:                          # the stock dividend's credit: read only beside a debit
                    blocked = sorted({local(x) for x in head.get("unless_netted", [])} & netted)
                    # 2.2 (review): a class's stock dividend is inside only that class's all-forms dividend or Dividends.
                    # A preferred all-forms read never covers a common stock dividend tagged beside cash-only common
                    # dividends: its debit was never subtracted, so its credit is not added back
                    uncovered = []
                    for deb, cls in head.get("class_debits", {}).items():
                        try:
                            tagged = store.get(local(deb), s, e, u) is not None
                        except Conflict:
                            tagged = True
                        if tagged and not {local(cls), "Dividends"} & used:
                            uncovered.append(local(deb))
                    if not {local(x) for x in head["with"]} & used or blocked or uncovered:
                        try:                                # unread, so a conflict on it never stops the roll
                            f = store.first([local(c["element"]) for c in chain], s, e, u)
                        except Conflict:
                            f = None
                        if f is not None:
                            notes.append(f"us-gaap:{f['tag']} ({fmt(f['value'])}) not read: " + (
                                "the stock dividend is already netted out (" + ", ".join("us-gaap:" + t for t in blocked)
                                + ")" if blocked else "its class's stock dividend (" + ", ".join(
                                    "us-gaap:" + t for t in uncovered) + ") is in no dividend read, so its debit was "
                                "never subtracted" if uncovered else "the dividends read exclude stock dividends, so "
                                                                     "none left this balance to be added back"))
                        continue
                if head.get("read") == "each":              # exclusive elements, summed; one value twice is read once
                    found = [(c, f) for c, f in ((c, store.get(local(c["element"]), s, e, u)) for c in chain)
                             if f is not None]
                    hits = []
                    for c, f in found:
                        same = next((g for _, g in hits if g["value"] == f["value"]), None)
                        if same is None:
                            hits.append((c, f))
                        else:
                            notes.append(f"us-gaap:{f['tag']} equals us-gaap:{same['tag']} ({fmt(f['value'])}): read "
                                         f"once, as one {name} tagged twice (this skill's choice: FASB's elements are "
                                         f"exclusive and its equity calculation sums them)")
                else:
                    hit = next(((c, f) for c, f in ((c, store.get(local(c["element"]), s, e, u)) for c in chain)
                                if f is not None), None)
                    hits = [hit] if hit is not None else []
                if not hits:
                    missing.append(name)
                    continue
                for c, f in hits:
                    used.add(f["tag"])
                    terms.append((f["tag"], f, int(c["sign"])))
                    if "with" in head:
                        credit = f
                    if c.get("net_out"):
                        outs = [g for g in (store.get(local(x), s, e, u) for x in c["net_out"]) if g is not None]
                        terms += [(g["tag"] + " (netted out)", g, -int(c["sign"])) for g in outs]
                        netted |= {g["tag"] for g in outs}
                        allforms.append((f["tag"], outs))
            for tag, outs in allforms:                      # said once the stock dividend's credit is known
                notes.append(f"us-gaap:{tag} counts stock and PIK dividends, which leave this balance unchanged: " + (
                    ", ".join("us-gaap:" + g["tag"] for g in outs) + " netted out" if outs else "none netted out")
                    + (f"; the stock dividend's credit us-gaap:{credit['tag']} is added back (FASB's equity calculation "
                       f"pairs the two)" if credit is not None else "" if outs else ", so any inside it is subtracted too"))
            settle(r, const, ("closing " + end_bal["tag"], end_bal), terms, base=movements(terms[1:], beg, end_bal))
            r["note"] = "; ".join(["not tagged over the duration (counted as 0): " + ", ".join(missing)] * bool(missing)
                                  + notes)
        except Conflict as ex:
            absent(r, str(ex))
        out.append(r)
    return out


def segments(store: Store, data: dict, const: dict) -> list:
    seg_axis = norm_name(next(m["name"] for m in data["members"] if m["kind"] == "axis" and m["role"] == "segment"), "Axis")
    ci_axis = norm_name(next(m["name"] for m in data["members"] if m["kind"] == "axis" and m["role"] != "segment"), "Axis")
    op = next(norm_name(m["name"], "Member") for m in data["members"] if m["kind"] == "member" and m["role"] == "segment")
    recon = [norm_name(m["name"], "Member") for m in data["members"] if m["kind"] == "member" and m["role"] == "reconciling"]
    # the reportable segments' aggregation subtotal sits on the segment axis beside the segments it sums: never a part
    sub = [norm_name(m["name"], "Member") for m in data["members"] if m["kind"] == "member" and m["role"] == "subtotal"]
    out = []
    for tag in const["revenue_chain"]:
        groups: dict = {}
        for k in store.keys():
            if k[0] == tag and k[1] is not None and k[4] and {a for a, _ in k[4]} <= {seg_axis, ci_axis}:
                groups.setdefault((k[1], k[2], k[3]), []).append(k)
        for (s, e, u), ks in sorted(groups.items()):
            dims = [dict(k[4]) for k in ks]
            # One fact per segment. A filer can tag a segment's revenue twice, on the segment axis alone (the
            # disaggregation note) and with ConsolidationItems=OperatingSegments (the segment note): the
            # OperatingSegments fact is the segment's own figure and is counted, and the other is named.
            by_member: dict = {}
            subtotals = []
            for k, d in zip(ks, dims):
                if seg_axis in d and d[seg_axis] in sub:
                    subtotals.append(k)                  # a subtotal of the segments: named, never summed
                elif seg_axis in d and d.get(ci_axis, op) == op:
                    by_member.setdefault(d[seg_axis], []).append(k)
            seg_keys, twice = [], []
            for m, mk in by_member.items():
                keep = next((k for k in mk if dict(k[4]).get(ci_axis) == op), mk[0])
                seg_keys.append(keep)
                twice += [(m, keep, k) for k in mk if k != keep]
            op_keys = [k for k, d in zip(ks, dims) if d == {ci_axis: op}]
            if not seg_keys and not op_keys and not subtotals:
                continue
            r = row("segment_sum", e, u, s, tag)
            try:
                sub_named = ", ".join(subtotal_name(store, k, seg_axis, ci_axis) for k in subtotals)
                if not seg_keys and not op_keys:
                    out.append(absent(r, f"only the reportable segments' aggregation subtotal is tagged on the segment "
                                         f"axis ({sub_named}), and a subtotal is never summed as a segment"))
                    continue
                total = store.get(tag, s, e, u)
                if total is None:
                    out.append(absent(r, f"no undimensioned us-gaap:{tag} is among the facts read over the duration: a "
                                         f"missing default is not zero (QF-37)"))
                    continue
                parts = [("segment " + dict(k[4])[seg_axis], store.get(*k), 1) for k in seg_keys] if seg_keys else \
                        [("operating segments total", store.get(*op_keys[0]), 1)]
                rec_parts = []
                for m in recon:
                    alone = [k for k, d in zip(ks, dims) if d == {ci_axis: m}]
                    per_seg = [k for k, d in zip(ks, dims) if d.get(ci_axis) == m and seg_axis in d and d[seg_axis] not in sub]
                    for k in alone or per_seg:
                        rec_parts.append((m + (" " + dict(k[4])[seg_axis] if seg_axis in dict(k[4]) else ""),
                                          store.get(*k), 1))
                other = sorted({d[ci_axis] for d in dims if ci_axis in d and d[ci_axis] not in recon + [op]})
                settle(r, const, (tag + " (consolidated)", total), parts + rec_parts)
                notes = []
                if twice:
                    named = []
                    for m, kk, o in twice:           # the uncounted fact never stops the tie, even when it conflicts
                        try:
                            ov = store.get(*o)["value"]
                            named.append(m if ov == store.get(*kk)["value"] else f"{m} (alone {fmt(ov)})")
                        except Conflict:
                            named.append(f"{m} (alone: conflicting values)")
                    notes.append("counted once, as the OperatingSegments fact (also tagged on the segment axis alone): "
                                 + ", ".join(named))
                if subtotals:
                    notes.append("not summed, the reportable segments' aggregation subtotal: " + sub_named)
                if not rec_parts:
                    notes.append("no reconciling items tagged")
                if other:
                    notes.append("not counted, on the filer's own consolidation-item members: " + ", ".join(other))
                r["note"] = "; ".join(notes)
            except Conflict as ex:
                absent(r, str(ex))
            out.append(r)
    return out


def subtotal_name(store: Store, k: tuple, seg_axis: str, ci_axis: str) -> str:
    """A subtotal fact as named in a note: its member (and consolidation item) and value. It is never summed, so a
    conflict on it never stops the tie."""
    d = dict(k[4])
    try:
        v = fmt(store.get(*k)["value"])
    except Conflict:
        v = "(conflicting values)"
    return f"{d[seg_axis]}" + (f" [{ci_axis}={d[ci_axis]}]" if ci_axis in d else "") + f" {v}"


def additive(tag: str, unit: str, const: dict) -> bool:
    rule = const["non_additive_rule"]
    return (tag not in const["non_additive_tags"] and not any(p in tag for p in rule["name_parts"])
            and not any(p in unit for p in rule["unit_parts"]) and unit.lower() not in rule["units"])


def quarters(store: Store, const: dict) -> tuple:
    q0, q1 = const["quarter_days"]
    a0, a1 = const["annual_days"]
    out, underived = [], 0
    series: dict = {}
    for k in store.keys():
        if k[1] is not None and k[4] == () and additive(k[0], k[3], const):
            series.setdefault((k[0], k[3]), []).append(k)
    for (tag, u), ks in sorted(series.items()):
        by_start: dict = {}
        for k in ks:
            by_start.setdefault(k[1], []).append(k)
        for start, group in sorted(by_start.items()):
            group = sorted(group, key=lambda k: k[2])
            for a, b in zip(group, group[1:]):
                if not q0 <= (b[2] - a[2]).days <= q1:
                    continue
                tagged = sorted((k for k in ks if k[2] == b[2] and k[1] != start and q0 <= (k[2] - k[1]).days <= q1),
                                key=lambda k: abs((k[1] - a[2]).days - 1))
                if not tagged:
                    underived += 1
                    continue
                r = row("ytd_quarter", b[2], u, tagged[0][1], tag)
                try:
                    fa, fb, fq = store.get(*a), store.get(*b), store.get(*tagged[0])
                    longer = "FY" if a0 <= (b[2] - b[1]).days <= a1 else f"YTD to {b[2]}"
                    settle(r, const, ("tagged quarter " + tag, fq), [(f"{longer} {tag}", fb, 1), (f"YTD to {a[2]} {tag}", fa, -1)])
                except Conflict as ex:
                    absent(r, str(ex))
                out.append(r)
    return out, underived


def run_all(store: Store, data: dict, const: dict) -> tuple:
    qrows, underived = quarters(store, const)
    rows = (balance(store, data, const) + cash(store, data, const) + income(store, data, const)
            + roll(store, data, const, "retained_earnings") + roll(store, data, const, "equity_roll")
            + segments(store, data, const) + qrows)
    return rows, underived


def key(r: dict) -> tuple:
    return (r["tie"], r["variant"], r["start"], r["end"], r["unit"])


# ── classing a break ──────────────────────────────────────────────────────────────────────────────────────────────────
def filings(r: dict) -> list:
    return sorted({(f["filed"] or dt.date.min, f["accn"]) for f in r["facts"] if f["accn"]})


def show_filings(fs: list) -> str:
    return "; ".join(f"{acc} filed {fd if fd != dt.date.min else '?'}" for fd, acc in fs)


def component(tag: str, tie: str, const: dict):
    """Could a fact of this element be a line the tie is missing? None: the tie is searched for no component at all
    (a difference of one element, or dimensioned parts). The rule reads the element's local name, so a filer's own
    element named like an equity movement is a lead too."""
    rule = const["component_candidates"].get(tie)
    if rule is None:
        return None
    name = tag.split(":", 1)[-1]
    if any(x in name for x in rule.get("exclude", [])):
        return False
    return name in rule.get("elements", []) or any(name.startswith(p) for p in rule.get("prefixes", []))


def show_facts(fs: list) -> str:
    return "; ".join(f"{q(f['tag'])} @ {cid(f)} ({fmt(f['value'])})" for f in fs[:3])


def classify(r: dict, store: Store, data: dict, const: dict, recheck, filed: dict) -> None:
    """Across filings first. A break whose inputs come from several filings is re-checked inside each filing that
    carries the row: it ties in one, cross-filing mix; one filing carries every input and breaks inside itself, the
    class is that filing's own (named). Only a row no single filing carries can be 'cross-filing'."""
    fs = filings(r)
    if len(fs) > 1:
        carriers = store.carriers(r["facts"])
        latest = lambda a: (filed.get(a) or dt.date.min, a)
        for acc in sorted({a for _, a in fs} | carriers, key=latest, reverse=True):
            rr = recheck(acc)[0].get(key(r))
            if rr is not None and rr["status"] == "TIES":
                r["class"] = "cross-filing mix"
                r["hint"] = (f"it ties inside filing {acc} (gap {fmt(rr['gap'])}); the latest-filed values mix filings "
                             f"({show_filings(fs)}), so the break is between filings, not in the filer's statements")
                r["filing"] = acc
                return
        for acc in sorted(carriers, key=latest, reverse=True):
            rows_a, store_a = recheck(acc)
            rr = rows_a.get(key(r))
            if rr is not None and rr["status"] == "BREAK":
                rr = dict(rr)
                classify_one(rr, store_a, data, const, cross=False)
                r["class"], r["filing"] = rr["class"], acc
                r["hint"] = (f"filing {acc} (filed {filed.get(acc) or '?'}) carries every input and breaks inside itself "
                             f"(gap {fmt(rr['gap'])}); the latest-filed values come from {show_filings(fs)}"
                             + (f"; inside that filing: {rr['hint']}" if rr["hint"] else ""))
                return
    classify_one(r, store, data, const, cross=len(fs) > 1)


def classify_one(r: dict, store: Store, data: dict, const: dict, cross: bool) -> None:
    """Give a BREAK one class, in this order: an element that never belongs in the tie equals the gap (not this tie), a
    fact of the same period that the tie could be missing equals it (missing component), sign (an input with the
    opposite sign closes it), scale (an input off by 1,000 closes it, the scaled input still material), an input
    equals the gap (without it the tie holds), cross-filing (inputs from several filings, none carrying all), a fact
    of the same period that is no line of this tie equals it (coincident value, a lead only), else residual. A fact
    'equals' the gap within the tolerance taken on the gap itself, never the tie's larger side."""
    gap = r["gap"]
    mt = tol(const, gap)
    fs = filings(r)
    used = {(f["tag"], cid(f)) for f in r["facts"]}
    search = const["component_candidates"].get(r["tie"]) is not None
    cands = [store.one[k] for k in store.one if search and k[1] == r["start"] and k[2] == r["end"]
             and k[3] == r["unit"] and k[4] == () and (k[0], cid(store.one[k])) not in used]
    near = [f for f in cands if abs(abs(f["value"]) - abs(gap)) <= mt]
    never = {e["element"].split(":", 1)[1]: e.get("why", "") for e in erows(data, r["tie"], "never")}
    bad = [f for f in near if f["tag"] in never]
    if bad:
        f = bad[0]
        r["class"] = "not this tie"
        r["hint"] = (f"the gap equals {q(f['tag'])} @ {cid(f)} ({fmt(f['value'])}), which never belongs in this tie: "
                     f"{never[f['tag']]}")
        return
    terms = [(x, c) for x, c in r["_terms"] if isinstance(x, dict)]
    # a fact equal to an input's own value restates that input (the continuing-operations share beside the share
    # read): it is never a line the tie is missing, and 'input equals gap' below says what it is
    near = [f for f in near if not any(abs(abs(f["value"]) - abs(x["value"])) <= mt for x, _ in terms)]
    comp = [f for f in near if component(f["tag"], r["tie"], const)]
    coincident = [f for f in near if f not in comp]
    if comp:
        unsummed = {local(e["element"]): e.get("why", "") for e in erows(data, r["tie"], "not summed")}
        r["class"] = "missing component"
        r["hint"] = "the gap equals " + show_facts(comp) + ": a line this tie does not read, or one the filer presents " \
                    "elsewhere" + "".join(f" ({q(t)}: {w})" for t, w in unsummed.items() if any(f["tag"] == t for f in comp))
        return
    for x, c in terms:
        if abs(gap - 2 * x["value"] if c == 0 else gap + 2 * c * x["value"]) <= mt:
            r["class"] = "sign"
            r["hint"] = (f"the gap is twice {q(x['tag'])} @ {cid(x)} ({fmt(x['value'])}): it looks tagged with the "
                         f"opposite sign (a fact's sign follows the element's meaning, QF-38)")
            return
    for x, c in terms:
        for k in (SCALE, 1 / SCALE):
            if k < 1 and abs(x["value"]) / SCALE <= mt:
                continue                   # scaled down it is no longer material: that is an input equal to the gap
            g2 = gap + x["value"] * (k - 1) if c == 0 else gap - c * x["value"] * (k - 1)
            if abs(g2) <= mt:
                r["class"] = "scale"
                r["hint"] = (f"{q(x['tag'])} @ {cid(x)} ({fmt(x['value'])}) looks off by a factor of 1,000: "
                             f"scaled, the tie holds")
                return
    alone = [x for x, c in terms if abs(gap - x["value"] if c == 0 else gap + c * x["value"]) <= mt]
    if alone:
        r["class"] = "input equals gap"
        r["hint"] = ("without " + show_facts(alone) + " the tie holds: an input equals the gap (a repeated, mis-dated or "
                     "mis-tagged fact; one tagged 1,000 times too large reads the same at this tolerance)")
        return
    lead = ("; a fact of the period that is no line of this tie also equals the gap (a lead only): "
            + show_facts(coincident)) if coincident else ""
    if cross and len(fs) > 1:
        r["class"] = "cross-filing"
        r["hint"] = (f"the inputs come from different filings ({show_filings(fs)}): a recast or restatement between them "
                     f"can break the tie, and no single filing carries every input, so neither the filing nor this tie "
                     f"is shown at fault (QF-34, QF-35)" + lead)
        return
    if coincident:
        r["class"] = "coincident value"
        r["hint"] = ("the gap equals " + show_facts(coincident) + ", a fact of the period that is no line of this tie: a "
                     "coincident value, a lead only")
        return
    r["class"] = "residual"


# ── output ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def fmt(v) -> str:
    if v is None:
        return "-"
    v = Decimal(v)
    return f"{v:,.0f}" if v == v.to_integral_value() else f"{v:,}"


def show_rows(rows: list, underived: int, const: dict, period, decimals_given: bool, read: dict) -> str:
    n_t = sum(r["status"] == "TIES" for r in rows)
    n_b = sum(r["status"] == "BREAK" for r in rows)
    n_a = sum(r["status"] == "ABSENT" for r in rows)
    lines = [f"ties: {n_t + n_b} checked · {n_t} TIES · {n_b} BREAK · {n_a} absent"
             + (f" · period {period}" if period else "")
             + f"  (tolerance: the larger of {fmt(const['tolerance_abs'])} and {const['tolerance_rel'] * 100:g}% "
               f"of the larger side, or of the movements in a roll-forward)",
             f"read: {read['facts']:,} facts ({read['undim']:,} undimensioned) from {read['filings']:,} filing(s)"
             + (f", {read['first']}..{read['last']}" if read["facts"] else "") + f"; {read['shape']}"]
    if n_b and not decimals_given:
        lines.append("note: no fact carries decimals, so no break here is widened for rounding; a break of rounding size "
                     "needs each fact's decimals (QF-41: decimals is precision)")
    for r in rows:
        span = f"{r['start']}..{r['end']}" if r["start"] else f"{r['end']}"
        head = f"{r['status']:<7} {r['tie']:<17} {span:<22} {r['unit']}"
        if r["status"] == "ABSENT":
            lines.append(f"{head}  {r['note']}")
            continue
        rhs = ""
        for i, (lab, v, c) in enumerate(r["right"]):
            rhs += f" - {lab} {fmt(v)}" if c < 0 else (" + " if i else "") + f"{lab} {fmt(v)}"
        lines.append(f"{head}  {r['left'][0]} {fmt(r['left'][1])} vs {rhs}")
        lines.append(f"{'':<8}gap {fmt(r['gap'])} (tolerance {fmt(r['tolerance'])})"
                     + (f"  class: {r['class']}" if r["class"] else ""))
        lines.append(f"{'':<8}facts: " + "; ".join(f"{q(f['tag'])} @ {cid(f)}" for f in r["facts"]))
        if r["note"]:
            lines.append(f"{'':<8}note: {r['note']}")
        if r["hint"]:
            lines.append(f"{'':<8}hint: {r['hint']}")
    if underived:
        lines.append(f"ytd_quarter: {underived} derived quarter(s) had no directly tagged quarter to compare (not a break)")
    if not read["dims"]:
        lines.append("segment_sum: not checked: no dimensioned fact is among those read"
                     + (" (a companyfacts file carries none: segment sums need the filing's instance or FSDS rows)"
                        if read["shape"] == "companyfacts" else ""))
    return "\n".join(lines)


def jsonable(r: dict) -> dict:
    def c(x):
        if isinstance(x, (Decimal, dt.date)):
            return str(x)
        if isinstance(x, (list, tuple)):
            return [c(y) for y in x]
        return x
    out = {k: c(v) for k, v in r.items() if not k.startswith("_") and k != "facts"}
    out["facts"] = [{"element": q(f["tag"]), "context": cid(f), "value": str(f["value"]), "accn": f["accn"],
                     "filed": str(f["filed"]) if f["filed"] else None} for f in r["facts"]]
    return out


def check(a, data: dict, const: dict) -> int:
    try:
        period = dt.date.fromisoformat(a.period) if a.period else None
    except ValueError:
        print(f"ties: --period {a.period!r} is not YYYY-MM-DD", file=sys.stderr)
        return 2
    try:
        facts, shape = read_facts(a.facts, const)
    except Bad as e:
        print(f"ties: {e}", file=sys.stderr)
        return 2
    store = Store(facts)
    rows, underived = run_all(store, data, const)
    by_accn: dict = {}
    cache: dict = {}

    def recheck(acc: str) -> tuple:
        """Every tie on one filing's facts alone: ({row key: row}, that filing's store)."""
        if acc not in cache:
            if not by_accn:
                for f in facts:
                    by_accn.setdefault(f["accn"], []).append(f)
            st = Store(by_accn.get(acc, []))
            rr, _ = run_all(st, data, const)
            cache[acc] = ({key(x): x for x in rr}, st)
        return cache[acc]

    filed: dict = {}
    for f in facts:
        if f["accn"] and f["filed"] and (f["accn"] not in filed or f["filed"] > filed[f["accn"]]):
            filed[f["accn"]] = f["filed"]
    if period is not None:
        rows = [r for r in rows if r["end"] == period]
    for r in rows:
        if r["status"] == "BREAK":
            classify(r, store, data, const, recheck, filed)
    rows.sort(key=lambda r: (r["end"], ORDER.index(r["tie"]), r["start"] or dt.date.min, r["variant"]))
    rc = 1 if any(r["status"] == "BREAK" for r in rows) else 0 if any(r["status"] == "TIES" for r in rows) else 3
    ends = sorted(f["end"] for f in facts)
    read = {"facts": len(facts), "undim": sum(not f["dims"] for f in facts), "filings": len({f["accn"] for f in facts
            if f["accn"]}), "first": ends[0] if ends else None, "last": ends[-1] if ends else None, "shape": shape,
            "dims": any(f["dims"] for f in facts)}
    dec = any(f["decimals"] is not None for f in facts)
    try:
        if a.json:
            print(json.dumps({"rows": [jsonable(r) for r in rows], "underived_quarters": underived, "decimals_given": dec,
                              "read": {k: str(v) if isinstance(v, dt.date) else v for k, v in read.items()},
                              "tolerance": {"abs": const["tolerance_abs"], "rel": const["tolerance_rel"]}}, indent=1))
        else:
            print(show_rows(rows, underived, const, period, dec, read))
        sys.stdout.flush()
    except BrokenPipeError:          # the reader (| head) stopped reading; the verdict stands
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return rc


def explain(a, data: dict, const: dict) -> int:
    ties = {t["id"]: t for t in data["ties"]}
    if not a.tie:
        for t in data["ties"]:
            print(f"{t['id']:<17} {t['identity']}")
        return 0
    t = ties.get(a.tie)
    if t is None:
        print(f"ties: no tie {a.tie!r}; known: {', '.join(ties)}")
        return 1
    print(f"{t['id']}: {t['identity']}\n  what: {t['what']}\n  period: {t['period']}\n  check: {t['check']}\n  source: {t['source']}")
    c = {r["id"]: r for r in data["constants"]}
    if t["id"] == "ytd_quarter":
        nr = const["non_additive_rule"]
        print(f"  elements: any additive undimensioned element. Never: {', '.join(const['non_additive_tags'])}; no element "
              f"named {' or '.join(nr['name_parts'])}; no unit with {' '.join(nr['unit_parts'])} or {', '.join(nr['units'])}"
              f"\n{'':<6}source: {c['non_additive_tags']['source']}; {c['non_additive_rule']['source']}"
              f"\n  a quarter is {const['quarter_days'][0]}-{const['quarter_days'][1]} days\n{'':<6}source: {c['quarter_days']['source']}")
    else:
        print("  elements, in the order read:")
    for e in (e for e in data["elements"] if t["id"] in e["tie"].split()):
        extra = "".join(f", {k} {e[k]}" for k in ("basis", "group", "sign") if e.get(k) not in (None, ""))
        why = f"\n{'':<6}why: {e['why']}" if e.get("why") else ""
        print(f"    {e['element']}\n{'':<6}{e['role']}{extra}; order {e['order']}; {e['period']}{why}\n{'':<6}source: {e['source']}")
    if t["id"] == "segment_sum":
        print("  axes and members:")
        for m in data["members"]:
            alias = f" (FSDS: {m['alias']})" if m.get("alias") else ""
            print(f"    {m['kind']:<7} {m['role']:<19} {m['name']}{alias}\n{'':<6}source: {m['source']}")
    print("  traps:")
    for tr in data["traps"]:
        if tr["tie"] in (t["id"], "all"):
            print(f"    - {tr['trap']}\n{'':<6}source: {tr['source']}")
    on = "its movements (the sum read, or closing less opening)" if t["id"] in ROLLS else "the larger side"
    print(f"  tolerance: the larger of {fmt(const['tolerance_abs'])} and {const['tolerance_rel']} of {on}\n"
          f"{'':<6}source: {c['tolerance_rel']['source']}")
    cc = const["component_candidates"].get(t["id"])
    print("  a fact equal to a gap is a missing component when it is: " + (
        "never searched (" + c["component_candidates"]["meaning_none"] + ")" if cc is None else
        ", ".join(cc.get("elements", []) + [p + "..." for p in cc.get("prefixes", [])]) or "none (any match is a "
        "coincident value, a lead only)") + f"\n{'':<6}source: {c['component_candidates']['source']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ties.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("facts")
    c.add_argument("--period", help="only ties whose period ends on this date (YYYY-MM-DD)")
    c.add_argument("--json", action="store_true")
    e = sub.add_parser("explain")
    e.add_argument("tie", nargs="?")
    a = ap.parse_args(argv)
    data, const = load()
    return {"check": check, "explain": explain}[a.cmd](a, data, const)


if __name__ == "__main__":
    sys.exit(main())
