"""Small downloadable donor receipt generated from posted Yazory records."""
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


LOGO_PATH = Path(__file__).resolve().parent / 'static' / 'yazory-logo.png'


def build_donor_receipt_pdf(receipt):
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    width, height = letter
    pdf.setTitle(f'Yazory receipt {receipt.id:06d}')
    pdf.drawImage(ImageReader(LOGO_PATH), 54, height - 115, width=125, height=65,
                  preserveAspectRatio=True, anchor='w', mask='auto')
    pdf.setFont('Helvetica-Bold', 20)
    pdf.drawRightString(width - 54, height - 74, 'DONATION RECEIPT')
    pdf.setStrokeColorRGB(.70, .60, .32)
    pdf.setLineWidth(3)
    pdf.line(54, height - 130, width - 54, height - 130)
    rows = (
        ('Receipt number', f'YZ-{receipt.id:06d}'),
        ('Date received', receipt.received_on.strftime('%m/%d/%Y')),
        ('Donor', receipt.contact.name),
        ('Supported family', receipt.family.name),
        ('Amount received', f'${receipt.amount_cents / 100:,.2f}'),
        ('Payment reference', receipt.reference or 'Manual receipt'),
    )
    y = height - 175
    for label, value in rows:
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawString(64, y, label.upper())
        pdf.setFont('Helvetica', 12)
        pdf.drawString(210, y, str(value)[:70])
        y -= 34
    pdf.setFont('Helvetica', 10)
    pdf.drawString(64, 105, 'Thank you for helping a family keep everyday life together.')
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(64, 78, 'Yazory · Developed and operated by Synccos Inc.')
    pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream
