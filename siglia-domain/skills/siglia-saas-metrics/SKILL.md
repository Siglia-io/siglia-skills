---
name: siglia-saas-metrics
description: SaaS and AI-SaaS metrics as filings disclose them versus as companies define them - revenue and its ASC 606 disaggregation, deferred revenue, RPO and its exemptions (ASC 606-10-50-14A, 50-14B and 50-15), capitalized commissions (ASC 340-40), capitalized software by taxonomy year, capex as two named lines, cloud and compute commitments (Item 303), gross margin in Research's order (never for by-nature statements, banks, insurers or BDCs), and company KPIs (ARR, NRR, customer counts, billings, AI revenue) with the SEC's definition expectation and Reg G's operating-metric exclusion. Each metric gives its us-gaap elements and ASC references by year, what it must never be computed from, and what the held set can ground. check-claim flags ARR or NRR computed from GAAP lines, a KPI without its definition, a falling RPO read as demand, a loss that "improved", and a direction word with one period's figure. Use before writing, reviewing or building anything that states or reads a SaaS figure or a gross margin.
---

# siglia-saas-metrics — what a SaaS figure is, and what it may never be computed from

**Version 1.4.1.**

The rules the reference carries:
- **Gross margin** follows Research's order (rubric row T3):
  1. GrossProfit;
  2. else revenue - CostOfRevenue;
  3. else revenue - (CostOfGoodsAndServicesSold + DirectCostsOfLeasedAndRentedPropertyOrEquipment), and only when every revenue line has its cost line.

  Otherwise it is not computed. It is not applicable to a by-nature statement: a separately tagged `LaborAndRelatedExpense` or `SalariesAndWages` beside `CostOfGoodsAndServicesSold`. Nor is it computed for a bank, thrift, insurer or BDC (X7; for insurers and BDCs a house rule). It never comes from a sub-line such as supplies. Where the cost lines exclude depreciation and amortization, it is labelled "before depreciation and amortization, which the statement shows separately". `CostOfServices` is absent from the 2024, 2025 and 2026 taxonomies.
- **Capex** is two named lines, PP&E purchases and capitalized software. `PaymentsToAcquireProductiveAssets` replaces the parts and is never added to them. FCF is labelled non-GAAP, and it is not computed for a bank, thrift, insurer or BDC.
- **Rubric rows** B4 (an ASC 606 disaggregation reconciles to the total its table names), T3, X2 and X7 are used with their corrections. X2's rule is two checks:
  - C4: a loss narrowed or widened, never "improved".
  - C5: a direction word needs both periods. A bare level ("fell to 41.2%") is not a comparison. A word that disagrees with its own "from" and "to" figures is flagged, and so is any word on equal figures, which read "unchanged".
- **The held rows** carry Corpus's verified counts, and the verify part's corrections govern. RPO is tagged for CAT, MSFT, GEOS and SEG. The expedient statements cover 8 issuers, the 12-month portion is an amount for CAT and a share for MSFT, and a billings KPI appears nowhere. The primer's older grounding line, which missed CAT and GEOS, is gone.
- **No code path is written in the data.** `metric NAME --grep DIR` searches a code folder you name, and sources are cited by file name.

**Why.** Research's deep-tier note on SaaS and AI metrics (26 Sep 2026) found two traps that no element name shows:
- **RPO can leave usage fees out by design.** ASC 606-10-50-14A lets usage fees for wholly unsatisfied (series) promises stay out, and 50-15 requires the note. So a consumption-priced AI company's RPO can omit most of its expected revenue. Usage estimated for a partially satisfied obligation is still disclosed.
- **`CapitalizedComputerSoftwareNet` narrowed in the 2026 taxonomy,** label and documentation, to software to be sold, leased or marketed. In 2024 and 2025 it may be either kind: a SaaS company's internal-use platform, or external-use software moved onto it from the deprecated sold-to-customers element. Read the company's note.

ARR, NRR, customer counts, billings and "AI revenue" are the company's own figures. The SEC expects each one with its definition, calculation and use (85 FR 10568). The held set grounds little of this. It is a 25-issuer snapshot of 16 Sep 2026 with about one SaaS name. It holds a tagged RPO for 4 issuers and no ARR, NRR or billings figure at all.

The reference is `data/saas.json`:
- 14 metrics, 12 rules and 5 checks;
- 143 sourced rows, each with its source.

`sources` resolves every source item, and says which:
- **A named file:** a Research note, re-read log or rubric file, or an agent primer, found by its file name among the checkout's tracked files. A Corpus pack is found by its file name in Corpus's folder. Each `anchor` must be in the file, or in the named row or pack when the item names a key: `Corpus pack (file.json, KEY)`.
- **A fin-concepts register row** (`siglia-fin-concepts SE-36`): the row is in the sibling skill's data, and each anchor is in that row, not only somewhere in the file.
- The section exists, and its paragraph labels occur in it in order. Each single-quoted string in a rule's `says` is in a cited section, or is one of that row's anchors. Each `absent` phrase is in none of them.
- **FASB taxonomy years:** read offline with siglia-xbrl-element, whose index and search are loaded in-process. An element row's element exists, and its label and period equal the row's. Its `asc` references are its references in that year, and a legacy one must be marked. Every year's label is compared by some taxonomy item of the row, so the items may split the years. `anchors` name an element that exists (`X`), is absent (`!X`), carries a reference (`X ASC p`), is documented in those words (`X: words`), or a label search's whole result (`search WORDS = X, Y`).
- **A FASB ASU, cited by reference** (`FASB ASU 2016-20 (storage.fasb.org, sha256 HEX, read DATE, by reference)`): its text is never read or quoted here, so it takes no anchors. It resolves when a named file the same row cites, Research's record of the read, holds both the ASU's number and that sha256.

## Steps

```bash
S="$SKILL_DIR/scripts/saas.py"     # SKILL_DIR: this skill's folder
PY=python3                         # 3.9 stdlib is enough
"$PY" "$S" list                                   # every metric, rule and check, one line each
"$PY" "$S" metric rpo                             # GAAP or company-defined, elements and refs by year, never-from, held, rules
"$PY" "$S" metric gross margin                    # T3's order and guard, by-nature, bank/thrift/insurer/BDC; CostOfServices absent
"$PY" "$S" metric capitalized software            # labels and refs by year, the three cash lines, the deprecated element, ASU 2025-06
"$PY" "$S" metric contract liabilities            # by alias; also by us-gaap element: metric PaymentsForSoftware
"$PY" "$S" metric rpo --grep ~/src/product        # plus every line of a code file under that folder naming each element
"$PY" "$S" check-claim "Acme's ARR is \$400M (Q4 revenue x 4)."   # C1 computed from GAAP lines, C2 no definition
"$PY" "$S" check-claim "RPO fell 20% as usage demand weakened."    # C3: a bare "usage" is not an exemption statement
"$PY" "$S" check-claim "Operating loss improved to \$3.1m."        # C4 a loss narrowed or widened; C5 one period only
"$PY" "$S" check-claim "Gross profit increased to \$7.94m from \$8.29m."   # C5: the word disagrees with its own figures
"$PY" "$S" sources                                # every source item resolves: named files, register, cached eCFR, taxonomy
```

**check-claim:**
- A claim that quotes the company's own definition passes, for example "the company defines ARR as...". So does one that says no definition is printed.
- C1 counts the definition only in the clause that holds the computation. Clauses are split at a sentence end, `;` and a dash. A computation the writer made ("which we derived as revenue x 4") is flagged even when the company's definition is named.
- C3 is cleared only by an actual exemption statement: 50-14, 50-14A or 50-15; *exempt* or *expedient*; right to invoice; or usage, consumption or variable consideration said to be excluded, omitted or left out. "RPO fell as usage demand weakened" is flagged.
- C4 flags a loss said to improve, worsen, get better or worse, or deteriorate in the same clause.
- C5 flags a direction word with one figure reached ("rose to $50M") and no comparison beside it. A comparison carries the other period's figure or the change itself:
  - a "from" figure;
  - a change: "by 5%", "up 5%", "down $2m", "rose 19%", "a 5% increase", "3 percentage points", "$8M more";
  - a figure after "compared with", "versus", "vs.", "against" or "than", or a figure followed by "a year earlier".

  A bare level ("fell to 41.2%", "increased to 15%") is not a comparison. Nor is a period named without its figure ("year over year"), or "by 2026".
- C5 also reads a direction word against its own "from" and "to" figures, with their sign and scale ("-$5.0m"; "$900 million to $1.2 billion"). It flags a word that disagrees with them: "increased to $7.94m from $8.29m", or a loss that "narrowed" to a larger figure ("narrowed" and "widened" compare sizes). It also flags any direction word on equal figures, which read "unchanged".
- The check reads the claim's text only. It cannot load the prior period's figure: the reader of the claim does that.

**Where things are found:**
- **The taxonomy** is siglia-xbrl-element's `$TMPDIR/siglia-xbrl-cache` (`SAAS_XBRL_CACHE` overrides it).
- **Named files** are this checkout's tracked files (`SAAS_ROOT` overrides it).
- `$TMPDIR` differs sandboxed and unsandboxed, so run `sources` on the side where the taxonomy cache was filled.

**Exit codes:**
- 0: found, clean, or all sources resolve;
- 1: an unknown name, a flag, a dangling source, or a `--grep` folder that does not exist;
- 2: the data file is unreadable, or `sources` could not check. That is a missing checkout, Corpus folder, register, cached eCFR, or 2024–2026 taxonomy year. It is never read as "resolves".

## Limits

- **Left out as unsourced:**
  - the SEC staff's view of ARR as non-GAAP or operational (its comment letters are on sec.gov, which this skill never fetches);
  - any market threshold for these metrics, such as "good" NRR (SE-36 to SE-38 record none);
  - whether a billings figure is non-GAAP;
  - the XBRL member a company uses for subscription revenue;
  - customer counts, AI revenue and bookings in the held set, which were not measured.
- **The held rows describe 25 names only,** measured by regex over held text and facts, not by full reading. A figure phrased outside the patterns could be missed. The held facts have no dimension and no taxonomy year.
- **Removed as unsourced:**
  - that AI inference and compute costs sit in cost of revenue (which line a cost sits in is the company's own classification);
  - bookings as contract value signed in a period (PG-33 says only that bookings are company-defined and may include cancellable orders).

  The subscription-revenue row is marked as this skill's reading, and so are the untagged-commitment row and the purchase-obligation note as a home for compute commitments (ASC 440-10-50 was not re-read). ASC 340-40's recognition condition and one-year expedient, removed in 1.1 as unsourced, are back, from ASU 2014-09 as issued, by reference.
- **Where Research's note and the primer are superseded:**
  - The "material cash requirements" sentence is in 229.303(b)(1)'s lead-in, not (b)(1)(ii) (eCFR as of 2026-09-24).
  - F3 says "The exemptions never apply to fixed consideration (50-14B)", after a list that includes contracts of one year or less, and the primer scopes 50-14B to the 50-14A exemption alone. Both are wrong. ASU 2016-20's 50-14B bars fixed consideration from the 50-14(b) right-to-invoice exemption and the 50-14A exemptions, and leaves 50-14(a) open. F3 gives 50-14A as its limb (b) without the series promise, and the primer as letting usage fees stay out. 50-14A has two limbs, and a SaaS usage fee usually relies on the series part of (b).
  - F5's "sales commissions on multi-year contracts" is not the test: 340-40 capitalizes recoverable costs.
  - F6 names only `PaymentsToDevelopSoftware` and the policy text block for internal-use software in 2026. The cash may be on `PaymentsToAcquireSoftware` or `PaymentsForSoftware` too. The 2026 taxonomy also ties internal-use software (ASC 350-40-50-1, common practice) to the PP&E and finite-lived intangible elements and to the software members, and this skill names that route.
  - F7's threshold leaves out the second condition's "used to perform the function intended", the weighing of development uncertainty, the interim periods and the transition methods.
  - F8's "they also belong in the purchase-obligation notes" has no primary source here.
- **Not verified by Research's checks, so kept out of every rule and marked where stated:**
  - the held rows' counts, which are Corpus's measurements, not primary-source facts;
  - the current Codification text of 606-10-50-15 and 340-40: only the ASUs as issued were read, so later technical corrections are unchecked;
  - that a customer count is an operating metric, and that ARR's status depends on how it is computed: inferences from 244.101(a) and 229.10(e)(4);
  - the practitioner definitions: ARR as MRR x 12, NRR and GRR, billings as revenue plus the change in deferred revenue, bookings, and the Rule of 40;
  - the sentence in 85 FR 63726 that removed backlog from Item 101(c). `sources` checks only that 229.101 lacks the word;
  - how filers use the RPO percentage's start-date axis.

  That 229.303 lacks "key performance indicators" is re-checked against the cached eCFR on every `sources` run.
- **The rubric rows' own company examples and figures are not copied into the reference.** Only the rules and their corrections are used. T3's supplies example is cited as an anchor for "a sub-line such as supplies".
- **Register rows SE-46 to SE-49 and QF-49 do not exist yet.** Research proposed them in the note, and on 26 Sep they are not in the fin-concepts register. This skill cites the note's findings instead. SE-39 still names only PP&E as capex, and the capex ruling adds capitalized software.
- **FASB ASC text is never quoted,** only cited by paragraph. Taxonomy labels and documentation are quoted under FASB's notice, which `metric` prints. ASUs 2014-09, 2016-20 and 2025-06 are cited by reference: `sources` checks that Research's record of the read holds each one's number and hash, not the ASU's text.
- **Some checks are weak by design:**
  - The paragraph-label check proves the labels occur in order in the section, not that they nest.
  - An `asc` names the references this row relies on, not all of an element's references.
  - A 17 CFR item's "as of" date is not compared with the cache's date. The quotes are re-checked against whatever the cache holds, and `sources` prints that date.
- **check-claim is a word-pattern check, not a reader.** Wording can evade it or trip it. "We define" reads as the writer's own definition, not the company's. For C5:
  - "more than $X" reads as a comparison.
  - A comparison after a dash or a semicolon is in another clause, so "rose to $50M — up 19%" is flagged.
  - "Improved" has no direction of its own (for a cost it can mean lower), so only equal figures are checked for it.
  - A bare four-digit year is not a figure. Figures of different kinds, such as a percent and an amount, are not compared.

  Quote a rule only after `siglia-def-check` re-reads it.
- **To add a metric or rule,** edit `data/saas.json`. T1 holds its shape and sources.
