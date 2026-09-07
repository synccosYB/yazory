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
Street address|כתובת רחוב|הויז אדרעס
City|עיר|שטאט
State|מדינה|סטעיט
ZIP code|מיקוד|זיפ קאוד
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
Donation amount ($)|סכום התרומה ($)|סכום פון די נדבה ($)
Donation amount|סכום התרומה|סכום פון די נדבה
Donation frequency|תדירות התרומה|ווי אפט די נדבה
Donation commitment|התחייבות לתרומה|צוזאג פון די נדבה
Donation commitments|התחייבויות לתרומות|צוזאגן פון נדבות
Donation & outreach|תרומה ויצירת קשר|נדבה און קשר
Weekly|שבועי|וועכנטליך
Monthly|חודשי|חודש׳ליך
One time|חד-פעמי|איין מאל
Track relatives, friends, and recurring or one-time commitments. A supporter connected to multiple cases is charged only once.|מעקב אחר קרובים, חברים והתחייבויות קבועות או חד-פעמיות. תומך המחובר למספר תיקים מחויב פעם אחת בלבד.|האלט חשבון פון קרובים, חברים און וועכנטליכע, חודש׳ליכע אדער איינמאליגע צוזאגן. א העלפער וואס איז פארבונדן מיט מער ווי איין משפחה ווערט נאר איינמאל געבעטן.
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
Nephew|אחיין|פלימעניק
Children & spouses|ילדים ובני זוג|קינדער און זייערע מאן אדער ווייב
Niece / nephew of applicant|אחיין / אחיינית של הפונה|נעפיו אדער ניס פונעם אנפרעגער
Supporter’s child|ילד של התומך|א קינד פונעם העלפער
Add another child|הוספת ילד נוסף|צולייגן נאך א קינד
This child is already listed under this supporter.|הילד הזה כבר רשום תחת התומך הזה.|דאס קינד שטייט שוין אונטער דעם העלפער.
Spouse’s sibling|אח/אחות של בן/בת הזוג|ברודער אדער שוועסטער פון דער ווייב אדער מאן
In-law’s maiden family|משפחת הנעורים של החותנים|די מיידל נאמען משפחה פון די מחותנים
In-law maiden name|שם הנעורים של החותנים|די מיידל נאמען פון די מחותנים
In-law maiden family / network|משפחת הנעורים ורשת הקשרים של החותנים|די מיידל נאמען משפחה און זייער נעטווארק
Father-in-law|חותן|שווער
Mother-in-law’s maiden name|שם הנעורים של החמות|די מיידל נאמען פון דער שוויגער
Mother-in-law’s family / network|משפחת הנעורים ורשת הקשרים של החמות|די מיידל נאמען משפחה און נעטווארק פון דער שוויגער
Child’s in-law family|משפחת החותנים של ילד/ה נשוי/אה|די מחותנים משפחה פון א פארהייראט קינד
Children & their spouses|ילדים ובני זוגם|קינדער און זייערע פארפעלקער
Mark which children are married and record the name of each child’s spouse.|סמנו אילו ילדים נשואים ורשמו את שם בן/בת הזוג של כל אחד מהם.|צייכנט אן וועלכע קינדער זענען פארהייראט און שרייבט אריין דעם נאמען פון זייער פארפאלק.
Children, spouses & mechutanim|ילדים, בני זוג ומחותנים|קינדער, זייערע פארפעלקער און מחותנים
For each married child, record the spouse and the spouse’s parents so the family’s mechutanim are clear.|לכל ילד/ה נשוי/אה, רשמו את בן/בת הזוג ואת הוריו/ה כדי שיהיה ברור מי הם המחותנים של המשפחה.|ביי יעדן פארהייראטן קינד, שרייבט אריין דעם פארפאלק און די עלטערן פונעם פארפאלק, אזוי זאל מען קלאר וויסן ווער די מחותנים זענען.
Married?|נשוי/אה?|פארהייראט?
Spouse name|שם בן/בת הזוג|נאמען פונעם פארפאלק
Spouse’s father (mechutan)|אבי בן/בת הזוג (מחותן)|דער טאטע פונעם פארפאלק (מחותן)
Spouse’s mother (mechuteneste)|אם בן/בת הזוג (מחותנת)|די מאמע פונעם פארפאלק (מחותנת)
Spouse’s family name|שם המשפחה של בן/בת הזוג|משפחה נאמען פונעם פארפאלק
Mechutanim|מחותנים|מחותנים
Mechutanim phone|טלפון המחותנים|טלפון פון די מחותנים
Save child & mechutanim|שמירת הילד/ה והמחותנים|אפהיטן קינד און מחותנים
Child and mechutanim updated.|פרטי הילד/ה והמחותנים עודכנו.|די פרטים פונעם קינד און די מחותנים זענען אפגעהיטן.
Updated child and mechutanim details|פרטי הילד/ה והמחותנים עודכנו|פארראכטן די פרטים פונעם קינד און די מחותנים
Add the children, then enter spouse and mechutanim details for each married child.|הוסיפו את הילדים, ולאחר מכן הזינו בן/בת זוג ומחותנים לכל ילד/ה נשוי/אה.|לייגט צו די קינדער, און ביי יעדן פארהייראטן קינד די פרטים פונעם פארפאלק און די מחותנים.
Child and spouse updated.|פרטי הילד/ה ובן/בת הזוג עודכנו.|די פרטים פונעם קינד און פארפאלק זענען אפגעהיטן.
Updated child and spouse details|פרטי הילד/ה ובן/בת הזוג עודכנו|פארראכטן די פרטים פונעם קינד און פארפאלק
Add the children, then mark which children are married and enter their spouses.|הוסיפו את הילדים, לאחר מכן סמנו אילו מהם נשואים והזינו את בני זוגם.|לייגט צו די קינדער, דערנאך צייכנט אן וועלכע זענען פארהייראט און שרייבט אריין זייערע פארפעלקער.
Save child|שמירת הילד/ה|אפהיטן דאס קינד
+ Add child|+ הוספת ילד/ה|+ צולייגן א קינד
connected cases · one charge|תיקים מקושרים · חיוב אחד|פארבינדענע קעיסעס · איין טשארדזש
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
    'Added child under supporter: ': {
        'he': 'נוסף ילד תחת התומך: ',
        'yi': 'צוגעלייגט א קינד אונטער דעם העלפער: ',
    },
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

CATALOG.update({
  'Collections': {'he':'גבייה', 'yi':'געלט אייננעמען'},
  'COLLECTION RECORDS': {'he':'רישומי גבייה', 'yi':'פארשרייבונגען פון געלט'},
  'Monthly commitments and manually recorded receipts. A pledge is never a receipt, and Yazory does not move money.': {'he':'התחייבויות חודשיות וקבלות שנרשמו ידנית. התחייבות אינה קבלה, ויעזורי אינה מעבירה כסף.', 'yi':'חודש׳ליכע צוזאגן און ידנית פארשריבענע קבלות. א צוזאג איז קיינמאל נישט קיין קבלה, און יעזורי שיקט נישט קיין געלט.'},
  'View': {'he':'הצגה', 'yi':'ווייזן'},
  'Monthly due commitments': {'he':'התחייבויות חודשיות לתשלום', 'yi':'חודש׳ליכע צוזאגן וואס קומען'},
  'Follow up manually where a pledged commitment has no recorded receipt.': {'he':'בצעו מעקב ידני כאשר להתחייבות אין קבלה שנרשמה.', 'yi':'מאכט ידנית נאכפאלגן ווען א צוזאג האט נישט קיין פארשריבענע קבלה.'},
  'Monthly pledge': {'he':'התחייבות חודשית', 'yi':'חודש׳ליכער צוזאג'},
  'Received to date': {'he':'התקבל עד כה', 'yi':'אריינגעקומען ביז יעצט'},
  'Follow-up status': {'he':'מצב מעקב', 'yi':'מצב פון נאכפאלגן'},
  'Manual follow-up': {'he':'מעקב ידני', 'yi':'ידנית נאכפאלגן'},
  'Recorded': {'he':'נרשם', 'yi':'פארשריבן'},
  'No assigned supporters or commitments for this month.': {'he':'אין תומכים או התחייבויות משויכים לחודש זה.', 'yi':'נישטא קיין צוגעטיילטע העלפער אדער צוזאגן פאר דעם חודש.'},
  'Record manual receipt': {'he':'רישום קבלה ידני', 'yi':'ידנית פארשרייבן א קבלה'},
  'This documents a receipt reported or handled outside Yazory; it does not move money.': {'he':'זה מתעד קבלה שדווחה או טופלה מחוץ ליעזורי; הוא אינו מעביר כסף.', 'yi':'דאס פארשרייבט א קבלה וואס מען האט געמאלדן אדער באהאנדלט אויסער יעזורי; עס שיקט נישט קיין געלט.'},
  'Received on': {'he':'תאריך קבלה', 'yi':'דאטום באקומען'},
  'Record receipt': {'he':'רישום קבלה', 'yi':'פארשרייבן קבלה'},
  'Receipt history': {'he':'היסטוריית קבלות', 'yi':'היסטאריע פון קבלות'},
  'Manual records only; they are not bank reconciliation.': {'he':'רישומים ידניים בלבד; אין מדובר בהתאמת בנק.', 'yi':'נאר ידנית פארשרייבונגען; דאס איז נישט קיין באנק־אויסגלייך.'},
  'No manual receipts recorded for this month.': {'he':'לא נרשמו קבלות ידניות לחודש זה.', 'yi':'נישטא קיין ידנית פארשריבענע קבלות פאר דעם חודש.'},
  'Manual receipt recorded.': {'he':'הקבלה הידנית נרשמה.', 'yi':'די ידנית קבלה איז פארשריבן.'},
  'Choose a supporter.': {'he':'בחרו תומך.', 'yi':'קלויבט אויס א העלפער.'},
  'Enter a valid received date.': {'he':'הזינו תאריך קבלה תקין.', 'yi':'לייגט אריין א גילטיגע דאטום ווען עס איז באקומען געווארן.'}
})

CATALOG.update({
 'Cases':{'he':'תיקים','yi':'משפחה־תיקים'}, 'Supporters':{'he':'תומכים','yi':'העלפער'}, 'Fundraising':{'he':'גיוס תרומות','yi':'געלט זאמלען'}, 'Expenses':{'he':'הוצאות','yi':'הוצאות'}, 'Approvals':{'he':'אישורים','yi':'באשטעטיגונגען'}, 'Reports':{'he':'דוחות','yi':'באריכטן'}, 'People & access':{'he':'אנשים והרשאות','yi':'מענטשן און רשות'}, 'Controls':{'he':'הגדרות בקרה','yi':'קאנטראָלס'},
 'SUPPORTER NETWORK':{'he':'רשת תומכים','yi':'נעץ פון העלפער'}, 'Assigned supporter relationships, pledges, receipts, and follow-up.':{'he':'קשרי תומכים משויכים, התחייבויות, קבלות ומעקב.','yi':'צוגעטיילטע העלפער, צוזאגן, קבלות און נאכפאלגן.'}, 'Search supporters':{'he':'חיפוש תומכים','yi':'זוכן העלפער'}, 'No supporters found.':{'he':'לא נמצאו תומכים.','yi':'נישט געפונען קיין העלפער.'},
 'APPROVAL QUEUE':{'he':'תור אישורים','yi':'ריי פאר באשטעטיגונגען'}, 'Requested expenses awaiting an organization administrator decision.':{'he':'בקשות הוצאה הממתינות להחלטת מנהל ארגון.','yi':'געבעטן הוצאות וואס ווארטן אויף א באשלוס פון ארגאניזאציע־מנהל.'},
 'SAVED DATA REPORT':{'he':'דוח נתונים שמורים','yi':'באריכט פון אפגעהיטענע דאטא'}, 'Saved-data totals only; blank intake values are not invented.':{'he':'סיכומי נתונים שמורים בלבד; ערכי קליטה ריקים אינם מומצאים.','yi':'נאר סך הכל פון אפגעהיטענע דאטא; ליידיגע ארייננעמען־ווערדן ווערן נישט אויסגעטראכט.'}, 'Household bills':{'he':'חשבונות משק הבית','yi':'חשבונות פון דער משפחה'}, 'Child estimates':{'he':'אומדני ילדים','yi':'שאצונגען פאר קינדער'}, 'Shortfall':{'he':'חסר','yi':'וויפיל עס פעלט'}, 'Received':{'he':'התקבל','yi':'באקומען'}, 'Organization costs':{'he':'עלויות הארגון','yi':'קאסטן פון ארגאניזאציע'}, 'No saved cases.':{'he':'אין תיקים שמורים.','yi':'נישטא קיין אפגעהיטענע תיקים.'},
 'ORGANIZATION CONTROLS':{'he':'הגדרות הארגון','yi':'ארגאניזאציע קאנטראָלס'}, 'Configure categories and monthly child estimates used in saved profile totals.':{'he':'הגדירו קטגוריות ואומדני ילדים חודשיים המשמשים בסיכומי פרופילים שמורים.','yi':'שטעלט איין קאטעגאריעס און חודש׳ליכע קינדער־שאצונגען וואס ווערן גענוצט אין אפגעהיטענע פרטים.'}, 'Expense categories (one per line)':{'he':'קטגוריות הוצאה (אחת בשורה)','yi':'הוצאה קאטעגאריעס (איינער א שורה)'}, 'Child estimate age bands (JSON; amounts are cents)':{'he':'טווחי גיל לאומדן ילדים (JSON; סכומים בסנטים)','yi':'עלטער־גרופעס פאר קינדער שאצונגען (JSON; סכומים זענען סענט)'}, 'Save controls':{'he':'שמירת הגדרות','yi':'אפהיטן קאנטראָלס'}, 'Controls saved.':{'he':'ההגדרות נשמרו.','yi':'די קאנטראָלס זענען אפגעהיטן.'},
 'Monthly shortfall':{'he':'חסר חודשי','yi':'חודש׳ליכער חסר'}, 'Saved intake and configured estimates':{'he':'קליטה שמורה ואומדנים שהוגדרו','yi':'אפגעהיטענע ארייננעמען און איינגעשטעלטע שאצונגען'}, 'Manual receipts':{'he':'קבלות ידניות','yi':'ידנית קבלות'}, 'Recorded manually; not money moved':{'he':'נרשם ידנית; לא הועבר כסף','yi':'ידנית פארשריבן; קיין געלט נישט געשיקט'}, 'Support target':{'he':'יעד תמיכה','yi':'ציל פון הילף'}, 'ABCharity':{'he':'ABCharity','yi':'ABCharity'}, 'Not connected. External actions are unavailable.':{'he':'לא מחובר. פעולות חיצוניות אינן זמינות.','yi':'נישט פארבונדן. דרויסנדיגע פעולות זענען נישט פאראן.'},
 'Total monthly income':{'he':'סך הכנסה חודשית','yi':'סך חודש׳ליכע הכנסה'}, 'Monthly household bills':{'he':'חשבונות בית חודשיים','yi':'חודש׳ליכע חשבונות פון שטוב'}, 'Child age-based estimates':{'he':'אומדנים לפי גיל הילד','yi':'שאצונגען לויטן עלטער פון קינד'}, '(estimate)':{'he':'(אומדן)','yi':'(שאצונג)'}, 'Actual child amounts entered':{'he':'סכומי ילדים בפועל שהוזנו','yi':'פאקטישע קינדער סכומים אריינגעלייגט'}, 'Total shortfall':{'he':'סך החסר','yi':'סך הכל וואס עס פעלט'}, 'Child estimates are shown separately and are not double counted with actual entered amounts.':{'he':'אומדני ילדים מוצגים בנפרד ואינם נספרים פעמיים עם סכומים בפועל שהוזנו.','yi':'קינדער שאצונגען ווערן געוויזן באזונדער און נישט צוויי מאל מיט פאקטישע אריינגעלייגטע סכומים.'}
 ,'Received this month':{'he':'התקבל החודש','yi':'באקומען דעם חודש'}, 'Lifetime received':{'he':'התקבל לאורך הזמן','yi':'באקומען במשך הזמן'}, 'Approved outstanding':{'he':'מאושר שטרם שולם','yi':'באשטעטיגט און נאך נישט באצאלט'}, 'Paid support':{'he':'סיוע ששולם','yi':'באצאלטע הילף'}, 'Paid organization costs':{'he':'עלויות ארגון ששולמו','yi':'באצאלטע ארגאניזאציע קאסטן'}, 'Enter valid child estimate settings.':{'he':'הזינו הגדרות אומדן ילדים תקינות.','yi':'לייגט אריין גילטיגע קינדער־שאצונג קאנטראָלס.'}, 'Choose valid expense categories.':{'he':'בחרו קטגוריות הוצאה תקינות.','yi':'קלויבט אויס גילטיגע הוצאה קאטעגאריעס.'}, 'Amount ($)':{'he':'סכום ($)','yi':'סכום ($)'}
})

CATALOG.update({
 'Profile totals': {'he':'סיכום המשפחה', 'yi':'סך הכל פון די משפחה'},
 'Saved profile': {'he':'הפרופיל נשמר', 'yi':'די פרטים זענען אפגעהיטן'},
 'Unsaved changes': {'he':'שינויים שלא נשמרו', 'yi':'די ענדערונגען זענען נאך נישט אפגעהיטן'},
 'Not saved yet': {'he':'טרם נשמר', 'yi':'נאך נישט אפגעהיטן'},
 'Monthly rent and food': {'he':'שכירות ומזון לחודש', 'yi':'רענט און עסן א חודש'},
 'Monthly income': {'he':'הכנסה חודשית', 'yi':'חודש׳ליכע הכנסות'},
 'Monthly assistance': {'he':'סיוע חודשי', 'yi':'חודש׳ליכע הילף'},
 'Remaining monthly need': {'he':'צורך חודשי שנותר', 'yi':'וויפיל עס פעלט נאך א חודש'},
 'Totals use entered amounts only. Save on the Review step to keep your changes.': {'he':'הסכומים מבוססים רק על הנתונים שהוזנו. שמרו בשלב הסקירה כדי לשמור את השינויים.', 'yi':'די סך הכל רעכנט נאר די אריינגעלייגטע סכומים. דריקט אויפן אפהיטן קנעפל ביים איבערקוקן צו האלטן די ענדערונגען.'}
})

CATALOG.update({
 'Monthly bill ($)': {'he':'סכום החשבון החודשי ($)', 'yi':'וויפיל איז דער ביל א חודש ($)'},
 'Monthly provider bills': {'he':'סך חשבונות הספקים לחודש', 'yi':'סך הכל בילס ביי די פירמעס א חודש'},
 'Provider bills are shown separately from rent and food to avoid counting the same expense twice. Leave unknown amounts blank.': {'he':'חשבונות הספקים מוצגים בנפרד משכירות ומזון כדי למנוע ספירה כפולה. השאירו סכומים לא ידועים ריקים.', 'yi':'די בילס ביי די פירמעס ווערן געוויזן באזונדער פון רענט און עסן, כדי נישט צו רעכענען די זעלבע הוצאה צוויי מאל. אויב מען ווייסט נישט דעם סכום, לאזט ליידיג.'}
})

_REPORT_ROWS = '''
Monthly expense report|דוח הוצאות חודשי|חודש׳ליכער הוצאות באריכט
Current saved monthly budget|התקציב החודשי השמור כעת|דער אפגעהיטענער חודש׳ליכער חשבון
Monthly expenses|הוצאות חודשיות|חודש׳ליכע הוצאות
Expenses above income|הוצאות מעבר להכנסה|וויפיל די הוצאות זענען מער פון די הכנסות
Expense breakdown|פירוט ההוצאות|פירוט פון די הוצאות
Income & assistance|הכנסות וסיוע|הכנסות און הילף
Monthly shortfall|החוסר החודשי|וויפיל עס פעלט א חודש
Monthly surplus|יתרה חודשית|וויפיל עס בלייבט איבער א חודש
Assistance applied to expenses|סיוע שנזקף להוצאות|הילף וואס דעקט די הוצאות
Source|מקור|פון וואו
Count this bill|אופן חישוב החשבון|ווי צו רעכענען דעם ביל
Add to monthly expenses|להוסיף להוצאות החודשיות|צולייגן צו די חודש׳ליכע הוצאות
Already included in food|כבר נכלל במזון|שוין אריינגערעכנט אין עסן
Already included in rent|כבר נכלל בשכירות|שוין אריינגערעכנט אין רענט
Choose how to count this bill|בחרו כיצד לחשב חשבון זה|קלויבט ווי צו רעכענען דעם ביל
Choose whether each bill is additional or already included in rent or food. Unclassified bills are excluded from totals.|בחרו אם כל חשבון הוא הוצאה נוספת או כבר נכלל בשכירות או במזון. חשבונות שלא סווגו אינם נכללים בסכום.|קלויבט צי דער ביל איז א באזונדערע הוצאה אדער שוין אריינגערעכנט אין רענט אדער עסן. אן דעם ווערט דער ביל נישט מיטגערעכנט.
Bills already included in rent or food are listed but not added again.|חשבונות שכבר נכללים בשכירות או במזון מוצגים אך אינם נספרים שוב.|בילס וואס זענען שוין אריינגערעכנט אין רענט אדער עסן ווערן נישט נאכאמאל צוגערעכנט.
Incomplete budget: totals use known amounts only. Enter missing amounts and classify each bill before relying on the shortfall.|התקציב אינו מלא: הסכומים מבוססים רק על נתונים ידועים. יש להשלים סכומים ולסווג כל חשבון לפני הסתמכות על החוסר.|דער חשבון איז נאך נישט פולשטענדיג. נאר די באקאנטע סכומים זענען מיטגערעכנט. פילט אויס די פעלנדע סכומים און קלויבט ווי צו רעכענען יעדן ביל, כדי צו וויסן וויפיל עס פעלט.
Remaining need equals expenses minus income and applicable assistance. Food stamps offset food costs only. Pledges and expense requests are not added to this budget.|הצורך שנותר הוא ההוצאות פחות ההכנסה והסיוע שניתן לנצל. תלושי מזון מקוזזים רק מהוצאות מזון. התחייבויות לתרומה ובקשות תשלום אינן מתווספות לתקציב זה.|וואס עס פעלט איז די הוצאות ווייניגער די הכנסות און די הילף וואס מען קען נוצן. פוד סטעמפס רעכענען זיך נאר קעגן עסן. צוגעזאגטע נדבות און בקשות פאר צאלונגען ווערן נישט צוגערעכנט אין דעם חשבון.
'''
for _row in _REPORT_ROWS.strip().splitlines():
    _en, _he, _yi = _row.split('|')
    CATALOG[_en] = {'he': _he, 'yi': _yi}

_CHILD_BUDGET_ROWS = '''
Housing|דיור|וואוינונג
Property taxes|ארנונה ומסי נכס|פראפערטי טעקס
Phone and internet|טלפון ואינטרנט|טעלעפאן און אינטערנעט
Groceries and household supplies|מזון ומוצרי בית|גראסערי און זאכן פארן שטוב
Childcare|טיפול בילדים|בעיביסיטינג
Insurance|ביטוח|אינשורענס
Medical|רפואה|רפואישע הוצאות
Clothing|ביגוד|קליידער
Home upkeep|תחזוקת הבית|אויפהאלטן די וואוינונג
Debt payments|החזרי חובות|אפצאלן חובות
Children’s additional needs|צרכים נוספים של הילדים|נאך הוצאות פאר די קינדער
Shabbos, Yom Tov and simchos|שבת, יום טוב ושמחות|שבת, יום טוב און שמחות
Other necessities|צרכים חיוניים אחרים|אנדערע נויטיגע הוצאות
Actual household total|סך ההוצאה בפועל למשפחה|דער גאנצער אמת׳ער סכום פאר די משפחה
Saved household bills|חשבונות משפחתיים שמורים|אפגעהיטענע בילס פון די משפחה
Child estimate|אומדן לילדים|געשאצטע הוצאה פאר די קינדער
Save budget|שמירת תקציב|היט אפ דעם חשבון
Period|תקופה|צייט
Monthly|חודשי|חודש׳ליך
Annual|שנתי|יערליך
Age-group rates|תעריפים לפי גיל|סכומים לויט די יארגאנג
Cost per child|עלות לכל ילד|וויפיל יעדעס קינד קאסט
Age|גיל|עלטער
Birth date|תאריך לידה|געבורטס דאטום
Child-specific monthly amount|סכום חודשי מותאם לילד|א באזונדערער חודש׳ליכער סכום פאר דעם קינד
Add children in the family profile to calculate their costs.|הוסיפו ילדים בפרופיל המשפחה לחישוב העלויות.|לייגט צו די קינדער אין די פרטים פון די משפחה צו רעכענען זייערע הוצאות.
Invalid budget period.|תקופת תקציב לא תקינה.|די צייט פארן חשבון איז נישט ריכטיג.
Enter a valid birth date.|הזינו תאריך לידה תקין.|לייגט אריין א ריכטיגע געבורטס דאטום.
Updated household expense plan|תוכנית הוצאות המשפחה עודכנה|דער הוצאות חשבון פון די משפחה איז אפגעהיטן
Incomplete plan: enter missing amounts, classify bills and check child records. Totals include known amounts only.|התוכנית אינה מלאה: השלימו סכומים, סווגו חשבונות ובדקו את פרטי הילדים. הסכומים כוללים רק מידע ידוע.|דער חשבון איז נאך נישט פול. פילט אויס די סכומים, צייכנט אן ווי צו רעכענען די בילס און קוקט איבער די פרטים פון די קינדער. נאר באקאנטע סכומים זענען מיטגערעכנט.
Actual totals replace saved bills and child estimates for that category. Include the whole household; enter zero for no expense. Annual amounts are divided by 12.|סכומים בפועל מחליפים חשבונות שמורים ואומדני ילדים באותה קטגוריה. כללו את כל המשפחה; הזינו אפס כשאין הוצאה. סכומים שנתיים מחולקים ב־12.|די אמת׳ע סכומים נעמען איבער די בילס און שאצונגען פאר די זעלבע סארט הוצאה. רעכנט אריין די גאנצע משפחה. אויב עס איז נישט דא קיין הוצאה, שרייבט נול. יערליכע סכומים ווערן צעטיילט אויף 12.
Enter your organization’s monthly planning rates. Blank means unknown. These are estimates, not verified bills. Shared housing and adult costs belong in household totals.|הזינו תעריפי תכנון חודשיים של הארגון. שדה ריק פירושו לא ידוע. אלו אומדנים ולא חשבונות מאומתים. דיור משותף והוצאות מבוגרים נכללים בסכומי המשפחה.|לייגט אריין די חודש׳ליכע סכומים וואס דער ארגון רעכנט פאר יעדן יארגאנג. ליידיג מיינט אז מען ווייסט נישט. דאס זענען שאצונגען, נישט באשטעטיגטע בילס. וואוינונג און הוצאות פון די עלטערן גייען אין דעם גאנצן משפחה חשבון.
Child cost equals the sum of age-group rates, with child-specific amounts replacing those rates. Birth date updates age automatically; otherwise keep the entered age current. Camp and seasonal costs should be entered as annual cost divided by 12.|עלות הילד היא סכום תעריפי הגיל, כאשר סכומים אישיים מחליפים את התעריף. תאריך לידה מעדכן גיל אוטומטית; אחרת יש לעדכן את הגיל ידנית. הזינו קייטנה והוצאות עונתיות כעלות שנתית חלקי 12.|די הוצאה פאר יעדעס קינד איז צוזאמען אלע סכומים פון זיין יארגאנג. א באזונדערער סכום פאר דעם קינד נעמט איבער דעם כלליות׳דיגן סכום. מיט א געבורטס דאטום ווערט דער עלטער אליין באנייט, אנדערש דארף מען עס אליין פאררעכטן. קעמפ און סעזאן הוצאות רעכנט מען די יערליכע סומע צעטיילט אויף 12.
'''
for _row in _CHILD_BUDGET_ROWS.strip().splitlines():
    _en, _he, _yi = _row.split('|')
    CATALOG[_en] = {'he': _he, 'yi': _yi}

_PROFILE_REPORT_ROWS = '''
Profile report|דוח פרופיל|באריכט פונעם פראפיל
Print profile / PDF|הדפסת פרופיל / PDF|דרוקן פראפיל / PDF
Back to profile|חזרה לפרופיל|צוריק צום פראפיל
Print / Save PDF|הדפסה / שמירה כ-PDF|דרוקן / אפהיטן אלס PDF
FAMILY PROFILE REPORT|דוח פרופיל משפחה|משפחה פראפיל באריכט
Generated|הופק|געמאכט
Search all lists|חיפוש בכל הרשימות|זוכן אין אלע ליסטעס
Name, note, reference, school…|שם, הערה, אסמכתא, מוסד…|נאמען, נאטיץ, רעפערענץ, מוסד…
List|רשימה|ליסטע
All lists|כל הרשימות|אלע ליסטעס
All statuses|כל הסטטוסים|אלע סטאטוסן
Supporter status|סטטוס תומך|העלפער סטאטוס
Expense status|סטטוס הוצאה|הוצאה סטאטוס
Donations from|תרומות מתאריך|נדבות פון
Donations through|תרומות עד תאריך|נדבות ביז
Apply filters|החלת מסננים|לייג צו פילטערס
Clear filters|ניקוי מסננים|מעק אויס פילטערס
Donations shown|תרומות מוצגות|געוויזענע נדבות
Donation history|היסטוריית תרומות|היסטאריע פון נדבות
No matching records.|לא נמצאו רשומות מתאימות.|קיין פאסיגע רעקארדס נישט געפונען.
File|קובץ|פייל
Type|סוג|סארט
Uploaded|הועלה|ארויפגעלייגט
Date|תאריך|דאטום
Activity|פעילות|אקטיוויטעט
Staff|איש צוות|שטאב
'''
for _row in _PROFILE_REPORT_ROWS.strip().splitlines():
    _en, _he, _yi = _row.split('|')
    CATALOG[_en] = {'he': _he, 'yi': _yi}
