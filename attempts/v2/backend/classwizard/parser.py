"""Conservative PDF extraction; never persist uploaded bytes or extracted text."""
import io
import re
from pypdf import PdfReader

COURSE = re.compile(r'\b([A-Z]{2,5})\s*(\d{4}[A-Z]?)\b')

def parse_pdf(content):
    if not content.startswith(b'%PDF-'):
        raise ValueError('This is not a PDF. Use manual entry instead.')
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError('Encrypted worksheets are unsupported. Use manual entry.')
        if len(reader.pages) > 30:
            raise ValueError('Worksheet exceeds the 30-page limit.')
        text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Unable to read this worksheet. Use manual entry.') from exc
    if len(text.strip()) < 30:
        raise ValueError('Image-only worksheets are unsupported. Use manual entry.')
    completed, progress, needed, uncertain = {}, set(), set(), set()
    section = 'unknown'
    for line in text.splitlines():
        lower = line.lower()
        if 'still needed' in lower or 'not complete' in lower:
            section = 'needed'
        elif 'in-progress' in lower or 'in progress' in lower:
            section = 'progress'
        elif 'completed' in lower:
            section = 'completed'
        for match in COURSE.finditer(line):
            code = f'{match[1]} {match[2]}'
            grade = re.search(r'\b(A|B|C|D|F|TR|P)\b', line[match.end():])
            if section == 'completed' and grade:
                completed[code] = grade[1]
            elif section == 'progress':
                progress.add(code)
            elif section == 'needed':
                needed.add(code)
            else:
                uncertain.add(code)
    overlap = set(completed) & progress
    for c in overlap:
        completed.pop(c)
        progress.discard(c)
        uncertain.add(c)
    credits = re.search(r'(?:Applied credits|Credits applied)\s*:?\s*(\d+(?:\.\d+)?)', text, re.I)
    return {'completed': completed, 'in_progress': sorted(progress), 'applied_credits': float(credits[1]) if credits else 0,
            'reviewed': False, 'satisfied_groups': [], 'requirement_choices': {}, 'approved_exceptions': [],
            'remaining_candidates': sorted(needed), 'uncertain_courses': sorted(uncertain),
            'warnings': ['Review all extracted fields before planning. Real DegreeWorks layout compatibility is unverified.',
                         'Transfer and pass grades do not establish minimum-grade prerequisites without explicit review.']}
