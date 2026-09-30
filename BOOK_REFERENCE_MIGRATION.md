# Optional directory references and person family connections

Deploy the updated code, then run in the Replit shell:

```sh
cd ~/workspace
git pull --rebase origin main
APP_ENV=production python -m flask --app app_entry_intake init-db
```

Republish the app after the migration. The migration creates two additive
tables, `person_book_record` and `person_family_connection`. Existing people,
cases, connections, donations and communications are preserved. Production
startup and GET requests do not create these tables or perform backfills.

People keep their existing canonical identities. Family connections can be
entered directly on any imported person's profile without a book or case.
Existing person-to-person relationship tools remain available for other kinds
of connections. Father and father-in-law links are directional canonical person
references. Manual changes, including cleared links, take precedence over later
source imports.

The book reference is optional metadata, shown in a collapsed section. It is
not the app's person ID and is never required to connect people. Book source
(name/edition) plus printed ID identifies a source entry for repeat uploads.
Use the same source on every page of one edition. Blank source defaults to
`directory`. Different editions should use different sources.

Supported source columns: `Book ID`, `Book source`, `Yiddish first name`,
`Yiddish last name`, `Father name`, `Father-in-law name`, `Father book ID`,
`Father-in-law book ID`, `Original relationship line`, `Source rows`, `Notes`,
and `Review`, alongside existing bilingual names, phones and address columns.
IDs and ZIP codes should be text in Excel to retain leading zeros.

Import can target the general directory or an accessible case. Source details
and review notes are saved for entries with and without phones. Repeat imports
fill missing details but preserve corrections. A conflicting phone/name or
phone/book reference is skipped and reported. Names alone never create a family
link. An explicit relative reference can fill an unassigned canonical family
link when the target entry is imported, including on a later page or another
case. Missing targets remain unresolved. Direct connections don't require these
source references.
