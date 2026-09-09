from flask import session
from translations_original import LANGUAGES, translate as _translate, translate_audit

_EXTRA = {
    'Shul friend': {
        'he': 'חבר מבית הכנסת',
        'yi': 'חבר פון שול',
    },
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
