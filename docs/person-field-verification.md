# Person field verification

Verification is additive metadata on canonical `supporter_person` identities.
Existing profile/contact/address values are unchanged. Every existing value starts
unverified; no automatic backfill or claims about directory entries 5381/5382 occur.
Only organization administrators can write verification; reads use directory permissions.

The profile and duplicate comparison have a compact Field verification section.
Open it to load all field statuses together; select Review to change a status.
Verified and Incorrect require a source/reason. Identity confirmation is independent
of contact details. Saving edits first is required: the control explicitly shows the
persisted value it will verify, and the server rejects stale fingerprints.

Each review stores the exact checked value, reason, reviewer, UTC time and status.
Changes through ORM imports/edits invalidate prior checks in the same transaction;
reverting does not restore an expired assertion. Names in both languages and address
components are covered. Fingerprints also prevent a raw SQL changed value from
appearing verified; direct SQL edits that change and later restore a value must also
expire the corresponding verification rows. Direct SQL maintenance should use the
application edit/import path instead. Relationships remain in the existing separately
confirmed relationship workflow. This change does not alter duplicate matching rules.

## Release

After pulling the commit, run the existing additive migration command before serving
new workers:

```bash
APP_ENV=production python -m flask --app app init-db
pytest -q tests/test_person_verification.py tests/test_unified_people.py tests/test_duplicate_review.py tests/test_person_addresses.py tests/test_directory_get_performance.py tests/test_staff_page_query_growth.py tests/test_screen_contracts.py
```

The init-db hook creates only the new person_verification table and indexes; it does
not rewrite any existing person details. Normal page loads issue no verification
queries. Opening a section reads names, address metadata and latest field reviews
in fixed batches, plus the most recent 30 history entries. Saves add one review;
relevant person edits invalidate checks with one batched UPDATE per flush.
