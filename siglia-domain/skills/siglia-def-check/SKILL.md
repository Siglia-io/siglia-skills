---
name: siglia-def-check
description: Re-read a financial definition on its primary or authoritative page and record the re-read, in one call - a CFR section through the eCFR versioner API (point in time), a Federal Register citation through govinfo's link service, or any other page by URL. Reports whether the quoted words are really there (ignoring case, whitespace, curly quotes and dashes), with the page's sha256, size, as-of date and the clock time, and appends a JSON record on request. Refuses sec.gov, asc.fasb.org, moodys.com and fitchratings.com. By-reference pages are checked and hashed without keeping their text. Use before a definition, threshold or quote from a regulation or source goes into a vocabulary, a register row, a research doc or a product label, and whenever a citation must be marked "re-read" rather than "lead".
---

# siglia-def-check — a definition, re-read on its own page

**Version 1.0.**

**Why it exists.** Research's own docs mark each claim **re-read** or **(agent)**, and only a re-read counts. The Case vocabulary's own errors came from definitions nobody re-read:
- **69 FR 15594:** a skeptic corrected a wrong Federal Register citation.

This makes the re-read one command with a record, instead of a hand fetch nobody can check afterwards.

## Steps

```bash
D="scripts/defcheck.py"
python3 "$D" ecfr "17 CFR 229.303(b)(1)" --quote "the next 12 months"
python3 "$D" ecfr "12 CFR 324.403" --quote "well capitalized" --date 2026-09-01
python3 "$D" fr "69 FR 15594" --quote "triggering event"
python3 "$D" url "https://www.bdc.ca/en/articles-tools/entrepreneur-toolkit/templates-business-guides/glossary/cash-runway" \
    --quote "burn rate" --licence ref
... --record <date>-rereads.jsonl     # append the re-read as one JSON line
```

- **The sandbox:** pass the host in `allowed_domains` (`www.ecfr.gov`, `www.govinfo.gov`, or the page's host).
- **Exit codes:**
  - `0` the quote is found;
  - `1` the page was read and the quote is **not** there (a finding: the definition moved, changed or never said that);
  - `2` the fetch failed, a bot or block page came back, or the citation is bad;
  - `4` a refused host.

**What one re-read prints:**
```
RE-READ 17 CFR 229.303(b)(1) · https://www.ecfr.gov/api/versioner/v1/full/2026-09-22/title-17.xml?section=229.303 ·
  as of 2026-09-22 · 2026-09-24T05:06:26Z · sha256 … · 16735 bytes · PD · quote FOUND
  …its plans for cash in the short-term ( i.e., the next 12 months from the most recent fiscal period end …
```
The time is the clock's at the fetch, never typed. The as-of date is eCFR's own `up_to_date_as_of` for the title, unless `--date` names another.

## The rules it keeps

- **Never fetched:**
  - **any sec.gov host**, because the SEC request budget is the estate's;
  - **asc.fasb.org**, because the FAF terms bar scripted access, so ASC is cited by paragraph;
  - **moodys.com** and **fitchratings.com** (Research §1).

  The same check runs on the page a redirect lands on (F7). SEC forms and releases are re-read through their public-domain copies: eCFR for the rules, govinfo for the Federal Register.
- **By-reference pages** (CFA, S&P, BDC, CFI and the like; `--licence ref`) are fetched to confirm the words are there and to hash the page. Their text is never printed or recorded (Research §1: cite by reference only).
- **Public-domain text** (CFR, the Federal Register) prints about 140 characters of context either side, and records it.
- **A bot page is not a re-read:**
  - eCFR must answer XML;
  - any page saying unblock, captcha or access denied is refused;
  - an HTTP error is refused;

  each exits 2, with nothing recorded as read.

## Real re-reads (24 Sep 2026)

| citation | quote | result |
|---|---|---|
| 17 CFR 229.303(b)(1), eCFR as of 2026-09-22 | "the next 12 months" | FOUND, 05:06:26Z, sha256 … |
| 17 CFR 230.415 | Research's re-read of the ATM definition, "an offering of equity securities into an existing trading market for outstanding shares of the same class at other than a fixed price" | FOUND, 05:06:31Z, sha256 … |
| 69 FR 15594, govinfo → FR-2004-03-25 04-6332 | "triggering event" | FOUND, 05:06:31Z, sha256 … |
| 17 CFR 210.4-08(c) | "any breach of covenant" | FOUND, 05:06:58Z |
| www.sec.gov/…/form8-k.pdf | — | REFUSED (4) |

## What it does not do

- **It does not judge whether a definition supports a mapping.** That is Research's; this proves the words are on the page, at that version, at that time.
- **It does not parse PDFs.** A PDF page's text is not extracted, and a quote in one reads NOT FOUND. Use the public-domain HTML or XML copy (eCFR, govinfo HTML).
- **eCFR's `section=` returns the whole section.** A paragraph citation such as `(b)(1)` is kept in the record's label, but the match is section-wide.
