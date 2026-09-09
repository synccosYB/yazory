"""Printable top-check PDFs for manual Yazory applicant payouts."""

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit


ONES = ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
        'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen',
        'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen')
TENS = ('', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy',
        'Eighty', 'Ninety')


def _under_thousand(value):
    words = []
    if value >= 100:
        words.extend((ONES[value // 100], 'Hundred'))
        value %= 100
    if value >= 20:
        words.append(TENS[value // 10] + (f'-{ONES[value % 10]}' if value % 10 else ''))
    elif value:
        words.append(ONES[value])
    return ' '.join(words)


def amount_words(amount_cents):
    dollars, cents = divmod(amount_cents, 100)
    if dollars > 1_000_000:
        raise ValueError('Check amount is too large.')
    parts = []
    for divisor, label in ((1_000_000, 'Million'), (1_000, 'Thousand'), (1, '')):
        group, dollars = divmod(dollars, divisor)
        if group:
            parts.append(_under_thousand(group))
            if label:
                parts.append(label)
    return f"{' '.join(parts) or 'Zero'} and {cents:02d}/100 Dollars"


ASSET_ROOT = Path(__file__).resolve().parent / 'static'
MICR_FONT_PATH = ASSET_ROOT / 'fonts' / 'Nimra-MICR.ttf'
LOGO_PATH = ASSET_ROOT / 'yazory-logo.png'


def build_check_pdf(payout, routing_number, account_number, bank_name=''):
    """Return an in-memory US Letter top-check ready for preprinted check stock."""
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    width, height = letter
    left, right = 44, width - 44
    top, bottom = height - 34, height - 252

    pdf.setTitle(f'Check {payout.check_number} - {payout.payee_name}')
    pdf.setStrokeColorRGB(.72, .72, .72)
    pdf.rect(left, bottom, right - left, top - bottom, stroke=1, fill=0)
    pdf.drawImage(ImageReader(LOGO_PATH), left + 10, top - 67, width=58, height=58,
                  preserveAspectRatio=True, anchor='c', mask='auto')
    if bank_name:
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(left + 78, top - 28, bank_name[:55])
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawRightString(right - 12, top - 22, payout.check_number)
    pdf.setFont('Helvetica', 9)
    pdf.drawRightString(right - 12, top - 39, 'VOID AFTER 90 DAYS')
    pdf.drawString(right - 190, top - 61, 'DATE')
    pdf.line(right - 155, top - 64, right - 12, top - 64)
    pdf.drawRightString(right - 15, top - 60, payout.check_date.strftime('%m/%d/%Y'))

    pdf.drawString(left + 12, top - 94, 'PAY TO THE')
    pdf.drawString(left + 12, top - 106, 'ORDER OF')
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(left + 82, top - 101, payout.payee_name[:62])
    pdf.line(left + 78, top - 106, right - 104, top - 106)
    pdf.rect(right - 94, top - 112, 82, 25, stroke=1, fill=0)
    pdf.drawCentredString(right - 53, top - 104, f'${payout.amount_cents / 100:,.2f}')

    pdf.setFont('Helvetica', 9)
    pdf.drawString(left + 12, top - 132, amount_words(payout.amount_cents)[:92])
    pdf.line(left + 10, top - 137, right - 12, top - 137)
    address_lines = [line.strip() for line in (payout.mailing_address or '').splitlines() if line.strip()]
    pdf.setFont('Helvetica', 8)
    for index, line in enumerate(address_lines[:3]):
        pdf.drawString(left + 82, top - 151 - index * 10, line[:78])

    pdf.drawString(left + 12, bottom + 42, 'MEMO')
    pdf.drawString(left + 50, bottom + 42, (payout.memo or '')[:52])
    pdf.line(left + 47, bottom + 39, left + 260, bottom + 39)
    pdf.line(right - 210, bottom + 39, right - 12, bottom + 39)
    pdf.drawCentredString(right - 111, bottom + 29, 'AUTHORIZED SIGNATURE')

    if 'NimraMICR' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('NimraMICR', MICR_FONT_PATH))
    pdf.setFont('NimraMICR', 11)
    micr_line = (f'{chr(0x2446)}{routing_number}{chr(0x2446)} '
                 f'{chr(0x2449)}{account_number}{chr(0x2449)}  {payout.check_number}')
    pdf.drawCentredString(width / 2, bottom + 7, micr_line)
    pdf.setDash(3, 3)
    pdf.line(left, bottom - 18, right, bottom - 18)
    pdf.setDash()
    pdf.setFillColorRGB(.35, .35, .35)
    pdf.setFont('Helvetica', 8)
    pdf.drawCentredString(width / 2, bottom - 32,
                         'Print at Actual Size (100%) on compatible top-check stock. Do not use Fit to Page.')
    stub_top = bottom - 56
    pdf.setStrokeColorRGB(.72, .72, .72)
    pdf.rect(left, stub_top - 132, right - left, 132, stroke=1, fill=0)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawString(left + 12, stub_top - 20, 'CHECK STUB')
    pdf.setFont('Helvetica', 9)
    case_number = f'YZ-{payout.family_id:04d}'
    previous = payout.prior_case_check_count or 0
    pdf.drawString(left + 12, stub_top - 40, f'Case number: {case_number}')
    pdf.drawString(left + 180, stub_top - 40, f'Check number: {payout.check_number}')
    pdf.drawString(left + 340, stub_top - 40, f'Check date: {payout.check_date:%m/%d/%Y}')
    pdf.drawString(left + 12, stub_top - 58, f'Payee: {payout.payee_name[:55]}')
    pdf.drawString(left + 340, stub_top - 58, f'Amount: ${payout.amount_cents / 100:,.2f}')
    pdf.drawString(left + 12, stub_top - 76,
                   f'Check sequence for this case: {previous + 1}  |  Previously issued: {previous}')
    message = payout.recipient_message or 'Please find the enclosed support payment. Wishing you and your family continued strength and success.'
    pdf.setFont('Helvetica-Oblique', 8)
    for index, line in enumerate(simpleSplit(message, 'Helvetica-Oblique', 8, right - left - 24)[:3]):
        pdf.drawString(left + 12, stub_top - 96 - index * 11, line)
    pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream
