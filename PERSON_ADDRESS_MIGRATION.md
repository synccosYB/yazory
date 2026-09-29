# Optional home and work addresses

After pulling this change, run `flask --app app_entry init-db` against the
deployment database before restarting or publishing the application. This uses
the existing explicit schema initialization hooks and creates the additive
`person_address_details` table. Existing records and addresses are preserved;
no backfill or lookup-provider account is needed.

All fields and the mailing preference start blank and remain optional. Existing
home street/city/state/ZIP and supporter workplace fields keep their current
storage. The new table owns the additional home components, work address and
mailing preference. Supporter case connections and directory profiles resolve
to the existing canonical SupporterPerson. Married child profiles resolve to
their linked supporter identity where present. Other roles retain their
existing identities; this change does not guess that similar names identify
the same person across roles.

Use the Home & work addresses action on the applicant, supporter, directory
profile, askan, staff, child, rabbi or partner contact. Directory affiliations
also expose the action for their existing person identity. Addresses can be
entered after creating a profile; profile creation never requires an address.

The receipt-address resolver uses the selected work address, otherwise the
existing home address. A selected but empty work address remains empty rather
than silently substituting another address. This change adds address storage
and editing; it does not send mail or change existing receipt PDF layouts.

Do not run the YZ-0006 wedding-list import until the importer has separately
been checked for address, category and relationship mapping.
