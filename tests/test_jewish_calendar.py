from datetime import date

from jewish_calendar import calendar_line


def test_calendar_line_has_localized_weekday_hebrew_date_and_next_parsha():
    assert calendar_line(date(2026, 9, 9), 'yi') == 'מיטוואך · כ״ז אלול תשפ״ו · פר׳ האזינו'
    assert calendar_line(date(2026, 9, 9), 'he') == 'יום רביעי · כ״ז אלול תשפ״ו · פרשת האזינו'
    assert calendar_line(date(2026, 9, 9), 'en') == 'Wednesday · כ״ז אלול תשפ״ו · Parshas האזינו'
