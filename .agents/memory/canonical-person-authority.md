---
name: Canonical person authority
description: Identity saves must survive legacy role replay and preserve explicit clears.
---

Once a role/profile has a canonical person ID, use that ID as the edit target; an old phone-based snapshot key must not choose a different person. Keep canonical identity edits and all linked snapshot refreshes in one transaction, and make edit-page GETs read-only.

**Why:** A profile save could conflict with its own case contact, while stale family/askan/child snapshots could replay older identity values on a later role save. Checking only the initial redirect/reload missed this second-writer failure.

**How to apply:** Identity regressions must include saving the person, reloading, and then invoking the existing role update path. Preserve legitimate role edits, but do not infer new identity changes merely from an old snapshot.

Primary, home, and cell phones are independent editable fields. Initialize fallbacks only for a newly created identity; do not restore an explicitly cleared cell phone or replace an independently edited primary phone from a role's home/cell values.

**Why:** Legacy family/child callbacks treated missing or different phones as values to repair, undoing successful person-profile saves.

**How to apply:** Cover distinct phone values and explicit blank fields followed by role replay, including married-child connections. An unlinked profile that resolves to an existing person must render that person's bilingual values without linking on GET.