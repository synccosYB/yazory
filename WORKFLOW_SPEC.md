The software should operate the entire organization—not only fundraising. Every action should enter a defined workflow with an owner, status, approval rules, deadlines, documents, and permanent audit history.

# Organization-wide workflow structure

## 1. Organization setup and governance

This establishes who controls the organization.

### Workflow

1.  Create organization and legal entity. 
2.  Configure banking, payment processing, accounting, and receipt details. 
3.  Add board members, rabbinical supervisors, administrators, caseworkers, finance staff, and fundraisers. 
4.  Assign roles and financial approval limits. 
5.  Establish organizational policies: 
   -  Case eligibility 
   -  Privacy and disclosure 
   -  Expense approval thresholds 
   -  Emergency assistance 
   -  Restricted donations 
   -  Surplus funds 
   -  Conflicts of interest 
6.  Approve policies by the board and rabbinical leadership. 
7.  Require annual review and reapproval. 

### Roles

-  Board or executive leadership 
-  Rabbinical committee 
-  Executive director 
-  Finance administrator 
-  Compliance administrator 
-  Case administrator 
-  Fundraising administrator 
-  Read-only auditor 

No employee should be able to create a transaction, approve it, and release its payment alone.

---

# Family and case operations

## 2. Referral workflow

A new family may be referred by a rabbi, relative, organization, medical advocate, school, or administrator.

### Statuses

`New referral → Contact attempted → Consent received → Intake scheduled → Intake opened`

The referral records:

-  Person making the referral 
-  Relationship to the family 
-  Basic reason for assistance 
-  Urgency 
-  Rabbi or community reference 
-  Safe method of contacting the family 
-  Permission to identify the referring person 

A referral is not yet an approved case.

## 3. Family intake workflow

The intake administrator gathers:

-  Household members 
-  Children, ages, grades, and schools 
-  Income and employment 
-  Household expenses 
-  Insurance and public benefits 
-  Assistance received elsewhere 
-  Medical-impact summary 
-  Rabbis and community affiliations 
-  Siblings, cousins, friends, and supporter connections 
-  Supporting documents 
-  Privacy and fundraising consent 

### Statuses

`Draft → Missing information → Family review → Submitted for verification`

Sensitive medical documents should be separated from general case and fundraising information.

## 4. Verification workflow

Each fact receives a verification status:

-  Verified 
-  Partially verified 
-  Documentation requested 
-  Unable to verify 
-  Not applicable 

Verification may include:

-  Income and employment 
-  Bank statements 
-  Rent or mortgage 
-  Tuition 
-  Utilities 
-  Existing organizational assistance 
-  Rabbi or community reference 
-  Family composition 
-  Vendor balances 

### Statuses

`Assigned → Verification in progress → Clarification required → Verified → Rejected`

The verifier cannot give final case approval alone.

## 5. Needs assessment and budgeting

The system calculates:

```math
\text{Household shortfall}
=
\text{approved household expenses}
-
\text{income and outside assistance}
```

The case fundraising requirement becomes:

```math
\text{Fundraising goal}
=
\text{household shortfall}
+
\text{case-related organization expenses}
+
\text{approved reserve}
```

The budget includes:

-  Approved household-expense categories 
-  Monthly assistance limit 
-  Case duration 
-  Organization’s expenses for managing the case 
-  Processing fees 
-  Emergency reserve 
-  Existing assistance from other organizations 
-  Expected family contribution 

### Statuses

`Assessment draft → Finance review → Rabbinical review → Approved/Revision required/Declined`

## 6. Case approval workflow

Approval should require:

1.  Intake administrator completes the file. 
2.  Verifier signs off on the information. 
3.  Financial administrator approves the calculations. 
4.  Two case administrators approve the proposed plan. 
5.  Rabbinical supervisor approves the case. 
6.  Executive approval is required above configurable limits. 

The final approval establishes:

-  Assistance amount 
-  Fundraising goal 
-  Approved expenses 
-  Case duration 
-  Review frequency 
-  Privacy level 
-  Supporter outreach permissions 
-  Surplus policy 
-  Assigned staff 

### Statuses

`Awaiting approval → Approved with conditions → Approved → Declined → Appealed`

## 7. Family-support plan

An approved case receives a support schedule:

-  Tuition payments 
-  Grocery or butcher allowance 
-  Rent or mortgage support 
-  Utilities 
-  Transportation 
-  Childcare 
-  Household help 
-  Other approved needs 

Payments should go directly to vendors where practical. Direct family payments require documented justification.

### Statuses

`Plan draft → Family confirmation → Approved → Active → Modified → Completed`

## 8. Case review and renewal

Every case receives monthly operational review and a deeper review every three or six months.

The review examines:

-  Changes in income 
-  Employment status 
-  Household expenses 
-  Other assistance 
-  Funds collected 
-  Funds spent 
-  Case-related organizational expenses 
-  Remaining balance 
-  Continued eligibility 
-  Supporter fatigue or collection risk 

### Decisions

-  Continue unchanged 
-  Increase or reduce assistance 
-  Request documents 
-  Pause assistance 
-  Pause fundraising 
-  Extend the case 
-  Begin closure 

Missed reviews should generate escalations and restrict new nonessential expenses.

---

# Supporter network and fundraising

## 9. Supporter-tree workflow

Contacts are organized into private supporter circles:

-  Immediate family and spouses 
-  First cousins 
-  Shul friends 
-  Yeshivah or school friends 
-  Extended family 
-  Community contacts 

### Workflow

`Identified → Relationship verified → Contact permitted → Assigned to fundraiser → Ready for outreach`

Every supporter record contains:

-  Connection to the husband or wife 
-  Family-tree relationship 
-  Contact information 
-  Introduced by 
-  Assigned fundraiser 
-  Suggested amount 
-  Communication preference 
-  Privacy restrictions 
-  Donation history 

The family should be able to mark people who must not be contacted.

## 10. Fundraising-plan approval

Before outreach begins:

1.  Build supporter groups. 
2.  Estimate amounts by group. 
3.  Prepare private and public messaging. 
4.  Decide what case information may be shared. 
5.  Assign fundraisers. 
6.  Set monthly and overall goals. 
7.  Obtain case-administrator approval. 
8.  Obtain privacy approval from the appropriate supervisor. 

### Statuses

`Draft → Privacy review → Approved → Active → Paused → Completed`

## 11. Outreach workflow

Each contact moves through:

`Not contacted → Assigned → Contact attempted → Reached → Follow-up → Pledged → Declined → Do not contact`

The system tracks:

-  Calls, texts, emails, and meetings 
-  Fundraiser responsible 
-  Promises made 
-  Follow-up dates 
-  Suggested and agreed amounts 
-  Reasons for declining 
-  Communication consent 

Fundraisers should only see the contacts assigned to them and a limited version of the family story.

## 12. Pledge workflow

A pledge records:

-  Donor 
-  Case 
-  Monthly or one-time amount 
-  Start and end date 
-  Payment method 
-  Case restriction 
-  Anonymous preference 
-  Receipt preference 
-  Fundraiser attribution 

### Statuses

`Proposed → Confirmed → Payment setup pending → Active → Past due → Paused → Completed → Canceled`

Verbal or offline pledges should require confirmation before being included as dependable projected revenue.

## 13. Donation collection workflow

`Payment scheduled → Processing → Collected → Posted → Receipt issued → Reconciled`

Failed payments move through:

`Failed → Automatic retry → Donor notified → Staff follow-up → Updated payment method/Uncollectible`

The dashboard distinguishes:

-  Pledged 
-  Expected 
-  Processing 
-  Successfully collected 
-  Failed 
-  Refunded 
-  Available for spending 

## 14. Donor-service workflow

The donor portal or staff workflow should allow:

-  Update payment method 
-  Increase or reduce donation 
-  Pause or cancel 
-  Download receipts 
-  Request anonymity 
-  Change communication preferences 
-  Ask a question 
-  Report an incorrect charge 

Requests move through:

`Received → Assigned → Resolved → Donor notified → Closed`

---

# Financial operations

## 15. Expense-request workflow

Every expenditure is classified as either:

- **Family assistance**, or 
- **Organization’s expense for that particular case** 

### Workflow

1.  Submit expense. 
2.  Assign case and category. 
3.  Attach invoice or receipt. 
4.  Identify family assistance or organizational expense. 
5.  Check approved budget and available case balance. 
6.  Obtain required approval. 
7.  Schedule payment. 
8.  Release payment. 
9.  Attach proof of payment. 
10.  Post to case ledger. 
11.  Reconcile with bank activity. 

### Statuses

`Draft → Submitted → Under review → Approved → Scheduled → Paid → Reconciled`

Alternative outcomes:

`Revision requested → Rejected → Voided → Refunded`

## 16. Expense approvals

| Expense typeRequired approval     |                                            |
| --------------------------------- | ------------------------------------------ |
| Routine approved assistance       | Case administrator + finance release       |
| New expense category              | Two case administrators                    |
| Above-budget payment              | Finance + two administrators               |
| Major budget change               | Rabbinical supervisor                      |
| Case-related organization expense | Case administrator + finance administrator |
| Related-party payment             | Two administrators + rabbinical supervisor |
| Large payment                     | Executive approval                         |
| Cash payment                      | Two approvals and signed receipt           |
| Emergency assistance              | Administrator + rabbinical approval        |

Thresholds should be configurable by amount and expense category.

## 17. Organization-expense allocation

Expenses such as payment-processing fees, bookkeeping, fundraising, and case-management costs must use a documented allocation method.

For example:

-  Direct expense: completely assigned to one case 
-  Per-transaction allocation 
-  Percentage of funds collected 
-  Time-based allocation 
-  Equal allocation among active cases 

Allocation changes require finance approval and remain visible in the audit trail.

## 18. Vendor workflow

Vendors include schools, groceries, butchers, landlords, utilities, transportation companies, and service providers.

### Workflow

`Vendor proposed → Identity verified → Payment details verified → Approved → Active`

Vendor changes require re-verification, especially bank-account changes.

The system tracks:

-  Cases served 
-  Bills 
-  Credits 
-  Payments 
-  Tax documentation where applicable 
-  Contact people 
-  Duplicate invoices 
-  Payment history 

## 19. Payment workflow

1.  Approved expense enters payment queue. 
2.  Finance verifies the payee and banking details. 
3.  System checks for duplicate invoices. 
4.  Payment batch is created. 
5.  Authorized individual approves the batch. 
6.  A different authorized individual releases it. 
7.  Bank result is received. 
8.  Ledger and case balance are updated. 
9.  Failed or returned payments enter an exception queue. 

## 20. Bank reconciliation

`Bank transaction imported → Suggested match → Finance review → Matched → Reconciled`

Exceptions include:

-  Unknown deposit 
-  Unmatched withdrawal 
-  Duplicate charge 
-  Incorrect amount 
-  Returned payment 
-  Processing-fee difference 
-  Chargeback 

Monthly financial reports should not be finalized until reconciliation is complete.

## 21. Refund and chargeback workflow

`Request/dispute received → Original donation located → Case impact calculated → Approval → Refund processed → Ledger adjusted → Donor notified`

If money has already been spent, the system must show how the refund affects the case balance and whether the organization must cover the difference.

## 22. Inter-case transfer workflow

Case-restricted funds should not be transferred casually.

Required steps:

1.  Record why funds cannot remain in the original case. 
2.  Review donor restrictions. 
3.  Obtain donor authorization when required. 
4.  Obtain finance approval. 
5.  Obtain rabbinical or executive approval. 
6.  Post equal transfer entries in both case ledgers. 
7.  Notify the appropriate oversight users. 

---

# Emergency and exceptional situations

## 23. Emergency-assistance workflow

`Emergency reported → Basic verification → Rabbinical approval → Second approval → Immediate payment → Documentation completed → Post-payment review`

Missing documentation must be completed within a defined period, such as 48 hours.

## 24. Complaint and safeguarding workflow

Complaints may come from families, donors, vendors, employees, or community members.

### Workflow

`Received → Risk classified → Assigned privately → Investigated → Decision → Corrective action → Closed`

Serious allegations should restrict access to specifically authorized investigators and leadership.

## 25. Conflict-of-interest workflow

Users must disclose relationships with:

-  Assisted families 
-  Vendors 
-  Donors 
-  Employees 
-  Outside organizations 

A conflicted user is automatically removed from approval decisions related to that case or transaction.

## 26. Fraud or unusual-activity workflow

The system should flag:

-  Duplicate invoices 
-  Multiple payments for the same obligation 
-  Payments to newly changed bank accounts 
-  Expenses just below approval thresholds 
-  Unusual cash payments 
-  Payments to related parties 
-  Excessive refunds 
-  Unexpected case-balance changes 

`Flagged → Payment held → Compliance review → Cleared/Escalated/Rejected`

---

# Administration and staff

## 27. User onboarding

`Invited → Identity verified → Role assigned → Training completed → Access approved → Active`

Access should be based on responsibility:

-  Case access 
-  Donor access 
-  Medical-information access 
-  Financial access 
-  Payment authority 
-  Reporting access 

## 28. User departure or role change

`Change requested → Manager approval → Access reviewed → Permissions updated/revoked → Open assignments transferred → Completed`

Departing users should lose access immediately while their historical actions remain preserved.

## 29. Task and escalation workflow

Every case-related task includes:

-  Owner 
-  Due date 
-  Priority 
-  Case 
-  Required documents 
-  Dependency 
-  Escalation person 

### Statuses

`Open → In progress → Waiting on family → Waiting on third party → Completed → Overdue`

Overdue financial and safety tasks escalate automatically.

## 30. Document workflow

`Uploaded → Classified → Case assigned → Privacy level selected → Reviewed → Approved → Archived`

Document types include:

-  Intake documents 
-  Income proof 
-  Bills and invoices 
-  Rabbinical approvals 
-  Consents 
-  Receipts 
-  Bank records 
-  Donor authorizations 
-  Case-review reports 

The system should retain earlier versions and show who viewed, downloaded, or changed sensitive documents.

---

# Oversight and reporting

## 31. Per-case transparency workflow

Each case dashboard shows authorized supervisors:

-  Total collected 
-  Donors and amounts 
-  Active recurring donations 
-  Failed collections 
-  Family assistance paid 
-  Case-specific organization expenses 
-  Processing fees 
-  Refunds 
-  Available balance 
-  Pending expenses 
-  Upcoming commitments 
-  Approval history 

Reports should be automatically prepared monthly, reviewed by finance, and acknowledged by the assigned administrators and rabbinical supervisor.

## 32. Organization-wide reporting

Leadership sees:

-  Active families 
-  Total monthly household gaps 
-  Collections by case 
-  Assistance delivered 
-  Organization expenses by case 
-  General overhead 
-  Case reserves 
-  Restricted and unrestricted balances 
-  Failed payments 
-  Fundraising effectiveness 
-  Vendor balances 
-  Upcoming obligations 
-  Cases awaiting review 
-  Approval bottlenecks 

## 33. Audit workflow

`Audit scheduled → Period selected → Documents locked → Sample transactions reviewed → Exceptions recorded → Management response → Corrective action → Audit closed`

Auditors receive read-only access. Nothing reviewed in an audit should be silently editable.

## 34. Case closure

1.  Stop new outreach. 
2.  Review recurring donations. 
3.  Notify donors when required. 
4.  Pay approved outstanding obligations. 
5.  Reconcile the case ledger. 
6.  Resolve the remaining restricted balance. 
7.  Produce a final financial report. 
8.  Obtain finance approval. 
9.  Obtain two administrator approvals. 
10.  Obtain rabbinical approval. 
11.  Lock the case. 

### Statuses

`Closure proposed → Collections stopping → Financial reconciliation → Final approval → Closed`

## 35. Reopening a case

A closed case is not simply changed back to active.

`Reopening requested → New circumstances documented → Financial reassessment → Rabbinical approval → New assistance plan → Reopened`

The previous case period remains historically intact.

# Core system rule

Every important record should follow the same operating pattern:

```
svg
```

svg

svg

At every stage, the system records:

-  Who owns it 
-  Who submitted it 
-  Who verified it 
-  Who approved it 
-  What changed 
-  When it happened 
-  Which documents support it 
-  What money was affected 
-  Who was notified 

This gives the organization one connected operating system for referrals, cases, supporter relationships, fundraising, collections, assistance, organizational expenses, accounting, rabbinical oversight, and transparency.