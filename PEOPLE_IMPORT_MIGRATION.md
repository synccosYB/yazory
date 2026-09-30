# People import and bilingual names

The update preserves existing legacy names and every case, pledge, receipt and
communication reference. English and Yiddish names are stored separately; a
legacy name populates its detected script, with the other variant left blank.
No translation or transliteration is guessed.

`person_names` holds the two variants. `person_name_owner` links applicant,
relative, askan and married-child role records to the canonical person's names.
Case contacts and imported profiles also use that canonical row. Both tables
are additive. The release migration is repeatable and does not overwrite
variants that have already been entered.

After pulling the update in the Replit shell, run:

```sh
APP_ENV=production python -m flask --app app_entry_intake init-db
```

Then republish the application. Production startup does not perform migrations.
Back up the database using the existing deployment procedure before migration.

People directory accepts CSV and XLSX. It recognizes English Name, Yiddish Name
or Yiddish/Hebrew Name, Name, Phone 1–3, Email 1–2, Address or Home Address,
Apartment/Unit, City, State, ZIP/Postal Code, Country, Workplace/Company, and
Work Address/City/State/ZIP/Country. Store ZIP codes as text in spreadsheets to
preserve leading zeros. A name is required; phone numbers may be blank.
Address-only imports reuse an exact source-record fingerprint on repeated uploads,
never a name-only match. Supplied invalid phone numbers are still rejected.
These records can be connected to cases and create normal workflow links and tasks.
No additional schema migration is needed. Reimports fill missing details,
preserve existing data and do not duplicate the same person/case connection.

Choose General people directory or an accessible case on the upload form.
Case imports create both Contact and SupporterLink, preserving case-specific
pledges and statuses. Open Names, addresses & relationships on a directory row
to connect two people independently of their cases. Existing supporters also
have a People relationships action on their profile.

Manual person, applicant, child, supporter, staff, rabbi and askan forms expose
English/Yiddish names. Existing records can also edit them through their
Home & work addresses editor. The pending public application keeps bilingual
answers in its existing JSON record. English is LTR; Yiddish is RTL; interface
labels ship in English, Hebrew and Yiddish.
