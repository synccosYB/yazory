# Duplicate review

Run the existing additive deployment migration before starting the new version:

```bash
APP_ENV=production flask --app 'app:create_app()' init-db
```

This adds `person_merge` (original data, actor, timestamp and old-link redirects)
and `person_identity_alias` (retained phone, email and identity lookup aliases).
No cleanup or merges run during migration. Existing match decisions are retained.

Open People directory → Possible duplicates. Review scans all canonical people,
preloads names, and renders twenty pairs per page. Phone/email matches or full name
plus household address propose review; names or addresses alone never merge.
Review later has a separate queue. Not-a-duplicate decisions stay suppressed.

Organization administrators may preview and confirm a merge, choosing the surviving
Person ID. Source-book conflicts and incompatible family links block merging.
The preview must be reloaded if either record changes. The transaction retains case
contact IDs, monetary records, communication/task references and case-specific notes.
Conflicting personal details remain in administrator-only Merge history. Existing
case contact rows are preserved even when both people were connected to the same case;
separate pledges or payments are never silently collapsed.

The retired public number remains reserved. Old person/profile links redirect to the
survivor, including subsequent merges. Preserved aliases prevent old contact values
from bypassing duplicate checks. Add Person warns before creation and allows an explicit
different-person choice for genuinely shared contact details. Spreadsheet imports
check phone variants and emails in bulk, alongside existing address checks. Book
imports retain their explicit source identity safeguards. Connect reuses the selected
canonical person rather than making another person.

PostgreSQL sequences prevent retired internal IDs from being reused. New SQLite demo
and test databases also use AUTOINCREMENT; an ORM reservation guard protects older
SQLite databases. Production uses PostgreSQL. No live database cleanup was performed
as part of implementation.
