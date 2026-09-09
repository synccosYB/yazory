from flask import session
from translations_original import LANGUAGES, translate as _translate, translate_audit

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
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
