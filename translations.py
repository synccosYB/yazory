"""Shared UI translations. Stored records and workflow values remain unchanged."""
from flask import session

LANGUAGES = {'en': 'English', 'he': 'עברית', 'yi': 'אידיש'}
# English | Hebrew | Heimish Yiddish
_ROWS = '''
Overview|לוח בקרה|איבערבליק
Families|משפחות|משפחות
Family|משפחה|משפחה
Expenses & approvals|הוצאות ואישורים|הוצאות און באשטעטיגונגען
Activity log|יומן פעילות|וואס מען האט געטון
A circle of support.|מעגל של תמיכה.|א קרייז פון הילף.
WORKSPACE|סביבת עבודה|ארבעטס פלאץ
Yazory team|צוות יעזורי|די יעזורי שטאב
Demo workspace|סביבת הדגמה|דעמא
Staff workspace|סביבת צוות|פאר די שטאב
Family support /|תמיכה במשפחות /|הילף פאר משפחות /
Initial release|גרסה ראשונה|ערשטע ווערסיע
Sign out|התנתקות|ארויסגיין
DEMO WORKSPACE · Use fictional information only. Pledges and payment records do not move money.|הדגמה בלבד · יש להזין פרטים לדוגמה בלבד. רישום התחייבויות ותשלומים אינו מעביר כסף.|נאר א דעמא · לייגט נאר אריין אויסגעטראכטע פרטים. צוזאגן און פארשרייבונגען שיקן נישט קיין געלט.
Yazory · Helping families keep everyday life together.|יעזורי · עוזרים למשפחות להמשיך בשגרת החיים.|יעזורי · מיר העלפן משפחות מיטן טאג טעגליכן לעבן.
THE BIG PICTURE|התמונה הכוללת|דער גאנצער בילד
Every family. A little more supported.|לכל משפחה, עוד קצת תמיכה.|יעדע משפחה. מיט נאך אביסל הילף.
Keep care, community, and everyday expenses connected.|מרכזים את הטיפול, הקהילה והוצאות היום־יום במקום אחד.|די משפחה, די העלפער און די הוצאות, אלעס אויף איין פלאץ.
+ New family|+ משפחה חדשה|+ נייע משפחה
Active families|משפחות פעילות|אקטיווע משפחות
Cases receiving support|תיקים המקבלים תמיכה|משפחות וואס באקומען הילף
Monthly pledges|התחייבויות חודשיות|חודש׳ליכע צוזאגן
Active cases · pledged, not collected|תיקים פעילים · התחייבויות שטרם נגבו|אקטיווע משפחות · צוגעזאגט, נישט איינגעקומען
Approved this month|אושר החודש|באשטעטיגט דעם חודש
Includes paid expenses|כולל הוצאות ששולמו|מיט די שוין באצאלטע הוצאות
Paid this month|שולם החודש|באצאלט דעם חודש
Recorded against|נרשם עבור|פארשריבן פאר
Family directory|רשימת משפחות|רשימת המשפחות
The people at the heart of the work.|המשפחות שבמרכז העשייה.|די משפחות פאר וועמען מיר ארבעטן.
View all →|הצגת הכול →|אלעס ווייזן →
Needs attention|דורש טיפול|דארף אויפמערקזאמקייט
You’re all caught up.|הכול מעודכן.|אלעס איז מסודר.
No expense requests waiting.|אין בקשות להוצאות הממתינות לטיפול.|עס ווארטן נישט קיין בקשות פאר הוצאות.
Review expense requests →|בדיקת בקשות להוצאות →|איבערקוקן די בקשות →
SMALL COMMITMENTS. MEANINGFUL SUPPORT.|התחייבויות קטנות. תמיכה משמעותית.|קליינע צוזאגן. א גרויסע הילף.
A family should be able to focus on healing.|כדי שהמשפחה תוכל להתמקד בהחלמה.|די משפחה זאל זיך קענען אפגעבן מיט דער רפואה.
Bring relatives and friends together to help cover tuition, groceries, and the daily costs that don’t stop during illness.|מחברים קרובים וחברים לסיוע בשכר לימוד, מזון והוצאות היום־יום שאינן פוסקות בזמן מחלה.|מען נעמט צוזאם קרובים און חברים צו העלפן מיט שכר לימוד, גראסערי און די טאג טעגליכע הוצאות בשעת דער מחלה.
CASE MANAGEMENT|ניהול תיקים|פארוואלטן די משפחות
One profile for the household and its circle of support.|פרופיל אחד למשק הבית ולמעגל התומכים.|אלע פרטים פון דער משפחה און אירע העלפער אויף איין פלאץ.
Search families|חיפוש משפחות|זוכן משפחות
Search family name…|חיפוש שם משפחה…|זוכט א משפחה…
Search|חיפוש|זוכן
Community contact|איש קשר בקהילה|קשר אין דער קהילה
Children|ילדים|קינדער
Case status|מצב התיק|וואו די משפחה האלט
View →|צפייה →|אריינקוקן →
Not entered|לא הוזן|נאך נישט אריינגעלייגט
No families yet. Start with a new family intake.|אין משפחות עדיין. התחילו בקליטת משפחה חדשה.|נאך נישטא קיין משפחות. הייבט אן מיט א נייע משפחה.
FAMILY INTAKE|קליטת משפחה|ארייננעמען א משפחה
New family intake|קליטת משפחה חדשה|ארייננעמען א נייע משפחה
Edit family profile|עריכת פרופיל משפחה|ענדערן די פרטים פון דער משפחה
Start with the household, then add schools, supporters, and expenses.|התחילו בפרטי המשפחה, ולאחר מכן הוסיפו מוסדות לימוד, תומכים והוצאות.|הייבט אן מיט די משפחה, דערנאך לייגט צו מוסדות, העלפער און הוצאות.
Household & community|המשפחה והקהילה|די משפחה און די קהילה
Family / individual name|שם המשפחה / הפונה|נאמען פון דער משפחה אדער דעם פונה
Spouse name|שם בן/בת הזוג|נאמען פונעם מאן אדער די ווייב
Phone|טלפון|טעלעפאן
Address|כתובת|אדרעס
Father|אב|טאטע
In-laws|מחותנים|שווער און שוויגער
Affiliated rabbi|רב המשפחה|דער רב פון דער משפחה
Weekday shul|בית הכנסת בימי חול|וואו מען דאוונט אינדערוואכן
Shabbos shul|בית הכנסת בשבת|וואו מען דאוונט שבת
Household circumstances|מצב המשפחה|די מצב פון דער משפחה
Describe the household’s practical support needs.|תארו את צורכי הסיוע של המשפחה.|שרייבט מיט וואס די משפחה דארף הילף.
Cancel|ביטול|צוריק
Save|שמירה|אפהיטן
profile|פרופיל|די פרטים
intake|קליטה|די נייע משפחה
· FAMILY PROFILE|· פרופיל משפחה|· פרטים פון דער משפחה
Address not entered|לא הוזנה כתובת|נאך נישטא קיין אדרעס
Phone not entered|לא הוזן טלפון|נאך נישטא קיין טעלעפאן
Edit profile|עריכת פרופיל|ענדערן די פרטים
Monthly pledged:|התחייבות חודשית:|צוגעזאגט א חודש:
Move case to|העברת התיק למצב|טוישן דעם מצב צו
Update status|עדכון מצב|אפהיטן דעם מצב
Spouse|בן/בת זוג|מאן אדער ווייב
Rabbi|רב|רב
No circumstances recorded.|לא נרשם תיאור מצב.|נאך נישט פארשריבן די מצב.
Children & schools|ילדים ומוסדות לימוד|קינדער און מוסדות
Child|ילד/ה|קינד
Age / grade|גיל / כיתה|עלטער / כיתה
School|מוסד לימודים|מוסד
Tuition contact|איש קשר לשכר לימוד|קשר פאר שכר לימוד
Add the children’s schools and tuition contacts.|הוסיפו מוסדות לימוד ואנשי קשר לשכר לימוד.|לייגט צו די מוסדות און מיט וועמען מען רעדט וועגן שכר לימוד.
+ Add child & school|+ הוספת ילד ומוסד|+ צולייגן א קינד און מוסד
Child name *|שם הילד/ה *|נאמען פונעם קינד *
Age *|גיל *|עלטער *
Grade|כיתה|כיתה
School *|מוסד לימודים *|מוסד *
Tuition department contact|איש קשר במחלקת שכר לימוד|קשר אין דער שכר לימוד אפטיילונג
Name, phone, or email|שם, טלפון או דוא״ל|נאמען, טעלעפאן אדער אימעיל
Add child|הוספת ילד|צולייגן דאס קינד
Circle of support|מעגל התמיכה|דער קרייז פון העלפער
Track relatives, friends, and monthly commitments. Pledges are not received donations.|מעקב אחר קרובים, חברים והתחייבויות חודשיות. התחייבויות אינן תרומות שהתקבלו.|האלט חשבון פון קרובים, חברים און חודש׳ליכע צוזאגן. א צוזאג איז נאכנישט קיין געלט וואס איז אריינגעקומען.
Supporter|תומך|העלפער
Relationship|קרבה|קרבה
Pledge & outreach|התחייבות ויצירת קשר|צוזאג און קשר
Build this family’s circle of support.|בנו את מעגל התמיכה של המשפחה.|נעמט צוזאם די העלפער פאר דער משפחה.
+ Add supporter|+ הוספת תומך|+ צולייגן א העלפער
Name *|שם *|נאמען *
Monthly pledge ($)|התחייבות חודשית ($)|חודש׳ליכער צוזאג ($)
Outreach status|מצב יצירת הקשר|וואו מען האלט מיטן קשר
Add supporter|הוספת תומך|צולייגן דעם העלפער
Expense requests|בקשות להוצאות|בקשות פאר הוצאות
Approval and payment recording are available in|אישור ורישום תשלומים זמינים ב|באשטעטיגן און פארשרייבן באצאלונגען ביי
+ Request expense|+ בקשה להוצאה|+ בעטן אן הוצאה
Category|סוג הוצאה|סארט הוצאה
Payee *|מקבל התשלום *|פאר וועמען מען באצאלט *
Amount ($) *|סכום ($) *|סכום ($) *
Budget month *|חודש תקציב *|פאר וועלכן חודש *
Notes|הערות|הערות
Submit request|שליחת בקשה|אריינגעבן די בקשה
Case activity|פעילות בתיק|וואס מען האט געטון פאר דער משפחה
No activity recorded.|לא נרשמה פעילות.|נאך נישטא קיין פארשרייבונגען.
FINANCIAL SUPPORT|תמיכה כספית|געלט הילף
Review requests, approve support, and record completed payments.|בדיקת בקשות, אישור סיוע ורישום תשלומים שבוצעו.|קוקט איבער בקשות, באשטעטיגט הילף און שרייבט פאר וואס מען האט באצאלט.
All|הכול|אלעס
Marking an expense paid records an external payment. Yazory does not send funds.|סימון הוצאה כשולמה מתעד תשלום חיצוני. יעזורי אינה מעבירה כסף.|ווען מען צייכנט אן באצאלט, שרייבט מען נאר פאר א באצאלונג. יעזורי שיקט נישט קיין געלט.
Family / payee|משפחה / מקבל התשלום|משפחה / פאר וועמען
Month|חודש|חודש
Amount|סכום|סכום
Status|מצב|מצב
Next step|השלב הבא|דער קומענדיגער שריט
Expense action|פעולה בהוצאה|וואס צו טון מיט דער הוצאה
Payment reference (required for Paid)|אסמכתת תשלום (חובה לסימון כשולם)|באצאלונג רעפערענץ (פאר באצאלט)
Payment reference|אסמכתת תשלום|באצאלונג רעפערענץ
Complete|הושלם|פארטיג
No expenses here.|אין הוצאות להצגה.|נישטא דא קיין הוצאות.
ACCOUNTABILITY|שקיפות ומעקב|קלארקייט און חשבון
The latest 200 changes, with the staff identity and UTC timestamp.|200 השינויים האחרונים, עם זהות איש הצוות ושעת UTC.|די לעצטע 200 ענדערונגען, ווער עס האט עס געטון און די צייט אין UTC.
View family →|צפייה במשפחה →|אריינקוקן אין דער משפחה →
YAZORY STAFF|צוות יעזורי|די יעזורי שטאב
Welcome back.|ברוכים השבים.|ברוכים הבאים.
Sign in to your family support workspace.|כניסה למערכת התמיכה במשפחות.|גייט אריין צו דער ארבעט פאר די משפחות.
Email|דוא״ל|אימעיל
Password|סיסמה|פעסווארד
Sign in|כניסה|אריינגיין
Staff sign in|כניסת צוות|אריינגיין פאר די שטאב
Return to overview|חזרה ללוח הבקרה|צוריק צום איבערבליק
Unable to complete request|לא ניתן להשלים את הבקשה|מען קען נישט ענדיגן די בקשה
Intake|קליטה|נייע פניה
Under review|בבדיקה|מען קוקט איבער
Active|פעיל|אקטיוו
Paused|מושהה|דערווייל אפגעשטעלט
Closed|סגור|פארמאכט
Declined|נדחה|אפגעזאגט
Requested|התבקש|געבעטן
Approved|אושר|באשטעטיגט
Paid|שולם|באצאלט
Voided|בוטל|אנולירט
To contact|ליצירת קשר|מען דארף זיך פארבינדן
Contacted|נוצר קשר|מען האט גערעדט
Pledged|התחייב|צוגעזאגט
Sibling|אח/אחות|ברודער אדער שוועסטער
Spouse’s sibling|אח/אחות של בן/בת הזוג|ברודער אדער שוועסטער פון דער ווייב אדער מאן
First cousin|בן/בת דוד מדרגה ראשונה|ערשטע קאזין
Second cousin|בן/בת דוד מדרגה שנייה|צווייטע קאזין
Yeshivah / school friend|חבר מהישיבה / מבית הספר|חבר פון ישיבה אדער שולע
Friend|חבר|חבר
Other|אחר|אנדערע
Tuition|שכר לימוד|שכר לימוד
Groceries|מזון ומכולת|גראסערי
Butcher|בשר|בוטשער
Rent / mortgage|שכירות / משכנתה|רענט / מארטגעדזש
Utilities|חשבונות הבית|לעקטער, גאז און וואסער
Transportation|תחבורה|פארן
Organization expense|הוצאות הארגון|הוצאות פון דער ארגאניזאציע
Family intake saved.|קליטת המשפחה נשמרה.|די נייע משפחה איז אפגעהיטן.
Profile updated.|הפרופיל עודכן.|די פרטים זענען אפגעהיטן.
Email or password is incorrect.|הדוא״ל או הסיסמה שגויים.|דער אימעיל אדער פעסווארד איז נישט ריכטיג.
Choose language|בחירת שפה|אויסקלויבן א שפראך
STAFF ADMINISTRATION|ניהול צוות|פארוואלטן שטאב
Staff & assignments|צוות ושיבוצים|שטאב און צוטיילונגען
Organization administrators control accounts and explicit family access.|מנהלי ארגון מנהלים חשבונות והרשאות מפורשות למשפחות.|ארגאניזאציע־מנהלים פירן חשבונות און קלארע צוטריט צו משפחות.
Add staff account|הוספת חשבון צוות|צולייגן א שטאב־חשבון
Create staff account|יצירת חשבון צוות|שאפן שטאב־חשבון
Staff accounts|חשבונות צוות|שטאב־חשבונות
Role|תפקיד|ראָלע
Organization administrator|מנהל ארגון|ארגאניזאציע־מנהל
Family administrator|מנהל משפחות|משפחה־מנהל
Assign / revoke family|שיבוץ / ביטול משפחה|צוטיילן / אוועקנעמען משפחה
No family assignments.|אין שיבוצים למשפחות.|נישטא קיין צוטיילונגען צו משפחות.
Staff account created.|חשבון הצוות נוצר.|דער שטאב־חשבון איז געשאפן.
Organization administrator access is required.|נדרשת הרשאת מנהל ארגון.|מען דארף צוטריט פון אן ארגאניזאציע־מנהל.
You are not assigned to this family.|אינך משובץ למשפחה זו.|איר זענט נישט צוגעטיילט צו דער משפחה.
Only family administrators can receive family assignments.|רק מנהלי משפחות יכולים לקבל שיבוץ למשפחות.|נאר משפחה־מנהלים קענען באקומען צוטיילונגען צו משפחות.
Choose a valid role and a password of at least 12 characters.|בחרו תפקיד תקין וסיסמה של 12 תווים לפחות.|קלויבט א גילטיגע ראָלע און א פעסווארד פון כאטש 12 אותיות.
A staff account already uses this email.|חשבון צוות כבר משתמש בדוא״ל זה.|א שטאב־חשבון נוצט שוין דעם אימעיל.
Owner|בעלים|אייגנטימער
The owner organization administrator cannot be demoted.|לא ניתן להוריד את דרגת מנהל הארגון הבעלים.|מען קען נישט אראפנעמען די ראָלע פונעם אייגנטימער ארגאניזאציע־מנהל.
At least one organization administrator is required.|נדרש לפחות מנהל ארגון אחד.|מען דארף האבן כאטש איין ארגאניזאציע־מנהל.
Office employee|עובד/ת משרד|אפיס־ארבעטער
Fundraiser|מגייס/ת תרומות|געלט־זאמלער
Fundraising workspace|מרחב גיוס תרומות|געלט־זאמלער ארבעטס פלאץ
FUNDRAISING|גיוס תרומות|געלט זאמלען
Assigned family supporter outreach and pledges.|מעקב פניות והתחייבויות של תומכי משפחות משובצות.|קשר מיט העלפער און צוזאגן פון צוגעטיילטע משפחות.
Reference|מספר סימוכין|רעפערענץ
Return to fundraising|חזרה לגיוס תרומות|צוריק צו געלט זאמלען
Organization administrators do not use family assignments.|מנהלי ארגון אינם משתמשים בשיבוצי משפחות.|ארגאניזאציע־מנהלים ניצן נישט קיין משפחה צוטיילונגען.
You do not have permission for this action.|אין לך הרשאה לפעולה זו.|איר האט נישט קיין רשות פאר דעם.
Documents|מסמכים|דאקומענטן
No documents uploaded.|לא הועלו מסמכים.|קיין דאקומענטן זענען נישט ארויפגעלייגט.
PDF, PNG, or JPEG document|מסמך PDF, PNG או JPEG|א PDF, PNG, אדער JPEG דאקומענט
Upload document|העלאת מסמך|ארויפלייגן דאקומענט
Delete|מחיקה|אויסמעקן
Choose a PDF, PNG, or JPEG document.|בחרו מסמך PDF, PNG או JPEG.|קלויבט א PDF, PNG, אדער JPEG דאקומענט.
Document must be between 1 byte and 8 MB.|המסמך חייב להיות בגודל שבין בית אחד ל־8 MB.|דער דאקומענט מוז זיין צווישן 1 בייט און 8 MB.
The document filename extension does not match its contents.|סיומת שם המסמך אינה תואמת לתוכנו.|דער דאקומענט נאמען־ענדונג שטימט נישט מיט זיין אינהאלט.
'''
CATALOG = {row.split('|')[0]:dict(zip(('he','yi'),row.split('|')[1:])) for row in _ROWS.strip().splitlines()}

def translate(text):
    return CATALOG.get(text, {}).get(session.get('language', 'en'), text)

AUDIT_PREFIXES = {
    'Updated staff role for ': {
        'he': 'עודכן תפקיד הצוות עבור ',
        'yi': 'מען האט געטוישט די שטאב ראלע פאר ',
    },
    'Assigned family administrator: ': {
        'he': 'הוקצה מנהל משפחה: ',
        'yi': 'צוגעטיילט א משפחה אדמיניסטראטאר: ',
    },
    'Revoked family administrator: ': {
        'he': 'בוטלה הקצאת מנהל משפחה: ',
        'yi': 'אוועקגענומען א משפחה אדמיניסטראטאר: ',
    },
    'Assigned staff member: ': {
        'he': 'הוקצה איש צוות: ',
        'yi': 'צוגעטיילט א שטאב מיטגליד: ',
    },
    'Revoked staff assignment: ': {
        'he': 'בוטל שיבוץ איש צוות: ',
        'yi': 'אוועקגענומען א שטאב צוטיילונג: ',
    },
}

def translate_audit(text):
    language = session.get('language', 'en')
    for prefix, translations in AUDIT_PREFIXES.items():
        if text.startswith(prefix):
            return translations.get(language, prefix) + text[len(prefix):]
    return translate(text)

# Shared sequential intake and compact navigation labels.
_INTAKE_ROWS = '''
Intake steps|שלבי קליטה|די טריט ביים ארייננעמען
Household|משק הבית|די משפחה
Community|קהילה|די קהילה
Children & budget|ילדים ותקציב|קינדער און הוצאות
Employment & income|תעסוקה והכנסות|ארבעט און הכנסות
Assistance|סיוע|הילף
Provider accounts|חשבונות ספקים|קאונטס ביי די פירמעס
Review|בדיקה|איבערקוקן
Back|הקודם|צוריק
Next|הבא|ווייטער
Number of children|מספר ילדים|וויפיל קינדער
Monthly rent or mortgage ($)|שכירות או משכנתה לחודש ($)|חודש׳ליכע רענט אדער מארטגעדזש ($)
Monthly food costs ($)|הוצאות מזון לחודש ($)|חודש׳ליכע הוצאות פאר עסן ($)
Enter monthly amounts in dollars. Leave unknown amounts blank.|יש להזין סכומים חודשיים בדולרים. סכומים שאינם ידועים יש להשאיר ריקים.|לייגט אריין חודש׳ליכע סכומים אין דאלאר. וואס מען ווייסט נישט לאזט ליידיג.
His employment / occupation|תעסוקת הבעל|זיין ארבעט
Her employment / occupation|תעסוקת האישה|איר ארבעט
His employer|מעסיק הבעל|ביי וועמען ער ארבעט
Her employer|מעסיק האישה|ביי וועמען זי ארבעט
His monthly income ($)|הכנסת הבעל לחודש ($)|זיין חודש׳ליכע הכנסה ($)
Her monthly income ($)|הכנסת האישה לחודש ($)|איר חודש׳ליכע הכנסה ($)
Other monthly income ($)|הכנסה חודשית נוספת ($)|אנדערע חודש׳ליכע הכנסות ($)
Receiving food stamps?|מקבלים תלושי מזון?|באקומען זיי פוד סטעמפס?
Monthly food stamps ($)|סכום תלושי מזון לחודש ($)|חודש׳ליכע פוד סטעמפס ($)
Choose…|בחרו…|קלויבט אויס…
Yes|כן|יא
No|לא|ניין
Other assistance|סיוע נוסף|אנדערע הילף
Accounts|חשבונות|קאונטס
Add assistance|הוספת סיוע|צולייגן הילף
Add account|הוספת חשבון|צולייגן א קאונט
No entries yet. Add only what applies.|אין רשומות עדיין. הוסיפו רק את הנדרש.|נאך גארנישט אריינגעלייגט. לייגט צו נאר וואס איז שייך.
Account type|סוג חשבון|סארט קאונט
Utility company|חברת שירותים|יוטיליטי פירמע
Grocery store|חנות מכולת|גראסערי
Mosdos / school|מוסד לימודים|מוסד
Organization / provider name|שם הארגון או הספק|נאמען פון דער ארגאניזאציע אדער פירמע
Monthly assistance ($)|סכום הסיוע לחודש ($)|חודש׳ליכע הילף ($)
Account number|מספר חשבון|קאונט נומער
Contact phone|טלפון ליצירת קשר|טעלעפאן פאר קשר
Child / account holder|ילד או בעל החשבון|קינד אדער בעל הקאונט
Previous entry|רשומה קודמת|פריערדיגע איינטראג
Next entry|רשומה הבאה|קומענדיגע איינטראג
Remove entry|הסרת רשומה|אראפנעמען די איינטראג
Add your own utility companies, grocery stores and mosdos. No providers are prefilled.|הוסיפו חברות שירותים, חנויות מכולת ומוסדות לפי הצורך. אין ספקים שמולאו מראש.|לייגט צו אייערע יוטיליטי פירמעס, גראסעריס און מוסדות. קיין נעמען זענען נישט פאראויס אנגעפילט.
Use the step buttons to check or change details before saving.|השתמשו בכפתורי השלבים לבדיקה או לשינוי לפני השמירה.|נוצט די קנעפלעך פון די טריט צו איבערקוקן אדער טוישן פארן אפהיטן.
Enable JavaScript to complete the step-by-step intake.|יש להפעיל JavaScript להשלמת הקליטה בשלבים.|מען דארף אנצינדן JavaScript צו אויספילן די טריט.
Intake text is too long.|הטקסט בטופס ארוך מדי.|דער טעקסט איז צו לאנג.
Number of children must be between 0 and 50.|מספר הילדים חייב להיות בין 0 ל־50.|די צאל קינדער מוז זיין צווישן 0 און 50.
Choose Yes or No for food stamps.|בחרו כן או לא עבור תלושי מזון.|קלויבט יא אדער ניין פאר פוד סטעמפס.
Enter the monthly food stamp amount.|הזינו את סכום תלושי המזון החודשי.|לייגט אריין דעם חודש׳ליכן סכום פוד סטעמפס.
Invalid account or assistance entry.|רשומת חשבון או סיוע אינה תקינה.|די איינטראג פאר קאונט אדער הילף איז נישט ריכטיג.
Enter the provider or organization name.|הזינו את שם הספק או הארגון.|לייגט אריין דעם נאמען פון דער פירמע אדער ארגאניזאציע.
Enter the monthly assistance amount.|הזינו את סכום הסיוע החודשי.|לייגט אריין דעם חודש׳ליכן סכום הילף.
Choose an account type.|בחרו סוג חשבון.|קלויבט אויס א סארט קאונט.
Profile sections|חלקי הפרופיל|די טיילן פון די פרטים
Household budget & accounts|תקציב המשפחה וחשבונות|הוצאות און קאונטס פון דער משפחה
Review or update income, assistance and provider accounts in the intake steps.|בדקו או עדכנו הכנסות, סיוע וחשבונות בשלבי הקליטה.|קוקט איבער אדער טוישט הכנסות, הילף און קאונטס אין די טריט.
'''
for _row in _INTAKE_ROWS.strip().splitlines():
    _en, _he, _yi = _row.split('|')
    CATALOG[_en] = {'he': _he, 'yi': _yi}

CATALOG.update({
 'Receiving other assistance?': {'he':'מקבלים סיוע נוסף?', 'yi':'באקומען זיי נאך אנדערע הילף?'},
 'Choose Yes or No for other assistance.': {'he':'בחרו כן או לא עבור סיוע נוסף.', 'yi':'קלויבט יא אדער ניין פאר אנדערע הילף.'},
 'Add the assistance source and monthly amount.': {'he':'הוסיפו את מקור הסיוע והסכום החודשי.', 'yi':'לייגט צו פון וועמען די הילף קומט און דעם חודש׳ליכן סכום.'}
})
