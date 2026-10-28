"""Presentation data for family reports; never writes or infers payments."""
from collections import Counter
from datetime import timezone
from zoneinfo import ZoneInfo


def donation_rows(receipts, donations):
    rows = [dict(source='Recorded receipt', source_id=row.id,
                 contact_id=row.contact_id, name=row.contact.name if row.contact else '',
                 received_on=row.received_on, gross=row.amount_cents,
                 net=row.amount_cents, fees=0, reference=row.reference or '',
                 note=row.note or '') for row in receipts]
    for row in donations:
        stamp = row.donation_time
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        rows.append(dict(source='ABCharity', source_id=row.id,
                         contact_id=row.donor.contact_id,
                         name=row.donor.local_name or row.donor.name,
                         received_on=stamp.astimezone(ZoneInfo('America/New_York')).date(),
                         gross=row.amount_cents, net=row.net_cents,
                         fees=row.amount_cents-row.net_cents,
                         reference=row.external_id, note=row.notes or ''))
    return sorted(rows, key=lambda row: (row['received_on'], row['source'], row['source_id']), reverse=True)


NEXT_ACTION = {
    'To contact': 'Contact supporter', 'Contacted': 'Record conversation outcome',
    'Call back': 'Schedule callback', 'No answer': 'Try contacting again',
    'Left a message': 'Follow up on message', 'Wrong number': 'Correct phone number',
    'Declined': 'Review decline notes', 'Pledged': 'Confirm pledge schedule',
    'Paid': 'Review payment records', 'Paused': 'Review paused contact',
}


def contact_summary(contacts, payments):
    paid_ids = {row['contact_id'] for row in payments if row['net'] > 0}
    return dict(
        statuses=sorted(Counter(row.status for row in contacts).items()),
        missing_phone=sum(not row.phone for row in contacts),
        unlinked_paid=[row for row in contacts if row.status == 'Paid' and row.id not in paid_ids],
        next_actions={row.id: ('Find contact details' if not row.phone else
                              NEXT_ACTION.get(row.status, 'Review contact')) for row in contacts},
    )
