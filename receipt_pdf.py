"""Branded donor PDFs with embedded Hebrew/Yiddish font support."""
from io import BytesIO
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import object_session

_ROOT = Path(__file__).parent
_FONT = 'YazoryDejaVu'
_NAVY = (0.09, 0.20, 0.32)
_GOLD = (0.68, 0.52, 0.25)


def _font():
    if _FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(
            _FONT, str(_ROOT / 'static/fonts/DejaVuSans.ttf')))
    return _FONT


def _value(page, x, y, value):
    value = str(value)
    direction = 'RTL' if any('\u0590' <= ch <= '\u05ff' for ch in value) else 'LTR'
    page.drawString(x, y, value, direction=direction)


def _document(title, rows, notes, *, pledge=False):
    stream = BytesIO()
    page = canvas.Canvas(stream, pagesize=letter, pageCompression=1)
    page.setTitle(title)
    font = _font()
    page.drawImage(ImageReader(str(_ROOT / 'static/yazory-logo-corrected.png')),
                   54, 684, width=92, height=92, mask='auto')
    page.setFillColorRGB(*_NAVY)
    page.setFont(font, 10)
    page.drawRightString(558, 748, 'YAZORY')
    page.setFont(font, 8)
    page.drawRightString(558, 732, '2 Stonegate Dr. Suite 422')
    page.drawRightString(558, 719, 'Monroe, NY 10950')
    page.drawRightString(558, 706, '845-285-2092  |  info@yaazory.org')
    page.setStrokeColorRGB(*_GOLD)
    page.setLineWidth(1.5)
    page.line(54, 676, 558, 676)
    page.setFillColorRGB(*_NAVY)
    page.setFont(font, 17)
    page.drawString(54, 637, title)
    page.setFont(font, 9)
    page.setFillColorRGB(0.35, 0.39, 0.43)
    page.drawString(54, 618, 'PLEDGE CONFIRMATION' if pledge else 'DONATION RECORD')
    page.setStrokeColorRGB(0.86, 0.88, 0.90)
    page.roundRect(54, 317, 504, 273, 8, stroke=1, fill=0)
    y = 562
    for label, value in rows:
        page.setFont(font, 9)
        page.setFillColorRGB(0.35, 0.39, 0.43)
        page.drawString(75, y, label)
        page.setFont(font, 11)
        page.setFillColorRGB(*_NAVY)
        _value(page, 244, y, value)
        y -= 31
    page.setFont(font, 10)
    page.setFillColorRGB(*_NAVY)
    y = 285
    for note in notes:
        page.drawString(54, y, note)
        y -= 20
    page.setStrokeColorRGB(*_GOLD)
    page.line(54, 91, 558, 91)
    page.setFont(font, 8)
    page.setFillColorRGB(0.35, 0.39, 0.43)
    page.drawString(54, 73, 'Yazory helps families manage essential daily expenses.')
    page.drawRightString(558, 73, 'yaazory.org')
    page.showPage()
    page.save()
    stream.seek(0)
    return stream


def build_donor_receipt_pdf(receipt):
    return _document('Donation receipt', (
        ('Receipt number', f'YZ-{receipt.id:06d}'),
        ('Date received', receipt.received_on.strftime('%m/%d/%Y')),
        ('Donor', receipt.contact.name),
        ('Supported family', receipt.family.name),
        ('Amount received', f'${receipt.amount_cents / 100:,.2f}'),
        ('Payment reference', receipt.reference or 'Manual receipt'),
    ), ('Thank you for helping a family keep everyday life together.',))


def build_pledge_acknowledgment_pdf(contact):
    """A pledge is never represented as a received donation."""
    from app_original import CharityDonation, CharityDonor, Receipt

    session = object_session(contact)
    paid_cents = 0
    fixed_twelve_months = False
    pledged_totals = []
    if session is not None:
        paid_cents = session.scalar(select(func.coalesce(func.sum(Receipt.amount_cents), 0)).where(
            Receipt.contact_id == contact.id)) or 0
        donations = session.scalars(select(CharityDonation).join(
            CharityDonor, CharityDonor.id == CharityDonation.donor_id).where(
            CharityDonor.contact_id == contact.id)).all()
        paid_cents += sum(row.amount_cents for row in donations)
        pledged_totals = [row.pledge_total_cents for row in donations
                          if row.subscription and row.pledge_total_cents]
        fixed_twelve_months = bool(pledged_totals)
    total_cents = max(pledged_totals) if fixed_twelve_months else contact.monthly_cents
    rows = [
        ('Donor', contact.name),
        ('Supported family', contact.family.name),
        ('Case', f'YZ-{contact.family_id:04d}'),
        ('Pledged amount', f'${total_cents / 100:,.2f}'),
        ('Payment schedule', f'${contact.monthly_cents / 100:,.2f} monthly for 12 months'
         if fixed_twelve_months else contact.pledge_frequency),
        ('Received to date', f'${paid_cents / 100:,.2f}'),
    ]
    if fixed_twelve_months or contact.pledge_frequency == 'One time':
        rows.append(('Remaining pledge', f'${max(total_cents - paid_cents, 0) / 100:,.2f}'))
    rows.append(('Issued on', date.today().strftime('%m/%d/%Y')))
    return _document('Pledge acknowledgment', rows, (
        'Payments received are documented separately in your donation history.',
        'This acknowledgment is not a receipt for unpaid pledge amounts.'), pledge=True)


def build_abcharity_payment_pdf(donation, contact):
    """Record an imported payment without claiming Yazory processed it."""
    return _document('Donation payment record', (
        ('Payment reference', f'ABCharity #{donation.external_id}'),
        ('Date received', donation.donation_time.strftime('%m/%d/%Y')),
        ('Donor', contact.name),
        ('Supported family', contact.family.name),
        ('Campaign tax ID', '92-3617094'),
        ('Amount paid', f'${donation.amount_cents / 100:,.2f}'),
        ('Net received by case', f'${donation.net_cents / 100:,.2f}'),
    ), ('Payment processed by ABCharity; imported into Yazory.',
        'For the original processor receipt, contact ABCharity.'))
