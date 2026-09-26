#!/usr/bin/env python3
"""siglia-def-check: re-read a financial definition on its primary or authoritative page, and record the re-read.

  ecfr "17 CFR 229.303(b)(1)" --quote "the next 12 months" [--date YYYY-MM-DD]
        the eCFR versioner API (point in time; the default date is the title's own up_to_date_as_of)
  fr "69 FR 15594" --quote "..."        a Federal Register page, through govinfo's link service
  url URL --quote "..." --licence PD|ref   any other page. A by-reference page (ref) is checked and hashed, and its
        text is neither printed nor recorded
  add --record FILE to append the re-read as one JSON line (a file you name; nothing else is written)

Every re-read prints one line a document can carry: what was read, the version or as-of date, the clock time, the
page's sha256 and size, and whether the quote was found, with its context for public-domain text. Matching ignores
case, whitespace, curly quotes and dash styles. Refused, never fetched: any sec.gov host (the SEC request budget is the
estate's), asc.fasb.org (the FAF terms bar scripted access), moodys.com and fitchratings.com (Research §1).
Exit: 0 found · 1 read, quote NOT found (a finding) · 2 cannot fetch, a bot page, or a bad citation · 4 refused host
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys

UA = "Siglia definition check (research; contact via siglia.io)"
REFUSE = [(r"(^|\.)sec\.gov$", "sec.gov: the SEC request budget is reserved for the estate's hosts"),
          (r"(^|\.)asc\.fasb\.org$", "asc.fasb.org: the FAF terms bar scripted access; cite ASC by paragraph"),
          (r"(^|\.)moodys\.com$", "moodys.com: DO NOT USE (Research §1)"),
          (r"(^|\.)fitchratings\.com$", "fitchratings.com: DO NOT USE (Research §1)")]
TRAILER = b"\n__SIGLIA_DEFCHECK__"


class Stop(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/:?#]+)", url)
    return (m.group(1) if m else "").lower()


def refuse(url: str) -> None:
    h = host_of(url)
    for rx, why in REFUSE:
        if re.search(rx, h):
            raise Stop(4, f"REFUSED {url}: {why}")


def get(url: str) -> tuple[int, str, str, bytes]:
    """(http status, final url, content type, body), through curl: the proxy is kinder to it than to urllib."""
    refuse(url)
    curl = os.environ.get("SIGLIA_DEFCHECK_CURL", "curl")
    r = subprocess.run([curl, "-sS", "-L", "--max-redirs", "5", "--compressed", "--max-time", "120", "-A", UA,
                        "-o", "-", "-w", TRAILER.decode() + "%{http_code} %{url_effective} %{content_type}", url],
                       capture_output=True)
    body, sep, tail = r.stdout.rpartition(TRAILER)
    if r.returncode != 0 or not sep:
        raise Stop(2, f"could not fetch {url} (curl exit {r.returncode}: {r.stderr.decode(errors='replace').strip()[:200]})")
    parts = tail.decode(errors="replace").split(" ", 2) + ["", ""]
    code, final, ctype = int(parts[0] or 0), parts[1], parts[2]
    refuse(final)   # a redirect may not carry the request somewhere refused
    return code, final, ctype, body


def text_of(body: bytes) -> str:
    s = body.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


def norm(s: str) -> str:
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s).replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()   # case kept for display; matching lowers both sides


def check(kind: str, citation: str, url: str, quote: str, licence: str, as_of: str | None, a) -> int:
    code, final, ctype, body = get(url)
    if code != 200:
        raise Stop(2, f"{citation}: {url} answered HTTP {code}")
    if kind == "ecfr" and (b"<html" in body[:2000].lower() or "html" in ctype.lower()):
        raise Stop(2, f"{citation}: eCFR answered a web page, not the XML (a bot page?); nothing was re-read")
    if kind != "ecfr" and re.search(rb"(?i)unblock|captcha|are you a robot|access denied", body[:4000]):
        raise Stop(2, f"{citation}: {final} looks like a bot or block page; nothing was re-read")
    shown = norm(text_of(body))
    t, q = shown.lower(), norm(quote).lower()   # lower() keeps offsets for the text shown
    at = t.find(q) if q else -1
    sha = hashlib.sha256(body).hexdigest()
    when = now()
    ctx = ""
    if at >= 0 and licence == "PD":
        ctx = shown[max(0, at - 140): at + len(q) + 140]
    rec = {"kind": kind, "citation": citation, "url": url, "final_url": final, "as_of": as_of, "re_read_at": when,
           "sha256": sha, "bytes": len(body), "licence": licence, "quote": quote if licence == "PD" else "",
           "found": at >= 0, "offset": at if at >= 0 else None, "context": ctx}
    head = (f"RE-READ {citation} · {final or url}" + (f" · as of {as_of}" if as_of else "") +
            f" · {when} · sha256 {sha[:16]} · {len(body)} bytes · {licence}")
    if at >= 0:
        print(head + " · quote FOUND")
        if ctx:
            print(f'  …{ctx}…')
        else:
            print("  (by reference: the page's text is not printed or recorded)")
    else:
        print(head + " · quote NOT FOUND on the page as read (the definition moved, changed, or was never there)")
    if a.record:
        with open(a.record, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"  recorded: {a.record}")
    return 0 if at >= 0 else 1


def cmd_ecfr(a) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*C\.?F\.?R\.?\s*(?:§\s*)?(\d+\.\d+[a-z]?(?:-\d+)?)\s*((?:\([0-9a-zA-Z]+\))*)\s*", a.citation)
    if not m:
        raise Stop(2, f"not a CFR citation: {a.citation!r} (want e.g. '17 CFR 229.303(b)(1)')")
    title, section, para = m.group(1), m.group(2), m.group(3)
    date = a.date
    if not date:
        code, _, _, body = get("https://www.ecfr.gov/api/versioner/v1/titles.json")
        try:
            ts = {str(t["number"]): t for t in json.loads(body)["titles"]}
            date = ts[title]["up_to_date_as_of"]
        except (ValueError, KeyError) as e:
            raise Stop(2, f"cannot read eCFR's titles.json for title {title}: {e}")
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", date or ""):
        raise Stop(2, f"bad date {date!r}")
    url = f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?section={section}"
    return check("ecfr", f"{title} CFR {section}{para}", url, a.quote, "PD", date, a)


def cmd_fr(a) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*F\.?R\.?\s*(\d+)\s*", a.citation)
    if not m:
        raise Stop(2, f"not a Federal Register citation: {a.citation!r} (want e.g. '69 FR 15594')")
    url = f"https://www.govinfo.gov/link/fr/{m.group(1)}/{m.group(2)}?link-type=html"
    return check("fr", f"{m.group(1)} FR {m.group(2)}", url, a.quote, "PD", None, a)


def cmd_url(a) -> int:
    if not re.match(r"https?://", a.url):
        raise Stop(2, f"not a URL: {a.url!r}")
    return check("url", a.url, a.url, a.quote, a.licence, None, a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="defcheck.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    for name, arg in (("ecfr", "citation"), ("fr", "citation"), ("url", "url")):
        sp = s.add_parser(name)
        sp.add_argument(arg)
        sp.add_argument("--quote", required=True, help="the words the definition must contain")
        sp.add_argument("--record", help="append the re-read as one JSON line to this file")
        if name == "ecfr":
            sp.add_argument("--date", help="YYYY-MM-DD (default: eCFR's up_to_date_as_of for the title)")
        if name == "url":
            sp.add_argument("--licence", required=True, choices=("PD", "ref"),
                            help="PD: public domain (context printed and recorded); ref: by reference (hash only)")
    a = p.parse_args(argv)
    try:
        return {"ecfr": cmd_ecfr, "fr": cmd_fr, "url": cmd_url}[a.cmd](a)
    except Stop as e:
        print(f"defcheck.py: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
