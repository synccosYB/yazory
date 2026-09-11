"""Presentation helper for the organization's Hebrew calendar header."""
from datetime import timedelta
from pyluach import dates, parshios

WEEKDAYS = {
    'en': ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Shabbos', 'Sunday'),
    'he': ('יום שני', 'יום שלישי', 'יום רביעי', 'יום חמישי', 'יום שישי', 'שבת', 'יום ראשון'),
    'yi': ('מאנטאג', 'דינסטאג', 'מיטוואך', 'דאנערשטאג', 'פרייטאג', 'שבת', 'זונטאג'),
}
PARASHA_PREFIX = {'en': 'Parshas', 'he': 'פרשת', 'yi': 'פר׳'}
EREV_PREFIX = {'en': 'Erev', 'he': 'ערב', 'yi': 'ערב'}
EREV_SHABBOS = {'en': 'Erev Shabbos', 'he': 'ערב שבת', 'yi': 'ערב שבת'}


def _holiday_name(hebrew_date, language):
    """Return pyluach's calendar observance in the requested language."""
    return hebrew_date.holiday(hebrew=language in ('he', 'yi'), prefix_day=True)


def _erev_holiday_name(day, language):
    """Return an Erev label when tomorrow begins a festival (not a fast)."""
    tomorrow = day + timedelta(days=1)
    tomorrow_gregorian = dates.GregorianDate(
        tomorrow.year, tomorrow.month, tomorrow.day)
    tomorrow_hebrew = tomorrow_gregorian.to_heb()
    festival = tomorrow_hebrew.festival(
        hebrew=language in ('he', 'yi'), prefix_day=False)
    if not festival:
        return None
    # Staff use the familiar abbreviated wording for Erev Rosh Hashana.
    if festival in ('ראש השנה', 'Rosh Hashana'):
        festival = 'ר״ה' if language == 'yi' else (
            'ראש השנה' if language == 'he' else 'Rosh Hashana')
    return f'{EREV_PREFIX[language]} {festival}'


def calendar_line(day, language='en'):
    """Return weekday, Hebrew date, calendar observances, and next parsha."""
    language = language if language in WEEKDAYS else 'en'
    gregorian = dates.GregorianDate(day.year, day.month, day.day)
    hebrew = gregorian.to_heb()
    parts = [WEEKDAYS[language][day.weekday()], hebrew.hebrew_date_string()]
    holiday = _holiday_name(hebrew, language)
    if holiday:
        parts.append(holiday)
    else:
        erev_holiday = _erev_holiday_name(day, language)
        if erev_holiday:
            parts.append(erev_holiday)
    if day.weekday() == 4:
        parts.append(EREV_SHABBOS[language])
    parsha = parshios.getparsha_string(gregorian, hebrew=True)
    # A festival can replace the regular Shabbos reading. The header still
    # identifies the next weekly parsha, as requested by staff.
    for offset in range(1, 22):
        if parsha:
            break
        future = day + timedelta(days=offset)
        parsha = parshios.getparsha_string(
            dates.GregorianDate(future.year, future.month, future.day), hebrew=True)
    if parsha:
        parts.append(f'{PARASHA_PREFIX[language]} {parsha}')
    return ' · '.join(parts)
