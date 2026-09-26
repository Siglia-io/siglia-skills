---
name: siglia-fin-concepts
description: The market-standard reading of plain investor questions, from a sourced register of 297 financial concepts across cash flow, profitability and growth, liquidity and credit, valuation, shareholder returns and dilution, events and red flags, sector measures (banks, REITs, insurers, energy, software) and the qualifiers and figure mechanics that make a number "low" or "strong". For a question like "is apple cashflow low" it gives the concepts meant, the XBRL elements and period rules, the comparison frame the qualifier needs, any line a named source draws or "no market threshold", the pitfalls, and each claim's source with tier and licence. Use before building, reviewing or answering anything that turns an investor's words into a financial concept, figure or threshold, instead of reasoning finance up from memory; and to validate the register itself.
---

# siglia-fin-concepts — how the market reads an investor's question, with sources

**Version 1.5.**

Eight research agents wrote the rows, one per family (04:47Z to 05:24Z on 24 Sep), under a brief whose rules are enforced below. This script only finds and checks them. **A question no row covers reads "not in the register"**: send Research a request, and never reason one up.

## One body of fact with Research

- **The five Case questions have their source of record in Research's doc,** a research note:
  1. is its cash flow low;
  2. is it running out of cash;
  3. can it pay its debts;
  4. is it diluting;
  5. is it raising money.

  Twelve rows carry `record` pointing there (CF-01–03, CF-20, CF-21, LS-06, LS-34, SH-14, SH-15, SH-19, SH-20, RF-14), and the card says Research wins.
- **Everywhere else, this register is primary,** and Research reviews it.
- **`read` prints Research's six rules (§0) above every reading:**
  1. a named comparison;
  2. owner-labelled lines only;
  3. no verdict or forecast;
  4. the period from each fact's own dates;
  5. lenders read not applicable;
  6. an absence is not a finding.

## Steps

```bash
C="scripts/concepts.py"
python3 "$C" read "is apple cashflow low"      # the concepts meant, the qualifier's frame, figures, lines, pitfalls
python3 "$C" find free cash flow               # ranked entries
python3 "$C" show CF-01 LS-34                  # an entry in full: every source, tier, licence, re-read or lead
python3 "$C" list --family LS
python3 "$C" validate                          # the register's rules; exit 1 on any FAIL
python3 "$C" elements                          # every element named, against FASB's 2026 taxonomy (siglia-xbrl-element's cache)
```

The register is `data/*.json`, one file per family: CF, PG, LS, VA, SH, RF, SE and QF.
- It has 297 entries and 1,307 source citations, of which 1,074 were re-read in the run.
- It has 502 quotes, all public-domain government text, each 25 words or fewer and each checked on its page by the agent that took it.
- It has 332 lines. 243 entries say there is no market threshold.

## What `validate` holds

| code | rule | level |
|---|---|---|
| R1 | id, concept, reading, at least 3 plain questions, confidence | FAIL |
| R2 | every source has tier 1 or 2 and a licence (PD, ref, OD); `none` is not usable | FAIL |
| R3 | never a source: FMP, Nasdaq data pages, Stooq, Yahoo, Macrotrends, Moody's, Fitch, FINRA, LSTA, IFRS. sec.gov may be cited by identifier but never marked fetched. investor.gov is never the only source | FAIL |
| R4 | a quote is public-domain text, re-read in the run, 25 words or fewer | FAIL |
| R5 | every line names the source that draws it. A definitional (arithmetic) line with no source is a REVIEW | FAIL / REVIEW |
| R6 | elements are `prefix:Name`. Checked against FASB's cached index: absent or deprecated is a REVIEW, or INFO when the row itself names it as a legacy fallback | REVIEW / INFO |
| R7 | by-reference works (ASC, CFA, S&P, BDC, CFI, WSP, Investopedia, Damodaran, Nareit, NAIC, journals) are never licensed PD. US government pages are exempt | FAIL |
| R8 | a row with no source re-read is a lead | REVIEW |
| R9, R10 | the review field is well formed; a source of record exists on main | FAIL |
| Q1 | §0.1: a qualifier question ("low", "strong", "too much"…) has a named comparison frame | FAIL |
| Q2 | §0.2: an S&P Global Ratings line says it is on S&P-adjusted figures | REVIEW |
| Q4 | §0.4: a row reading a cash-flow element says 10-Q cash flows are year-to-date | REVIEW |
| Q5 | §0.5: runway, current ratio and coverage rows say they are not applicable to lenders | REVIEW |
| Q6 | §0.6: a row reading a filed event says its absence is not a finding | REVIEW |

**At 1.0, with the element index cached: 0 FAIL, 90 REVIEW** (75 without it). The REVIEWs are Research's review list: 38 definitional lines with no source, 18 year-to-date notes, 15 elements, 9 absences, 6 lender notes, 3 S&P lines and 1 lead.

## What it does not do

- **It gives no advice, verdict or forecast.** A reading names concepts, figures, frames and lines, each with its source.
- **It is not product code.** The app must never read the skill folder.
- **It does not fetch.** `siglia-def-check` re-reads a definition, and `siglia-xbrl-element` shows what an element is.
