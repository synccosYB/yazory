# Person field verification

Verification is additive metadata on canonical `supporter_person` identities.
Existing profile/contact/address values are unchanged. Every existing value starts
unverified; no automatic backfill or claims about directory entries 5381/5382 occur.
Only organization administrators can write verification; reads use directory permissions.

The identity editor is a single profile form shared by the person hub and supporter
workspace. Names, contact details, home/work addresses and notes are edited directly.
Each field has collapsed verification controls. One Save changes action posts only
changed fields to `/people/<id>/verification` and commits edits, reviews and legacy
role snapshots together. Failures retain entered changes; stale values return 409.
Successful saves stay on the same screen and refresh the collapsed history.
Verification automatically returns to Unverified when an input changes; staff may
then explicitly verify the corrected value. Empty or duplicate legacy phone aliases
are hidden, while distinct numbers remain editable. Updating a home/cell number also
updates a matching legacy preferred-phone alias. Address metadata outside the edited
components is preserved. Existing single-field endpoints remain for compatibility.

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
not rewrite any existing person details. The profile editor loads names, address metadata, latest field reviews and the most
recent 30 history entries in fixed batches. Read-only hub pages defer this until the
editor is opened. Saving invalidates changed checks and adds reviews only for changed
fields. This update needs no additional database migration beyond the existing table.
