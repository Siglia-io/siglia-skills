---
name: siglia-earnings-quality
description: Earnings-quality reading from supplied XBRL facts, for coverage files and Case - cash conversion (operating cash flow against net income, and a loss narrowed or widened), accruals over average total assets, receivables growth against revenue growth with DSO, one-off items and the margin with and without the lines the issuer presents separately, the company's non-GAAP measures against their GAAP comparator and reconciliation (Regulation G, 17 CFR 244.100-102; S-K 10(e)), capex as Research ruled it (PP&E and capitalised software as two named lines) with capitalised interest and stock-based pay, and the perimeter when operations are discontinued (as Research ruled them). Each signal is a measured ratio or direction with its definition and source, never a verdict and never a line. Use before writing or reviewing a trajectory, earnings-quality, capex or non-GAAP claim, a Case cash-conversion reading, or any "are the earnings real" answer, instead of deriving accruals, DSO, capex or Reg G from memory.
---

# siglia-earnings-quality: what the facts show about earnings quality, with sources and no verdict

**Version 1.2.1.**

Research's content checks of this skill (B2, 26 Sep: 84 claims, 22 corrections) are applied too:
- operating cash flow is consolidated, while NetIncomeLoss and IncomeLossFromContinuingOperations are the parent's. So the consolidated continuing figure comes first, a parent-only figure is named, and the noncontrolling interests' share is shown when ProfitLoss is held and differs;
- a disposal group's revenue alone no longer marks discontinued operations present;
- SIC alone never decides a bank for revenue (1.2; 6091 and 6099 are not deposit banking), and bank revenue's sum is X7's, with S-X 9-04 giving only the captions;
- Regulation G's reach (a registrant or a person acting for it), 100(c)'s three conditions and 100(d)'s business-combination exemption, 10(e)(1)(iii) for a 10-Q, and 10(e)(5) for a segment measure GAAP requires;
- a 10-Q cash-flow statement is year-to-date, so the first quarter's is the quarter (S-X 10-01(c)(3) and 8-03);
- Items 2.05 and 2.06 are told apart, with no "most";
- gross margin subtracts both cost lines.

A review against the sources then brought in:
- Research's capex ruling in full: capitalised software is `PaymentsForSoftware` (the total) when held, with the parts inside it and never added; else `PaymentsToDevelopSoftware` plus `PaymentsToAcquireSoftware`, each named. The ASC 985-20 software-for-sale line is named as a line this skill does not read;
- the receivables signal carries its own perimeter note when discontinued operations are present and the recast comparatives are compared (B5);
- net debt's label names exactly what was subtracted;
- the composite scores are cited to their own rows;
- only the capex and capitalised-interest cash is said to sit in investing;
- DIO, the cash conversion cycle and working-capital swings are listed as defined in the register and not computed.

The corpus figures are Corpus's verified counts. No threshold ships.

**Why.** The seats kept re-deriving these readings, and the product got them wrong in print:
- Before this skill, seats re-derived earnings-quality terms in 120 sessions (83 since 20 Sep). They made 71 distinct web calls on the concepts in 17 sessions, 48 of them in 11 sessions since 20 Sep (Corpus pack (next6_packs_clean.json, earnings-quality), as its verifier corrected them).
- 23 of the 71 conditions the two demo funds wrote read trajectory or earnings-quality metrics, with 130 evaluations. The Case vocabulary has no accrual, receivables or non-GAAP concept, and its cash-conversion reading covers the latest fiscal year only.
- ER-001 found trajectory claims that compared across a discontinued-operations reclassification, put a net gain on business sales inside a margin, printed a raw float and used a year-old window (GAPS G29).

The definitions are not this skill's. Every source is a name, never a path, so the reference reads the same outside the repository. **No line ships.** Research has not ruled on earnings-quality thresholds. A signal is the measured figure and its direction against the company's own prior years.

## Steps

```bash
S="$SKILL_DIR/scripts/eq.py"            # SKILL_DIR: this skill's folder
PY=python3                              # 3.9 or later, stdlib only
"$PY" "$S" signals FACTS.json          # every signal: value, facts cited, definition and source
"$PY" "$S" signals FACTS.json --json   # the same, for code (Case, a coverage recipe, a grader)
"$PY" "$S" explain accruals            # a signal whole: formula, elements, rules, pitfalls, sources
"$PY" "$S" explain T4                  # an ER-001 row as Research ruled it, its correction, and how it is applied
"$PY" "$S" explain capex               # a rule: capex, gross_margin, net_debt, facility_size, absent_elements, words ...
"$PY" "$S" explain 244.100             # the Regulation G and S-K 10(e) rows that cite a CFR section
"$PY" "$S" list                        # every signal, rule and ER-001 row
"$PY" "$S" validate                    # every row sourced; beside the register and in a checkout, every source found
```

**FACTS.json** is `{"entity", "sic", "bdc", "registrant_type", "call_report", "fr_y9c", "facts": [...], "separately_presented": [...], "company_measures": [...]}`:
- `facts` are `financial_facts` rows as the store holds them (`id`, `taxonomy`, `tag`, `value_numeric`, `unit`, `period_start`, `period_end`, `accession_number`, `filed`, `form_type`, `superseded_by`), or `element`/`value`/`start`/`end`. Superseded facts are not read. Among current facts the latest filed wins. Facts that disagree with no later filing date between them are refused, and both are named.
- Lender-type (ER-001 X7 as ruled). `registrant_type` is one of bank, bank holding company, savings and loan association or savings and loan holding company (17 CFR 229.1401(a)). That, or a Call Report or FR Y-9C link (`call_report`, `fr_y9c`), decides first. Then `bdc` and `sic` go through Research's three tests (case-question-readings section 11), and a decision on SIC alone says so. For a lender-type filer, cash conversion, accruals and receivables read not applicable, and stock-based pay is not set against operating cash flow. That extension is the register's (CF-08 and CF-11 for operating cash flow, CF-15 for working capital). For a bank, bank revenue is net interest income plus noninterest income, as X7 rules (S-X 9-04 gives only the captions). So neither the operating margin nor stock-based pay's share of revenue is given. Only those keys decide a bank. A depository-institution SIC (6011-6089) with neither key leaves the question open, so no revenue-based ratio is given and the line names what the facts lack (1.2). 6091 (nondeposit trusts) and 6099 are not depository codes, and a note says so. Insurers and BDCs keep revenue, and a REIT is not lender-type.
- `separately_presented` names the lines the issuer shows apart on the face of the income statement, as `{fact_id, label, sign: "expense"|"income"}`. `one_off_items` gives the margin excluding them beside the GAAP margin (ER-001 T5).
- `company_measures` are the company's own non-GAAP figures, read from the 8-K Item 2.02 exhibit or MD&A, as `{name, period_end, value, comparator_fact_id, reconciliation, adjustments, source}`. The company's consolidated non-GAAP measures are not in the financial statements or notes (S-K 10(e)(1)(ii)(C)). A segment measure GAAP requires may carry an "adjusted" name in the notes, and it is not one of them (10(e)(5)).

**The signals:** `cash_conversion`, `accruals`, `receivables_vs_revenue`, `one_off_items`, `non_gaap_measures`, `capitalised_costs` (capex and the costs capitalised), `sbc_share` and `perimeter`. Each reads one of:
- `shown`;
- `none`: nothing of the kind is held, which is not a finding;
- `not_applicable`;
- `not_held`: an input is missing, and the line names what the facts supplied lack (ER-001 X9 as ruled; never "could not establish" for a bounded absence);
- `refused`.

**Capex, as Research ruled it.** Capex is purchases of property, plant and equipment plus capitalised software, shown as two named lines:
- PP&E purchases are `PaymentsToAcquirePropertyPlantAndEquipment`.
- Capitalised software is `PaymentsForSoftware`, the total, whenever it is held. `PaymentsToDevelopSoftware` and `PaymentsToAcquireSoftware` held beside it sit inside it and are named, never added. Without the total, capitalised software is `PaymentsToDevelopSoftware` plus `PaymentsToAcquireSoftware`, each named.
- The ruling also adds a filer's investing line for capitalised software to be sold (ASC 985-20) when tagged. That is a filer extension or a line the caller reads from the filing. This skill does not read it and says so.
- When the filer tags `PaymentsToAcquireProductiveAssets`, that one figure is capex: it replaces the parts and is never added to them.

Free cash flow built on capex is a non-GAAP measure, and this skill does not compute it. `CapitalizedComputerSoftwareNet` is software to be sold, so it is not the internal-use balance.

**What it prints.** Amounts as `$0.95m` or `$1.90bn`, ratios as `0.61x`, shares of a base as `3.71%`, always two decimals, and never a raw float (T6). Its only direction words are the sign's: higher, lower, unchanged, above, below and equal. For a loss in both years it says narrowed or widened, never "improved". Each direction word is written from both periods' figures (X2). It states no cause (X8). Before printing, it checks the text outside quoted issuer labels against the list of words it never prints, and exits 3 if one is there.

**Exit codes:**
- `signals`: 0 at least one signal shown · 1 none shown · 2 bad input · 3 a never-printed word reached the text.
- `explain`: 0 found · 1 unknown.
- `validate`: 0 clean · 1 a FAIL.

## Limits

- **No thresholds.** No line is drawn for cash conversion, accruals, DSO, the receivables-revenue gap, the non-GAAP gap, capitalised software's share of capex or stock-based pay. The register records only a training provider's rule of thumb for cash conversion (CF-08) and one for DSO (CF-17). Neither ships. When Research rules on earnings-quality thresholds, lines go into `data/` with their owner.
- **Fiscal years only.** It reads annual durations (364 to 371 days, both ends counted; ER-001 X1) and never a 10-Q year-to-date figure. The TTM roll is siglia-period-math's. When a later period is held, the header says so (ER-001 G29).
- **Gross margin is a rule, not a signal.** `explain gross_margin` gives Research's order (ER-001 T3 as ruled):
  - GrossProfit, else revenue less CostOfRevenue, else revenue less the sum of CostOfGoodsAndServicesSold and DirectCostsOfLeasedAndRentedPropertyOrEquipment, only when every revenue line has its cost line;
  - never CostOfGoodsAndServicesSold alone, and never a sub-line such as supplies;
  - not applicable for a by-nature statement (a labor line tagged beside cost of goods sold), and never for a bank;
  - labelled "before depreciation and amortization, which the statement shows separately" where the cost lines exclude it.

  `us-gaap:CostOfServices` is absent from the 2026 taxonomy (`explain absent_elements`).
- **Not in the register, so left out:**
  - contract costs capitalised under ASC 340-40;
  - fair-value remeasurement gains (warrant and earnout liabilities) and gains on the sale of a business, as one-offs, and which elements carry them. The caller names such a line in `separately_presented`;
  - an allowance-adequacy reading for non-banks.
- **Not computed:**
  - inventory build (days inventory outstanding, CF-18 and PG-23), the cash conversion cycle (CF-16) and working-capital swings with each line's cash sign (CF-15). The register defines them; this skill does not compute them;
  - DSO including contract assets or unbilled receivables. CF-17 asks only that a reading say whether they are included, so they are shown apart and left out;
  - composite scores: Beneish M, Piotroski F and Dechow F (CF-11 says none is authoritative; the models are RF-38, RF-39 and RF-41);
  - the balance-sheet accrual method;
  - free cash flow;
  - net debt and facility sizes, which other skills read. `explain net_debt` gives Research's rule: the components are listed, the label names exactly what was subtracted, and the cash is CashAndCashEquivalentsAtCarryingValue, never the total that includes restricted cash. `explain facility_size` gives the other: a facility's size is its maximum aggregate amount, and what is available is a separate, dated line;
  - any adjusted figure of this skill's own, except the ex-item margin ER-001 T5 asks for, labelled Siglia's arithmetic and shown beside the GAAP margin;
  - a filer's ASC 985-20 software-for-sale investing line, which capex leaves out and names.
- **Rulings sent as messages.** Research's gross-margin, capex and net-debt rulings of 26 Sep reached the seats as messages. Their sources read `Research ruling 2026-09-26 (...)`. Research's ruled rubric rows now carry them: T3 holds the gross-margin rule, and the capex, free-cash-flow and net-debt correction sits under C5. So each such source is cited beside `ER-001 T3 (ruled...)`, `ER-001 C5 (ruled...)` or a Research note of that date (`rubric-rows-ruled`, or `b2-skill-checks`, which says `PaymentsForSoftware` is never added to its parts). In a checkout, `validate` checks that row or note, and it fails a ruling cited alone. The ruled rows carry the ruling's gist, not every clause: the software order and the net-debt label are in the messages only. GAPS G29 was never ruled and stays ER-001 (unverified).
- **Quote a rule only after siglia-def-check re-reads it.** The CFR rows were read from the cached eCFR, not the live page.
