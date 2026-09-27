---
name: siglia-period-math
description: Fiscal-period arithmetic from a fact's own dates - the fiscal label (Q1-Q4, FY) of a period end for any year-end (January year-ends named two ways, 52/53-week years, a late-December year ending in January; a duration outside every band named neutrally, never FY, and a transition period only from a transition report), discrete quarters from 10-Q year-to-date facts (Q2 = 6M - 3M, Q3 = 9M - 6M, Q4 = FY - 9M) with their inputs and checks, a claim's period label checked against a fact's dates (MATCH or MISMATCH with the right label), a direction word checked against both periods (a loss narrowed or widened), and a lookback window's first day. Use before writing, reviewing or grading a quarter or FY label, a YTD derivation, a TTM, an increased/decreased claim or a date window, and when a label looks one year or one quarter off.
---

# siglia-period-math — period labels, YTD arithmetic and direction words from the dates

**Version 1.2.**

**Why.** The same period mistakes recur whenever filings are read by hand or by a model:
- **Wrong quarters.** Of 5,139 model-written claims that named a quarter with a year, 1,194 contradicted the record they cited (a Siglia measurement). 237 of 1,210 citations over duration facts named a period that was not the fact's own.
- **Wrong years.** A year-end from 1 Jan to 7 Feb is named two ways: 200 of 397 such SEC filers name it one year below the end-year rule, 60 by it, and the rest split. A 52/53-week year recorded at a late-December date can end in January.
- **YTD read as the quarter.** 10-Q cash flows are required year to date, with no quarter-only statement (17 CFR 210.10-01(c)(3); 8-03 for smaller reporting companies). No 10-Q is filed for Q4 (17 CFR 240.13a-13(a)), and since 2021 a 10-K usually carries no quarterly data (Item 302(a) as amended), so Q4 exists only inside the fiscal-year fact for revenue in 65 of 74 fiscal years and for operating cash flow in 74 of 74.
- **Stubs read as years.** A 354-day predecessor stub sits inside a loose 350-380 day window and reads as a fiscal year there. A year is 52 or 53 weeks.
- **Direction words on one period.** "Gross profit increased" citing only the latest period, when $8.29m became $7.94m; "operating income improved" on a loss that widened.

`data/periods.json` holds the rules as 86 sourced rows: CFR sections (S-X 10-01, 8-03, 3-06, S-K 302, Exchange Act rules 13a-10 and 13a-13, and 26 CFR 1.441-2 read by analogy), Federal Register releases (33-10890; the proposed Form 10-S), issuers' and regulators' own pages (Apple's results releases; the Call Report and FR Y-9C instructions), siglia-fin-concepts' QF rows, Research's rulings, the Corpus pack's counts, and this tool's own conventions, each named as such. `validate` holds the rows' shape and recomputes every worked example.

## Steps

From this skill's folder, with any Python 3.9 or later:

```bash
PY=python3
"$PY" scripts/period.py label --fye 01-26 --end 2025-04-27 --offset 0        # Q1 FY2026 (Nvidia); no --offset in 01-01..02-07 prints FY?
"$PY" scripts/period.py label --fye 09-26 --start 2022-09-25 --end 2023-09-30 --weeks52   # FY2023, a 53-week year
"$PY" scripts/period.py label --fye 12-30 --end 2026-01-02                   # Q4 FY2025: closes on the December before
"$PY" scripts/period.py label --fye 12-21 --start 2023-01-01 --end 2023-12-21    # unbanded duration ... (354 days): never FY2023
"$PY" scripts/period.py label --fye 11-30 --start 2024-07-01 --end 2024-11-30 --transition-report   # a 10-KT's transition period
"$PY" scripts/period.py quarterize facts.json --fye 12-31                    # [{start,end,value}] YTD facts -> quarters + TTM
"$PY" scripts/period.py quarterize facts.json --fye 09-01 --weeks52          # a 12/12/12/16-week year: 36-week stub, 16-week Q4
"$PY" scripts/period.py quarterize call.json --fye 12-31                     # Call Report RI/RI-B, FR Y-9C HI: calendar YTD
"$PY" scripts/period.py check-label 'Q3 FY2025' --fye 12-31 --start 2025-01-01 --end 2025-09-30   # MISMATCH: a 9M YTD stub
"$PY" scripts/period.py compare --cur 2025-04-01 2025-06-30 7.94 --prior 2024-04-01 2024-06-30 8.29 --word increased  # MISMATCH
"$PY" scripts/period.py window --days 1095 --today 2026-09-24 2010-12-31 2024-01-15   # OUTSIDE / inside
"$PY" scripts/period.py validate                                             # every row sourced, every example recomputed
"$PY" scripts/period.py show YTD cash                                        # reference rows holding every word
```

- **`label`** prints the label on its first line and the reasons below it. With `--start` it names a quarter, a year, a `YTD to Q3 FY2025` stub, a 10-Q's cumulative twelve months (`twelve months to Q2 FY2025`), an `unbanded duration START–END (N days)`, or, with `--transition-report`, a `transition period START–END`.
- **A year is 52 or 53 weeks**: 363-370 days end - start (Research, X1). A duration outside every band is never FYyyyy. By its dates alone it may be a first period from inception, a predecessor or successor period, or a transition period (which can sit in an ordinary 10-K or 10-Q, 17 CFR 240.13a-10(d)), so it is labelled `unbanded duration START–END (N days)`. It is a `transition period` only with the transition-report signal (`--transition-report`: form 10-KT or 10-QT, or `dei:DocumentTransitionReport` true), and only when it covers less than 12 months: a transition report never covers 12 or more months (17 CFR 240.13a-10(a)). A banded duration keeps its band whatever the report. 3-06(a) lets a 9-12 month period satisfy a one-year filing requirement only where the issuer changed its fiscal year, where the statements are those required for a significant acquired business (3-05, 3-14, 8-04, 8-06) and pertain to that business, or where the Commission permits it; never for a registered investment company. That is a filing rule, and this tool still never names such a period FYyyyy.
- **The January window.** For a year-end from 01-01 to 02-07, pass `--offset 0` (named by the year it ends in) or `-1` (named by the calendar year it mostly covers). Take it from the issuer's recent 10-K `DocumentFiscalYearFocus`. Without it the year prints `FY?` with both candidates; print the quarter alone. Outside the window the tool assumes the end-year rule (offset 0); `--offset -1` there is used as given, with a warning.
- **The year-end that closes a period** is the first one on or after its end less 45 days, looking back into the previous calendar year. So a 52/53-week year recorded at 12-30 that ends on 2026-01-02 is Q4 FY2025 and FY2025.
- **`--weeks52`** names the end's weekday and counts the duration in whole weeks. It also reads what the day bands miss in a 52/53-week year: a whole 12-17 weeks is a quarter, and 24-29 or 36-41 weeks a year-to-date stub. So a 12/12/12/16-week year's 36-week stub (251 days) is `YTD to Q3`, and its 16-week Q4 (111 days) is a quarter. Without the flag, a whole-week duration the day bands leave unbanded is flagged with the reading the flag would give. Which calendar a filer keeps is yours to give, like the offset.
- **`quarterize`** reads a JSON list of `{start, end, value}` (optional `id`, and `"transition_report": true` or `"form": "10-KT"`/`"10-QT"` for the transition-report signal), from a file or `-` for stdin, and prints each quarter with its derivation. It differences only quarters, year-to-date stubs and years. It FAILS on each of these:
  - a reported quarter its derivation contradicts (`--tol` for rounding in thousands);
  - four reported quarters that do not sum to the year;
  - a derived quarter outside 75-105 days (with `--weeks52`, a whole 12-17 weeks passes);
  - a fact it cannot place: an unbanded duration or a transition period (whatever it shares a start with), a lone YTD (a semiannual filer's six-month fact, say), an instant, or a non-additive YTD with `--non-additive` (EPS and weighted-average shares are never differenced or summed).
- **`check-label`** reads `Q1 FY2025`, `FY2025 Q3`, `1Q25`, `third quarter of fiscal 2025`, `calendar Q1 2025`, plus `Q3`, `FY2025` and `YTD to Q3 FY2025`. A bare `Q1 2025` is fiscal; only `calendar Q1 2025` is a calendar quarter.
- **`compare`** takes both periods (`START END VALUE` each; `-` as START for a balance) and prints the direction: `increased`, `decreased`, `unchanged`, a loss that `narrowed` or `widened` (to zero: break-even, not a profit), or a sign change that `turned`. With `--word` it checks the claim's word. With no `--prior` it answers "could not establish": a direction word needs both periods (Research, X2). It FAILS (exit 1) a comparison that is not like for like (a quarter against a YTD stub, a year or YTD stub sharing the quarter's end, or an unbanded duration), an overlap, a judgement word (`improved`) and, for a loss, `increased`/`decreased`. It gives no percent on a negative or zero base, and names a 53-week year or a 14/16/17-week quarter in either leg.
- **`window`** prints which dates fall on or after today less `--days` (the first day is inside).

**Exit codes:** 0 labelled, MATCH, all placed and passed, comparable, inside, valid, found · 1 no fiscal quarter, MISMATCH, a check failed or a fact unplaced, could not establish or not comparable, outside, invalid, nothing found · 2 unreadable input.

## Limits

- **Not computed:** the exact year-end date of a 52/53-week year. The pattern is sourced: 26 CFR 1.441-2(a), a tax rule read here by analogy for reporting calendars (and QF-31), says the year varies from 52 to 53 weeks and ends on the same weekday, the last of the month or the one nearest month-end. A last-weekday year ends up to six days before month-end, and a nearest-weekday year up to three days either side of it, never more than three days into the next month. Computing the date still needs the filer's weekday and which of the two it uses, and neither is recorded.
- **The naming window's bounds are Siglia's convention, not a rule or a measurement.** 1 Jan to 7 Feb, and the 5 most recent 10-Ks the offset is read over, are the design of Siglia's naming-offset rule (23 Sep 2026). The measurement over SEC 10-K DEI facts (200 filers at -1, 60 at 0, 137 split) was taken over the filers inside the window afterwards, so it did not set the bounds. No rule says how a year ending just outside them is named: there this tool assumes the end-year rule (offset 0), which nobody measured, and uses an `--offset -1` it is given, with a warning.
- **Unbanded durations are named, not settled.** By its dates alone the tool cannot tell a first period from inception, a predecessor or successor stub and a transition period apart, so it names none of them. Whether a year-long predecessor or successor stub is read as the year is an open question for Research (Corpus pack); this tool never names one FYyyyy.
- **The transition-report signal is yours to give, and it names only unbanded durations.** A transition period reported inside an ordinary 10-K or 10-Q (13a-10(d)) carries no signal and reads `unbanded duration`. A transition period that happens to fall in a band (a three-month transition on a 10-QT) reads as its band, with a note.
- **The day bands are conventions around observed lengths.** Research's X1 fixes the year at 52 or 53 weeks and says to band a duration; the quarter and year-to-date bands (75-105, 165-195, 255-290 days) are this tool's, set around the lengths the Corpus pack observed. So are the year-long span that earns a stub its note (330-400 days) and the gap that makes a comparison year over year (350-380 days).
- **Which filer keeps which week calendar is not recorded.** `--weeks52` is yours to give. With it, a real transition period that happens to be a whole 12-17, 24-29 or 36-41 weeks would be misread as a quarter or a stub.
- **Bank income is calendar year-to-date.** Call Report Schedules RI and RI-B and FR Y-9C Schedule HI run from 1 January whatever the fiscal year, so quarterize them with `--fye 12-31`. A bank that began operating in the year reports from its start, and push-down accounting from the acquisition date: those first stubs are lone year-to-date stubs.
- **The offset is yours to give.** The tool reads no filing, so it cannot settle a January year itself.
- **TTM here is the four-quarter sum.** QF-26's FY + YTD - prior YTD (both YTDs from one filing) agrees unless a later filing restated the year; the Corpus pack's recompute matched 658 of 672 cells, and the 14 that differ mix vintages. A vintage mix is not detected: give facts from one vintage.
- **Sign changes and judgement words** (`turned`; `improved` on a positive figure) follow this tool's convention; only the loss words and "unchanged" are Research's ruling.
- **One label or one comparison at a time.** Which number a label belongs to in a sentence, and which prior-period fact is the same concept, are the caller's to establish.
- **Older 10-Ks may carry Q4.** Before Item 302(a) was amended (Release 33-10890, 86 FR 2080: mandatory for the first fiscal year ending on or after 9 Aug 2021), a 10-K of a 12(b) or 12(g) registrant other than a foreign private issuer or a smaller reporting company gave selected quarterly data for each quarter of two years, Q4 included. The tool does not read that table: pass a reported Q4 as a quarter, and it is checked against FY - 9M.
- **Semiannual reporting is proposed, not adopted.** The SEC's proposed Form 10-S (91 FR 24968, 7 May 2026; no final rule found by 26 Sep 2026) would give a filer a six-month interim period and no Q1 or Q3 10-Q. Its six-month fact is then a lone year-to-date stub, which quarterize leaves unplaced; no quarter is derived.
- **Left out as unsourced here:** ASC 270 and ASC 260-10-55-12 (no local text).
