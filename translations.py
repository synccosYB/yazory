from flask import session
from translations_original import LANGUAGES, translate as _translate, translate_audit

_EXTRA = {
    'Shul friend': {
        'he': 'חבר מבית הכנסת',
        'yi': 'חבר פון שול',
    },
    'Filter this list': {'he': 'סינון הרשימה', 'yi': 'פילטער די ליסטע'},
    'Choose one or more options, then apply the filters.': {'he': 'בחרו אפשרות אחת או יותר, ולאחר מכן החילו את המסננים.', 'yi': 'קלויבט אויס איינס אדער מער, און דערנאך לייגט צו די פילטערס.'},
    'Filters active': {'he': 'מסננים פעילים', 'yi': 'פילטערס זענען אקטיוו'},
    'Search': {'he': 'חיפוש', 'yi': 'זוכן'},
    'Name or phone': {'he': 'שם או טלפון', 'yi': 'נאמען אדער טעלעפאן'},
    'All relationships': {'he': 'כל סוגי הקרבה', 'yi': 'אלע קרבה׳ס'},
    'All statuses': {'he': 'כל הסטטוסים', 'yi': 'אלע מצבים'},
    'All frequencies': {'he': 'כל התדירויות', 'yi': 'אלע אפטקייטן'},
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
