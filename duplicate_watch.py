"""Conservative duplicate checks for canonical people.

Names alone are never identities. Phones remain the primary identity. A matching
normalized name plus normalized home address is treated as a review condition,
not an automatic merge.
"""
import re

from sqlalchemy import select
import app_original as core
from person_addresses import PersonAddressDetails


def _normalized(value):
    value = (value or '').casefold().strip()
    value = re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE)
    return ' '.join(value.split())


def name_address_key(name, street, unit='', city='', state='', zip_code='', country=''):
    name = _normalized(name)
    street = _normalized(street)
    if not name or not street:
        return None
    return (
        name,
        street,
        _normalized(unit),
        _normalized(city),
        _normalized(state),
        _normalized(zip_code),
        _normalized(country),
    )


def row_name_address_key(row):
    return name_address_key(
        row.get('name', ''),
        row.get('home_street', ''),
        row.get('home_unit', ''),
        row.get('home_city', ''),
        row.get('home_state', ''),
        row.get('home_zip_code', ''),
        row.get('home_country', ''),
    )


def existing_name_address_map():
    """Return one existing canonical person for each populated name/home address."""
    db = core.db
    people = db.session.scalars(select(core.SupporterPerson).where(
        core.SupporterPerson.home_address != ''
    )).all()
    if not people:
        return {}
    details = db.session.scalars(select(PersonAddressDetails).where(
        PersonAddressDetails.person_kind == 'person',
        PersonAddressDetails.person_id.in_([person.id for person in people])
    )).all()
    detail_by_id = {row.person_id: row for row in details}
    result = {}
    for person in people:
        detail = detail_by_id.get(person.id)
        extra = dict(detail.home or {}) if detail else {}
        key = name_address_key(
            person.name,
            person.home_address,
            extra.get('unit', ''),
            person.city,
            person.state,
            person.zip_code,
            extra.get('country', ''),
        )
        if key is not None:
            result.setdefault(key, person)
    return result


def duplicate_address_message(row_number, person, *, book_id=''):
    ref = f", book ID {book_id}" if book_id else ''
    return (
        f"Row {row_number}{ref}: same name and home address already belong to "
        f"existing person #{person.id}. Review before importing."
    )
