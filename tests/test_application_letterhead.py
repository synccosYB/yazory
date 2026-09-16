from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTACT_DETAILS = (
    '2 Stone Gate Dr., Suite 422',
    'Monroe, NY 10950',
    '(845) 285-2092',
    'info@yaazory.org',
)


def test_application_letterhead_is_on_online_and_printed_applications():
    for filename in ('application_form_public.html', 'application_print.html'):
        template = (ROOT / 'templates' / filename).read_text()
        assert "filename='application-letterhead.css'" in template
        assert 'class="application-letterhead-contact" dir="ltr"' in template
        for detail in CONTACT_DETAILS:
            assert detail in template


def test_application_letterhead_has_clickable_phone_and_email():
    template = (ROOT / 'templates' / 'application_form_public.html').read_text()
    assert 'href="tel:+18452852092"' in template
    assert 'href="mailto:info@yaazory.org"' in template
