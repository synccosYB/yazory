# Shared text groups (native Group MMS)

The existing private bulk SMS tool remains available as **Private group text**.
**Shared text groups** creates a Twilio Conversations Group MMS conversation with
2–9 distinct US/Canada mobile numbers plus one MMS-capable local Twilio projected
address. Native phone participants see all numbers and replies. The group name is
stored in Yazory; individual phone apps control their displayed group name.

## Release and configuration

Run the normal additive database initialization before serving the new pages:

```bash
APP_ENV=production python -m flask --app 'app:create_app()' init-db
```

This creates `text_group`, `text_group_member`, and `text_group_message`; it does
not alter existing person, message, or case records. Startup GETs do not migrate
or create Conversations. A rollback can leave these additive tables in place.

Set `TWILIO_GROUP_MMS_FROM` to an owned MMS-capable US/Canada local Twilio number
(e.g. the organization's existing MMS number). `TWILIO_SMS_FROM` is the fallback.
A Messaging Service SID alone cannot identify the projected address. Existing
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `APP_BASE_URL`, and optionally
`TWILIO_MESSAGING_SERVICE_SID` are reused. Conversations must be available on the
account. Toll-free numbers and short codes are not supported by Group MMS.

Creating a group uses `ConversationWithParticipants`. If Twilio is still adding
members, **Finish group setup** checks readiness and installs a conversation-scoped
`onMessageAdded` webhook at `/twilio/text-groups/webhook`. This is a POST operation.
The app does not replace existing SMS inbox webhooks or enable global autocreation.
Only an existing exact number-group match enters this conversation. Changing the
member list on a phone may create a different thread outside this integration.

## History, security, and delivery

Yazory sends through the Conversation Messages API with its projected phone
number as Author. Twilio forwards member replies natively; Yazory never rebroadcasts
incoming replies. The public callback requires a valid Twilio signature and stores
only replies from known members, idempotently by `IM` message SID. Messages appear
in the group transcript, person history, recent group replies in Communications,
and notifications linking to the group conversation. The displayed `sent` status
means accepted by Twilio, not confirmed delivery to every handset.

Every creation/read/send rechecks current contact permissions, including workflow
assignments. Phone numbers are snapshotted when the group is created. Groups with
the same full phone-member set reuse one thread, avoiding ambiguous reply routing.
Outgoing form tokens have a unique database reservation before any provider send,
preventing concurrent/replayed form submissions from sending the same message twice.
An interrupted `sending` message is deliberately not auto-retried: check Twilio's
logs before a manual new send because delivery may already have occurred.

Preview/test groups never send, even if later opened under production settings.
Incoming attachment counts are recorded; attachments remain in the native phone
conversation and are not downloaded into Yazory in this text-only release.

## Verification

```bash
pytest -q tests/test_text_groups.py tests/test_group_sms.py \
  tests/test_case_helper_roster.py tests/test_communications.py \
  tests/test_twilio_service.py tests/test_notifications.py tests/test_screen_contracts.py
```

Automated tests use preview mode or mocked provider calls. After release, use two
consenting test phones: create a shared group, send a message, reply from each phone,
verify the other receives each reply, and confirm the transcript and notification.
No live texts are sent by the automated tests.
