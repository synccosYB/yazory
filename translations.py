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
    'Applicant information': {'he': 'פרטי הפונה', 'yi': 'די פרטים פונעם אפליקאנט'},
    'Save changes': {'he': 'שמירת השינויים', 'yi': 'אפהיטן די ענדערונגען'},
    'Intake sections': {'he': 'חלקי הקליטה', 'yi': 'טיילן פון דער בקשה'},
    'Family & community': {'he': 'המשפחה והקהילה', 'yi': 'די משפחה און די קהילה'},
    'Children & monthly costs': {'he': 'ילדים והוצאות חודשיות', 'yi': 'קינדער און חודש׳ליכע הוצאות'},
    'Debts & provider accounts': {'he': 'חובות וחשבונות ספקים', 'yi': 'חובות און קאונטס ביי די פירמעס'},
    'Applicant, household and community connections': {'he': 'פרטי המשפחה והקשרים בקהילה', 'yi': 'די משפחה און אירע קשרים אין דער קהילה'},
    'Record work and monthly household income together.': {'he': 'רשמו יחד את העבודה וההכנסה החודשית של המשפחה.', 'yi': 'לייגט צוזאם די ארבעט און די חודש׳ליכע הכנסות.'},
    'Record every source of regular help.': {'he': 'רשמו כל מקור של סיוע קבוע.', 'yi': 'לייגט אריין יעדע קביעות׳דיגע הילף.'},
    'Add utility companies, grocery stores, mosdos and other accounts.': {'he': 'הוסיפו חברות שירותים, חנויות מזון, מוסדות וחשבונות נוספים.', 'yi': 'לייגט צו יוטיליטי פירמעס, גראסעריס, מוסדות און אנדערע קאונטס.'},
    'Previous section': {'he': 'החלק הקודם', 'yi': 'דער פריערדיגער טייל'},
    'Next section': {'he': 'החלק הבא', 'yi': 'דער קומענדיגער טייל'},
    'Monthly summary': {'he': 'סיכום חודשי', 'yi': 'חודש׳ליכער סך הכל'},
    'Intake completeness': {'he': 'השלמת הקליטה', 'yi': 'וויפיל פון דער בקשה איז אויסגעפילט'},
    'Enable JavaScript to use the compact intake sections.': {'he': 'יש להפעיל JavaScript כדי להשתמש בחלקי הקליטה המרוכזים.', 'yi': 'JavaScript דארף זיין אנגעצונדן צו נוצן די קורצע טיילן פון דער בקשה.'},
    'ABCharity API key': {'he': 'מפתח API של ABCharity', 'yi': 'ABCharity API שליסל'},
    'Paste this campaign’s ABCharity API key. It will be encrypted and never shown again.': {'he': 'הדביקו את מפתח ה־API של הקמפיין. הוא יוצפן ולא יוצג שוב.', 'yi': 'לייגט אריין דעם ABCharity API שליסל פונעם קאמפיין. ער ווערט פארשלאסן און וועט מער נישט ווערן געוויזן.'},
    'Saved securely — leave blank to keep it': {'he': 'נשמר באופן מאובטח — השאירו ריק כדי לשמור אותו', 'yi': 'זיכער אפגעהיטן — לאזט ליידיג עס צו האלטן'},
    'Paste the campaign API key': {'he': 'הדביקו את מפתח ה־API של הקמפיין', 'yi': 'לייגט אריין דעם API שליסל פונעם קאמפיין'},
    'Save and test connection': {'he': 'שמירה ובדיקת החיבור', 'yi': 'אפהיטן און פרובירן דעם פארבינדונג'},
    'An encrypted API key is saved for this family.': {'he': 'מפתח API מוצפן שמור עבור משפחה זו.', 'yi': 'א פארשלאסענער API שליסל איז אפגעהיטן פאר דער משפחה.'},
    'Enter the ABCharity API key for this campaign.': {'he': 'הזינו את מפתח ה־API של ABCharity לקמפיין זה.', 'yi': 'לייגט אריין דעם ABCharity API שליסל פאר דעם קאמפיין.'},
    'ABCharity could not be synced. Check the campaign ID and API response.': {'he': 'לא ניתן לסנכרן את ABCharity. בדקו את מזהה הקמפיין ואת תגובת ה־API.', 'yi': 'ABCharity האט זיך נישט אפדעיטעד. קוקט איבער דעם קאמפיין נומער און דעם API ענטפער.'},
    'The saved ABCharity API key could not be read. Enter and save the key again.': {'he': 'לא ניתן לקרוא את מפתח ה־API השמור. הזינו ושמרו את המפתח מחדש.', 'yi': 'מען קען נישט ליינען דעם אפגעהיטענעם ABCharity API שליסל. לייגט אריין און היט אפ דעם שליסל נאכאמאל.'},
}

def translate(text):
    extra = _EXTRA.get(text)
    if extra:
        return extra.get(session.get('language', 'en'), text)
    return _translate(text)
