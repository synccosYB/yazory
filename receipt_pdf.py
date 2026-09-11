"""Dependency-free downloadable donor receipts."""
from io import BytesIO


def _pdf_text(value):
    """Escape text for a built-in PDF font; unsupported glyphs are replaced."""
    value = str(value).encode('latin-1', 'replace').decode('latin-1')
    return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_donor_receipt_pdf(receipt):
    rows = (
        ('Receipt number', f'YZ-{receipt.id:06d}'),
        ('Date received', receipt.received_on.strftime('%m/%d/%Y')),
        ('Donor', receipt.contact.name),
        ('Supported family', receipt.family.name),
        ('Amount received', f'${receipt.amount_cents / 100:,.2f}'),
        ('Payment reference', receipt.reference or 'Manual receipt'),
    )
    commands = [
        'BT', '/F1 20 Tf', '54 720 Td', '(YAZORY DONATION RECEIPT) Tj',
        '/F1 11 Tf', '0 -48 Td',
    ]
    for label, value in rows:
        commands.extend((f'({_pdf_text(label)}:  {_pdf_text(value)}) Tj', '0 -28 Td'))
    commands.extend(('/F1 10 Tf', '0 -30 Td',
                     '(Thank you for helping a family keep everyday life together.) Tj',
                     '0 -24 Td', '(Yazory - Developed and operated by Synccos Inc.) Tj', 'ET'))
    stream = '\n'.join(commands).encode('latin-1')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{number} 0 obj\n'.encode())
        pdf.extend(obj)
        pdf.extend(b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n'.encode())
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend((f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
                f'startxref\n{xref}\n%%EOF\n').encode())
    return BytesIO(bytes(pdf))
