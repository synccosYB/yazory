# Family profile reports

`GET /families/<id>/print` now returns a structured case report rather than an
unbounded dump of every profile list.

## Data ownership

- Budget: the existing `budget_totals` / `child_budget.calculate` path used by the
  family profile. Applicable assistance is already deducted from need; pledges
  are displayed separately and never subtracted a second time.
- Monthly pledge: `case_monthly_pledged` is shared with the family profile. When
  workflows are enforced, their approved/current pledge calculation is used.
- Cash: the existing `case_fund_totals` path used by the family profile. It includes
  Receipt records and ABCharity net donations, disbursements, and the existing
  conservative available-balance gate.
- Donation detail: a normalized read-only projection of Receipt and CharityDonation.
  Each row identifies its source, reference, gross, fees, net, and received date.
  Imported timestamps use America/New_York dates; manual receipt dates remain as entered.
- A contact marked Paid without a linked positive receipt gets a review notice.
  A status is never converted into a payment. The notice cannot establish whether
  a particular pledge is fully settled, or find a donation that has not been linked.

This change does not merge people, deduplicate payments across sources, or migrate
financial records. Existing cross-source duplicates still require reconciliation;
report totals intentionally agree with the existing profile calculation.

## Output and filters

The case-wide summary is unaffected by list filters. Printed scope shows search,
status and donation date filters. The donation-list subtotal is explicitly distinct
from the whole-case cash total. Date filters apply only to donations.

Full audit history is omitted by default. Use `include_activity=1` with the full
report, or `section=activity`, for the appendix. Search still filters that history.
Empty sections use concise messages, not empty tables. Contacts are ordered by
follow-up status, show parent connections and notes, and do not render an unknown
commitment as a recurring zero-dollar pledge. Next steps are explicitly suggestions.

English, Hebrew and Yiddish labels ship together. Names, phone numbers, dates,
addresses and amounts use bidi isolation; print CSS repeats table headings and
preserves rows. Browser-supplied headers/footers are controlled in the print dialog.

## Deployment

No schema changes or data migration are required. Deploy the Python helper,
route changes, template, translations and stylesheet together through the existing
GitHub-to-runtime release workflow. Restart the application after pulling the release.
Verify a permitted family in each locale, an imported donation, a filtered donation
list, the optional activity appendix and an unassigned-family access denial.
