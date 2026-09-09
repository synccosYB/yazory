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
    'Rabbi for this shul': {'he': 'רב בית הכנסת', 'yi': 'רב פון דעם שול'},
    'Gabbaim for this shul': {'he': 'גבאים לבית הכנסת', 'yi': 'גבאים פאר דעם שול'},
    '+ Add gabbai': {'he': '+ הוסף גבאי', 'yi': '+ לייג צו א גבאי'},
    'Gabbai phone': {'he': 'טלפון הגבאי', 'yi': 'גבאי טעלעפאן'},
    'Rabbi source': {'he': 'מקור הרב', 'yi': 'רב מקור'},
    'Use shul connected rabbi': {'he': 'השתמש ברב המקושר לבית הכנסת', 'yi': 'נוץ דעם רב פארבונדן צום שול'},
    'Enter rabbi manually': {'he': 'הזן רב ידנית', 'yi': 'שרייב דעם רב אליין'},
    'Choose directory rabbi': {'he': 'בחר רב מהמאגר', 'yi': 'קלייב א רב פונעם רשימה'},
    'Directory rabbi': {'he': 'רב מהמאגר', 'yi': 'רב פונעם רשימה'},
    'Rabbis': {'he': 'רבנים', 'yi': 'רבנים'},
    'Primary': {'he': 'ראשי', 'yi': 'הויפט'},
    'Make primary': {'he': 'הגדר כראשי', 'yi': 'מאך הויפט'},
    'No rabbis connected.': {'he': 'אין רבנים מקושרים.', 'yi': 'קיין רבנים זענען נישט פארבונדן.'},
    'Connect rabbi': {'he': 'קשר רב', 'yi': 'פארבינד א רב'},
    'Existing rabbi': {'he': 'רב קיים', 'yi': 'עקזיסטירנדיקער רב'},
    'Add new rabbi': {'he': 'הוסף רב חדש', 'yi': 'לייג צו א נייעם רב'},
    'Rabbi name': {'he': 'שם הרב', 'yi': 'רב נאמען'},
    'Rabbi connected.': {'he': 'הרב קושר.', 'yi': 'דער רב איז פארבונדן.'},
    '+ Add phone': {'he': '+ הוסף טלפון', 'yi': '+ לייג צו א טעלעפאן'},
    'Rabbi assistants / gabbaim': {
        'he': 'עוזרי הרב / גבאים', 'yi': 'רב׳ס געהילפן / גבאים'},
    '+ Add rabbi assistant': {
        'he': '+ הוסף עוזר לרב', 'yi': '+ לייג צו א רב׳ס געהילף'},
    'Rabbi assistant / gabbai': {
        'he': 'עוזר הרב / גבאי', 'yi': 'רב׳ס געהילף / גבאי'},
    'Assistant phone': {
        'he': 'טלפון העוזר', 'yi': 'טעלעפאן פונעם געהילף'},
    'Applicant home phone': {
        'he': 'טלפון הבית של הפונה', 'yi': 'היים טעלעפאן פונעם אפליקאנט'},
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
