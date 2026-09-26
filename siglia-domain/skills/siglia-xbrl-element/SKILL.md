---
name: siglia-xbrl-element
description: Look up a US GAAP XBRL element from FASB's own 2026 taxonomy files (xbrl.fasb.org, never sec.gov) in one call - its standard label, period type (duration or instant), balance (debit or credit), data type, whether it is abstract, whether and since when it is deprecated and what replaced it, FASB's documentation (the definition) quoted unchanged under FASB's Authorized Uses notice, and its ASC references by paragraph. Or search elements by the words of their label (and definition). Use before choosing, citing or computing with any us-gaap element, when a figure's element is uncertain, when a tag returns nothing (deprecated or removed?), and to settle what an element actually measures instead of guessing from its name.
---

# siglia-xbrl-element — what a us-gaap element is, from FASB's files

**Version 1.0.**

It is the element layer of the finance register (`siglia-fin-concepts`). Research names FASB's taxonomy files as the primary source for which element measures a figure. **Sessions get element names wrong, and the wrong one returns nothing, or the wrong thing, with no error.**

## Steps

```bash
X="scripts/xbrl_element.py"
python3 "$X" show NetCashProvidedByUsedInOperatingActivities,PaymentsToAcquirePropertyPlantAndEquipment
python3 "$X" show us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding --json
python3 "$X" search proceeds issuance common stock          # every word in the standard label
python3 "$X" search capital expenditure --doc               # ... or in FASB's definition
python3 "$X" --year 2021 show CashAndCashEquivalentsPeriodIncreaseDecrease   # an older taxonomy
```

- **The first run fetches** the five 2026 files (about 48 MB) with curl into `$TMPDIR/siglia-xbrl-cache/2026/` and builds an index (about 9 MB). Later runs read the index in under a second. Use `--offline` to forbid fetching and `--cache DIR` to put the cache elsewhere.
- **The sandbox:** fetching needs `xbrl.fasb.org` in `allowed_domains`. Sandboxed and unsandboxed runs have different `$TMPDIR`s, so each keeps its own cache.
- **Exit codes:** `0` every name found · `1` a name absent, or not fetched (dei) · `2` cannot fetch or parse.

## What it fixes in the extractor it came from (Research's four, and one more)

1. **curl, not urllib.** urllib got an IncompleteRead through the proxy. Each file is written to `.part` and moved into place only when whole, so a cut download never becomes the cached file (E1).
2. **Deprecation is read, not returned as None.** The `depcon` linkbase names the replacement and how (replaced by; dimensionally qualified; split into; mutually exclusive). The year comes from the element's own label, e.g. "(Deprecated 2024)". An element removed altogether reads **ABSENT from the 2026 taxonomy**, with a pointer to `--year` (E3, E4). Filings made before its removal carry it, so the fallback may be deliberate.
3. **Period type and balance** come from `us-gaap-2026.xsd` (E2). Cash-flow elements carry no balance.
4. **dei reads "not fetched".** The dei taxonomy is served from xbrl.sec.gov, which this skill never fetches, so dei is never guessed (E5).
5. **An XML guard**. A file declaring a DOCTYPE or an ENTITY is refused before the stdlib parser sees it, which rules out entity-expansion attacks (E11). FASB's files carry none.

## The licence (read by Research at https://xbrl.fasb.org/terms/TaxonomiesTermsConditions.html on 2026-09-24)

- **Labels and documentation may be quoted unchanged** in works that "comment on, explain, or assist in the use or implementation of the Taxonomy", with the Authorized Uses notice on the first page. So:
  - every output that quotes them starts with the notice;
  - `--json` carries the notice too;
  - text is never paraphrased in a field labelled as FASB's;
  - our own summaries go in fields labelled as ours.
- **Element names are identifiers** either way.
- **ASC text is never fetched or shown.** The FAF terms bar it, and the taxonomy licence does not cover the Codification. References are printed by paragraph, e.g. `ASC 230-10-45-24 [legacyRef]`. When every tie is `legacyRef`, the output says so: FASB describes those ties as unreviewed.

## Real runs (24 Sep 2026, the 2026 taxonomy: 17,179 elements)

- `NetCashProvidedByUsedInOperatingActivities`: "Cash Provided by (Used in) Operating Activity, Including Discontinued Operation"; duration; no balance. ASC 230-10-45-24/25/28, all legacyRef.
- `WeightedAverageNumberOfDilutedSharesOutstanding`: duration; shares. ASC 260-10-45-16 and 260-10-50-1(a), disclosureRef.
- `CashAndCashEquivalentsPeriodIncreaseDecrease`: **ABSENT from 2026.**
- `AccountsAndFinancingReceivablesAfterAllowanceForCreditLossCurrentRelatedAndNonrelatedPartyStatusExtensibleEnumeration`: **DEPRECATED since 2024**, replaced by `…CurrentRelatedPartyTypeExtensibleEnumeration`.
- `search capital expenditure` finds 2 elements, neither of them the usual capex line. With `--doc` it finds 10, and `PaymentsToAcquireProductiveAssets` is among them. **Capex is not an element named "capital expenditure":** use `show` on the register's element, not the phrase.

## What it does not do

- **It does not choose the element for a concept.** Which element measures "free cash flow" is the register's (`siglia-fin-concepts`), checked by Research. This skill says what an element is.
- **It does not read filings or company extensions.** A filer's custom element is not in FASB's taxonomy.
- **It reads us-gaap only.** srt, dei and ifrs-full say so and stop.
