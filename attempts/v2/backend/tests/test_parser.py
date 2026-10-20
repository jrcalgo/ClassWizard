import io
import pytest
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from classwizard.parser import parse_pdf

def pdf(lines):
    out = io.BytesIO()
    page = canvas.Canvas(out)
    for i, line in enumerate(lines):
        page.drawString(40, 750 - i * 20, line)
    page.save()
    return out.getvalue()

def test_synthetic_sections():
    r = parse_pdf(pdf(['Synthetic worksheet', 'Completed', 'ITSC 1212 A', 'In progress', 'ITSC 1213', 'Still needed', 'ITSC 2214', 'Applied credits: 24']))
    assert r['completed'] == {'ITSC 1212': 'A'}
    assert r['in_progress'] == ['ITSC 1213']
    assert r['remaining_candidates'] == ['ITSC 2214']
    assert r['applied_credits'] == 24
    assert not r['reviewed']

def test_repeated_layout_overlap_requires_review():
    r = parse_pdf(pdf(['Synthetic worksheet', 'Completed', 'ITSC 1212 A', 'In progress', 'ITSC 1212']))
    assert not r['completed'] and not r['in_progress']
    assert r['uncertain_courses'] == ['ITSC 1212']

def test_malformed_blank_encrypted():
    with pytest.raises(ValueError):
        parse_pdf(b'not a pdf')
    with pytest.raises(ValueError):
        parse_pdf(pdf([]))
    writer=PdfWriter(); writer.add_page(PdfReader(io.BytesIO(pdf(['Synthetic worksheet']))).pages[0]); writer.encrypt('secret')
    out=io.BytesIO(); writer.write(out)
    with pytest.raises(ValueError):
        parse_pdf(out.getvalue())
