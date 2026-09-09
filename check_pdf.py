"""Printable top-check PDFs for manual Yazory applicant payouts."""

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


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


def build_check_pdf(payout):
    """Return an in-memory US Letter top-check ready for preprinted check stock."""
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    width, height = letter
    left, right = 44, width - 44
    top, bottom = height - 34, height - 252

    pdf.setTitle(f'Check {payout.check_number} - {payout.payee_name}')
    pdf.setStrokeColorRGB(.72, .72, .72)
    pdf.rect(left, bottom, right - left, top - bottom, stroke=1, fill=0)
    pdf.setFillColorRGB(.08, .16, .28)
    pdf.setFont('Helvetica-Bold', 13)
    pdf.drawString(left + 12, top - 22, 'YAZORY')
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont('Helvetica', 8)
    pdf.drawString(left + 12, top - 35, 'Family support payout')
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

    pdf.drawString(left + 12, bottom + 20, 'MEMO')
    pdf.drawString(left + 50, bottom + 20, (payout.memo or '')[:52])
    pdf.line(left + 47, bottom + 17, left + 260, bottom + 17)
    pdf.line(right - 210, bottom + 17, right - 12, bottom + 17)
    pdf.drawCentredString(right - 111, bottom + 7, 'AUTHORIZED SIGNATURE')
    pdf.setDash(3, 3)
    pdf.line(left, bottom - 18, right, bottom - 18)
    pdf.setDash()
    pdf.setFillColorRGB(.35, .35, .35)
    pdf.drawCentredString(width / 2, bottom - 32,
                         'Print at Actual Size (100%) on compatible top-check stock. Do not use Fit to Page.')
    pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream
