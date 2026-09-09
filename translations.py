from flask import session
from translations_original import CATALOG, LANGUAGES, translate as _translate, translate_audit

_EXTRA = {
    'Shul friend': {
        'he': 'חבר מבית הכנסת',
        'yi': 'חבר פון שול',
    },
    'Mother-in-law’s maiden name': {
        'en': "Father's father-in-law name",
        'he': 'שם החותן של האב',
        'yi': "דעם טאטנ'ס שווערס נאמען",
    },
    'Mother-in-law’s family / network': {
        'en': "Father-in-law's father-in-law name",
        'he': 'שם החותן של החותן',
        'yi': "דעם שווער'ס שווערס נאמען",
    },
    'Name on card': {'he': 'שם על הכרטיס', 'yi': 'נאמען אויפן קארטל'},
    'Email for receipt': {'he': 'אימייל לקבלה', 'yi': 'אימעיל פאר קבלה'},
    'Card information': {'he': 'פרטי כרטיס', 'yi': 'קארטל אינפארמאציע'},
    'Process donation': {'he': 'עיבוד התרומה', 'yi': 'באארבעטן די נדבה'},
    'Scheduled amount': {'he': 'סכום קבוע', 'yi': 'באשטימטע סכום'},
    'Gross processed': {'he': 'סכום ברוטו', 'yi': 'ברוטא באארבעט'},
    'Processing fees': {'he': 'עמלות סליקה', 'yi': 'פראסעסינג קאסטן'},
    'Net received': {'he': 'נטו שהתקבל', 'yi': 'נעטא באקומען'},
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
