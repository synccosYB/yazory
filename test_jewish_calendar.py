from datetime import date

from jewish_calendar import calendar_line


def test_calendar_line_has_localized_weekday_hebrew_date_and_next_parsha():
    assert calendar_line(date(2026, 9, 9), 'yi') == 'מיטוואך · כ״ז אלול תשפ״ו · פר׳ האזינו'
    assert calendar_line(date(2026, 9, 9), 'he') == 'יום רביעי · כ״ז אלול תשפ״ו · פרשת האזינו'
    assert calendar_line(date(2026, 9, 9), 'en') == 'Wednesday · כ״ז אלול תשפ״ו · Parshas האזינו'


def test_calendar_line_includes_erev_yom_tov_and_erev_shabbos():
    assert calendar_line(date(2026, 9, 11), 'yi') == (
        'פרייטאג · כ״ט אלול תשפ״ו · ערב ר״ה · ערב שבת · פר׳ האזינו')
    assert calendar_line(date(2026, 9, 11), 'he') == (
        'יום שישי · כ״ט אלול תשפ״ו · ערב ראש השנה · ערב שבת · פרשת האזינו')
    assert calendar_line(date(2026, 9, 11), 'en') == (
        'Friday · כ״ט אלול תשפ״ו · Erev Rosh Hashana · Erev Shabbos · Parshas האזינו')


def test_calendar_line_includes_fast_day_from_jewish_calendar():
    assert 'תענית אסתר' in calendar_line(date(2027, 3, 22), 'yi')
