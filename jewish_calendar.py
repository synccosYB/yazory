"""Presentation helper for the organization's Hebrew calendar header."""
from datetime import timedelta
from pyluach import dates, parshios

WEEKDAYS = {
    'en': ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Shabbos', 'Sunday'),
    'he': ('יום שני', 'יום שלישי', 'יום רביעי', 'יום חמישי', 'יום שישי', 'שבת', 'יום ראשון'),
    'yi': ('מאנטאג', 'דינסטאג', 'מיטוואך', 'דאנערשטאג', 'פרייטאג', 'שבת', 'זונטאג'),
}
PARASHA_PREFIX = {'en': 'Parshas', 'he': 'פרשת', 'yi': 'פר׳'}


def calendar_line(day, language='en'):
    """Return the civil weekday, Hebrew date, and upcoming weekly parsha."""
    language = language if language in WEEKDAYS else 'en'
    gregorian = dates.GregorianDate(day.year, day.month, day.day)
    hebrew = gregorian.to_heb()
    parts = [WEEKDAYS[language][day.weekday()], hebrew.hebrew_date_string()]
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
