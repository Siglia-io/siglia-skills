---
name: siglia-statement-ties
description: Check that a filer's statements tie on its held XBRL facts (a companyfacts file, or fact rows) before trusting or citing a figure derived from them - the balance sheet (with temporary equity and noncontrolling interest), the cash roll (CFO + CFI + CFF + FX = the change in cash, cash equivalents and restricted cash), ProfitLoss = NetIncomeLoss + the noncontrolling share, the retained-earnings and equity roll-forwards (stock and PIK dividends leave total equity alone), segment sums, and a 10-Q's year-to-date durations against the tagged quarter (Q4 = FY less nine months). Prints TIES, BREAK (the gap, each fact's element and context id, and a class such as sign, scale, missing component, cross-filing or residual) or ABSENT (what is missing, bounded to the facts read). Use before citing a derived quarter, a Q4, a change in cash or in equity, when a figure looks off, when a filer may have recast, and in place of a spreadsheet three-statement-model check.
---

# siglia-statement-ties - do the statements tie on the facts actually held

**Version 2.2.**

**Why.** It replaces the finance plugin's 3-statement-model check. That spec assumes a spreadsheet model with every line to hand. A second reader ran it on held filings and found it did not hold. The Corpus pack (next6_packs_clean.json, statement-ties), with its verify pass's corrected counts, measured on 25 filers:
- **The balance totals tie exactly on 296 of 297 dates.** The one failure is a cross-filing mix: a later filing re-reported Assets, and the tie holds inside the earlier filing.
- **The balance parts need temporary equity and the noncontrolling interest.** Leaving either out broke dates that otherwise tie.
- **50 dates carry no Liabilities total.** The check there is an absence, not a pass.
- **Adding CommitmentsAndContingencies broke 4 balance sheets that otherwise tie.** The element is a caption.
- **86 of 87 cash-section failures came from one FX element,** the one that includes disposal groups and discontinued operations.
- **Companyfacts has no dimensions.** So a segment sum can never be run on it.

**Measured, 26 Sep 2026, this version.** The facts are the held facts of the same 25 filers: every filing's rows, us-gaap only, from a local snapshot of 16 Sep.

| tie | TIES | BREAK | ABSENT | breaks by class |
|---|---|---|---|---|
| `balance_totals` | 296 | 1 | 0 | 1 cross-filing mix |
| `balance_parts` | 239 | 8 | 50 | 4 cross-filing mix, 4 residual (each inside one filing) |
| `cash_roll` | 257 | 0 | 58 |  |
| `cash_sections` | 299 | 1 | 15 | 1 cross-filing mix |
| `net_income` | 88: 55 with no noncontrolling share tagged, 33 with it | 10 | 217: 200 one fact for both statements | 7 coincident value, 1 input equals gap, 1 sign, 1 residual |
| `retained_earnings` | 262 | 95 | 81 | 43 residual, 28 cross-filing, 20 missing component, 2 cross-filing mix, 1 input equals gap, 1 not this tie |
| `equity_roll` | 115 | 229 | 94 | 146 residual, 29 cross-filing, 26 missing component, 15 coincident value, 7 cross-filing mix, 3 input equals gap, 3 sign |
| `segment_sum` | 0 | 0 | 0 | companyfacts carries no dimensions |
| `ytd_quarter` | 3,737 | 184 | 0 | 147 cross-filing, 22 input equals gap, 15 sign |

194 breaks were classed inside the one filing that carries every input: 132 equity, 54 retained earnings, 4 net income and 4 balance parts.

**What moved from 2.0:**
- **Retained earnings and equity.** 84 roll-forward TIES are now BREAKs: 13 retained earnings and 71 equity. On the balance tolerance they passed. Each gap is 0.5% to 150% of the movements read, and the smallest is 8,404. 19 of them were over 5% of the movements.
- **ABSENT rows.** 40 roll ABSENT rows are new: 10 retained earnings and 30 equity. They include every duration of the 2 filers that tag equity only as the total including the noncontrolling interest.
- **ytd_quarter.** 23 of 2.0's missing components there are now cross-filing, because that tie is no longer searched for components.

**What the breaks were:**
- **net_income.**
  - Six breaks at one filer equal, to the dollar, its distributions to noncontrolling holders. Its noncontrolling share of income is not tagged, and a distribution is not that share, so they read coincident value, a lead only.
  - One filer tagged ProfitLoss +653,110 and NetIncomeLoss -653,110 for the same quarter: sign.
  - One filer tagged ProfitLoss equal to NetIncomeLoss beside a noncontrolling share: input equals gap.
- **retained_earnings.** The 20 missing components:
  - 11 name `PreferredStockDividendsIncomeStatementImpact`, preferred dividends not tagged as a dividend;
  - 4 name `PaymentsOfDividends`, dividends paid where the declared amount is untagged;
  - 3 name `DividendsPreferredStockStock`, a preferred dividend settled in stock beside a cash-only dividends element.
- **The roll-forwards read only the equity statement's total column.** In a quarterly roll, the opening balance comes from the previous filing.
- **Lines on members are not in companyfacts.** A large filer charges part of its buybacks to retained earnings on a retained-earnings member, and those lines never reach companyfacts. So an equity or retained-earnings BREAK is a lead to read the equity statement, not a finding.
- **ytd_quarter.**
  - 147 of the 184 breaks are cross-filing: the inputs come from different filings and no filing carries all three.
  - In 21 of the 22 input-equals-gap breaks, two of the three durations carry one value. The tagged quarter equals the longer year to date (10), the two years to date are equal (3), or all three are (8).

**2.0's three fixes, re-measured.**
- **Dividends declared as `DividendsCash` are read.** Without it, 28 retained-earnings ties break, each gap equal to it.
- **The combined APIC element for share-based compensation and option exercises is read.** 13 equity rows on 2 filers read it. 1 tie depends on it now; on 2.0's balance tolerance, 12 did, and none of those gaps equalled it.
- **The three repurchase elements are one group.** One filer tagged `StockRepurchasedDuringPeriodValue` and `StockRepurchasedAndRetiredDuringPeriodValue` with the same value for one repurchase.

## Steps

```bash
T=scripts/ties.py                             # relative to this skill's folder
python3 "$T" check CIK0000320193.json         # a whole companyfacts file: every applicable tie
python3 "$T" check FACTS.json --period 2025-06-30   # only ties whose period ends that day
python3 "$T" check FACTS.json --json          # the same rows as JSON, each fact with its element and context id
python3 "$T" explain                          # the nine ties, one line each
python3 "$T" explain retained_earnings        # one tie: identity, elements, traps, tolerance, candidates, sources
```

**FACTS.json** is one of three things:
- a whole companyfacts file (`{"facts": {"us-gaap": {tag: {"units": {unit: [rows]}}}}}`), where each row takes its tag and unit from its parent keys;
- a list of facts;
- `{"facts": [...]}`.

A fact carries `tag`, `start` (absent for an instant), `end`, `value` (or `val`, `value_numeric`) and `unit`. Optionally it carries `context` (its contextRef), `dims` or an FSDS `segments` string, `decimals`, `filed` and `accn`.
- **Repeated facts.** The latest `filed` wins. Two values with no filed date are ABSENT, never guessed.
- **A bare companyfacts row** (no tag, no unit) exits 2 and says why.

**The output.** Each row is one of three kinds:
- `TIES`: left, then each input with its sign, the gap within the tolerance.
- `BREAK`: the same, plus `facts:` (each input as `element @ context id`) and a `class:`. When the class was taken inside one filing, the hint names it, and `--json` gives it as `filing`.
- `ABSENT`: `could not establish...`, stated against the facts read. It says "not among the facts read", never that the filer does not report the line.

A companyfacts row has no contextRef, so its context id is `accession|start--end` (or `accession|end` for an instant), plus any `[Axis=Member]`. A header line says what was read: facts, filings, the date range and the shape.

**The classes of a BREAK.** First, across filings. A break whose inputs come from several filings is re-checked inside each filing that carries the row:

| class | meaning |
|---|---|
| cross-filing mix | the tie holds inside one filing: the break is between filings, never the filer's error |
| (that filing's class) | one filing carries every input and breaks inside itself: the class below, taken on that filing's facts, with the filing named |

Then, in this order, on the row (or on the one filing that carries it):

| class | meaning |
|---|---|
| not this tie | a fact equal to the gap never belongs here (share-based compensation in retained earnings). Look elsewhere. Since 2.2 a gap equal to CommitmentsAndContingencies is a missing component, as FASB's calculation sums it |
| missing component | a fact of the period equal to the gap is a line this tie could be missing (`component_candidates`, up to three named) |
| sign | one input with the opposite sign closes the tie |
| scale | one input off by 1,000 closes the tie, and the scaled input still exceeds the tolerance |
| input equals gap | without one input the tie holds: a repeated, mis-dated or mis-tagged fact |
| cross-filing | the inputs come from several filings and no single filing carries them all (for example a recast between two 10-Qs) |
| coincident value | a fact of the period equals the gap but is no line of this tie: a lead only |
| residual | none of the above |

**Two rules for the matching.**
- **What "equals" means.** A fact "equals" the gap within the tolerance taken on the gap itself, never the tie's larger side.
- **Restatements are not components.** A fact equal to an input's own value restates that input, so it is never a missing component.

**What each tie can be missing** (`component_candidates` in `data/ties.json`, by the element's local name):
- **the roll-forwards:** the equity statement's movement families and the net income measures, with the cash counterparts of dividends, repurchases, issuance, exercises and withholding;
- **net_income:** the noncontrolling share elements;
- **balance_parts:** the liability, temporary-equity and equity captions;
- **cash:** the cash balances, section totals, discontinued-operations cash flows and FX;
- **balance_totals:** nothing;
- **ytd_quarter and segment_sum:** never searched. The first differences one element; the second sums dimensioned parts.

**The nine ties** (`explain` prints each with its sources):

| tie | identity | reads |
|---|---|---|
| `balance_totals` | Assets = LiabilitiesAndStockholdersEquity | S-X 5-02 captions 18 and 32 |
| `balance_parts` | Assets = Liabilities + temporary equity + equity incl. NCI (CommitmentsAndContingencies named, not summed) | 5-02 captions 19-32; LS-10; ASC 480-10-S99 by reference; FASB 2026 balance-sheet calculation |
| `cash_roll` | opening + net change (+ FX when excluded) = closing, one basis, the restricted-cash total first | ASC 230 by reference (CF-30); S-X 10-01(c)(3), 8-03 |
| `cash_sections` | CFO + CFI + CFF + FX = the change in cash, cash equivalents and restricted cash | CF-30; the FX element including disposal groups |
| `net_income` | ProfitLoss (the cash flow's opening line) = NetIncomeLoss + the noncontrolling share, over the cash-flow duration; one fact for both is ABSENT | ASC 230-10-45-28 by reference; S-X 10-01(c)(2),(3), 8-03 |
| `retained_earnings` | opening + NetIncomeLoss - dividends (cash, stock and PIK) = closing; share-based compensation never | S-X 3-04, 5-02 caption 30(a), 10-01(a)(7) |
| `equity_roll` | opening StockholdersEquity + each movement group (credit adds, debit subtracts; DividendsCash first, stock and PIK netted out or the stock dividend's credit added back; repurchases read each) = closing | S-X 3-04, 10-01(a)(7), 8-03; FASB's balance attribute and equity calculation |
| `segment_sum` | segments + eliminations and corporate = consolidated, per element (instance or FSDS facts only) | PG-26, QF-37; Research's rubric ruling B4 |
| `ytd_quarter` | longer YTD - shorter YTD = the tagged quarter; Q4 = FY - nine months | S-X 10-01(c)(2),(3), 8-03; 17 CFR 240.13a-13(a); QF-34, QF-35 |

**The tolerance** is the larger of 1,000 (in the facts' unit) and 0.5% of the larger side. It is this skill's stated choice, since no published tolerance for a statement tie was found.
- **Roll-forwards.** For `cash_roll`, `retained_earnings` and `equity_roll`, the 0.5% is taken on the movements. That is the larger of the sum of the movements read and closing less opening, never the balance. 0.5% of a balance lets a missing movement smaller than that pass as a tie.
- **Rounding.** When facts carry `decimals`, the tolerance widens to the sum of the inputs' half-units of rounding (QF-41). Companyfacts carries no decimals.

**Exit codes:**
- `check`: 0 every checked tie ties · 1 a BREAK · 2 the facts file or `--period` unreadable · 3 no tie applicable (never a clean pass).
- `explain`: 0 found · 1 no such tie.

## Limits

- **A break is a fact about the filing or about what companyfacts holds, not a correction.** Nothing here changes a value. Read the class, the hint and the facts, then the filing.
- **It does not fetch.** The caller supplies the facts, and the tool reads nothing else. It uses no network.
- **Companyfacts limits the roll-forwards.** Companyfacts holds undimensioned us-gaap facts only: the equity statement's total column. So these never reach it:
  - column lines on members (retained earnings, APIC, treasury);
  - adoption effects (the cumulative-effect members);
  - a retirement's excess over par charged to retained earnings;
  - a filer's own elements.

  An equity or retained-earnings BREAK names the groups read and those not tagged. Treat it as a pointer to the equity statement.
- **The equity roll reads the parent's equity only.** A filer that tags only the total including the noncontrolling interest reads ABSENT, and the row names that total.
- **net_income reads ProfitLoss as the cash flow's opening line.** A cash-flow statement that starts from income from continuing operations is not read. One element in one context is one fact. So with only one of ProfitLoss and NetIncomeLoss tagged, and no noncontrolling share, the two statements carry one fact, the tie cannot fail, and the row is ABSENT.
- **The continuing-operations noncontrolling share is a labelled fallback.** It is read only when neither the total nor its parts are tagged, and the note says a discontinued share is not in it. No filer of the 25 needed it.
- **Dividends by form.**
  - `Dividends`, `DividendsCommonStock` and `DividendsPreferredStock` count cash, stock and PIK dividends.
  - Retained earnings read `Dividends` first, since all three forms reduce it. When only a cash element is tagged, a stock or PIK dividend is not read; a gap equal to one names it.
  - The equity roll reads `DividendsCash` first. When an all-forms element is read, the stock and PIK parts are netted out only when they are tagged; otherwise the stock dividend's credit (`StockIssuedDuringPeriodValueStockDividend`) is added back when it is tagged (2.2).
- **A missing component is judged by name.** The candidate lists are this skill's choice and match an element's local name, so a filer's own element named like a movement counts as a lead. A coincident value is never a finding.
- **Scale in one direction only.** At a 0.5% tolerance, an input tagged 1,000 times too large cannot be told from a stray fact equal to the gap. It reads input equals gap. Scale is kept for an input 1,000 times too small.
- **Limited scope:**
  - `ytd_quarter` runs on undimensioned facts only.
  - `segment_sum` runs on the revenue elements only, and needs dimensioned facts (an instance or FSDS rows).
  - The two-class numerator (income available to common) is differenced like any flow, and a break there is left to the reader.
- **Where a figure is quoted rather than tied, other rules apply.**
  - A cash figure, and the cash in net debt, is `CashAndCashEquivalentsAtCarryingValue`, never the total including restricted cash (Research's rubric ruling C5).
  - Segments sum to consolidated only after eliminations and corporate lines. A disaggregation reconciles to the total its own table names (Research's rubric ruling B4).
- **Adding a tie or an element:** edit `data/ties.json` and give the row a source. T14 holds every row to one, every movement to a group and a sign, every never-row and unread balance to a reason, and every tie to a candidate rule.
