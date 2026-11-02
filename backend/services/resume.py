"""A concise employee resume with shared content and editable Word/PDF layouts.

Only selected, non-confidential relationships are read. A resume does not build
the personnel sheet or inspect assessment sessions to show tenure.
"""
import io
from datetime import date
from html import escape

from services.documents import L, _name, _fmt_date, _register_fonts
from services.metrics import _as_interval, _total_years, disposal_intervals

SECTIONS = ('career', 'education', 'languages', 'training', 'metrics')
LABELS = {
    'ru': {'title': 'Резюме сотрудника', 'career': 'Профессиональный опыт',
           'education': 'Образование', 'languages': 'Знание языков',
           'training': 'Повышение квалификации', 'metrics': 'Опыт в цифрах',
           'empty': 'В выбранных разделах пока нет сведений.',
           'company': 'В компании, лет', 'total': 'Общий стаж, лет',
           'management': 'Управленческий, лет', 'expired': 'Срок подтверждения истёк'},
    'kk': {'title': 'Қызметкердің түйіндемесі', 'career': 'Кәсіби тәжірибе',
           'education': 'Білімі', 'languages': 'Тілдерді білуі',
           'training': 'Біліктілікті арттыру', 'metrics': 'Тәжірибе көрсеткіштері',
           'empty': 'Таңдалған бөлімдерде әзірге мәлімет жоқ.',
           'company': 'Компанияда, жыл', 'total': 'Жалпы өтіл, жыл',
           'management': 'Басшылық өтілі, жыл', 'expired': 'Растау мерзімі аяқталған'},
}
INK, MUTED, ACCENT, PALE, BORDER = '202C38', '566473', '176C73', 'EDF3F6', 'D9D9D9'


def _joined(*values):
    return ' · '.join(str(value) for value in values if value)


def _record(title, lines=(), period=''):
    return {'title': title, 'lines': [line for line in lines if line], 'period': period}


def build_resume(db, employee, lang, sections, contacts=False):
    """Build a public snapshot without loading unselected sections.

    ``db`` remains in the public contract; tenure uses only work intervals and
    needs no hierarchy queries, competency scores or full employee metrics.
    """
    lang = lang if lang in LABELS else 'ru'
    t, labels, today = L[lang], LABELS[lang], date.today()
    chosen = set(sections) & set(SECTIONS)
    result = {'name': employee.full_name, 'title': labels['title'], 'lang': lang,
              'position': _name(employee.current_position, lang),
              'unit': _name(employee.current_org_unit, lang),
              'contacts': _joined(employee.email, employee.phone) if contacts else '',
              'date': f"{t['generated']}: {_fmt_date(today)}", 'sections': []}
    career = list(employee.work_experience) if chosen & {'career', 'metrics'} else []
    for key in SECTIONS:
        if key not in chosen:
            continue
        records = []
        if key == 'career':
            for row in sorted(career, key=lambda r: r.date_from or date.min, reverse=True):
                employer = _name(row.org_unit, lang) if row.is_internal else row.external_employer
                position = _name(row.position, lang) if row.is_internal else row.external_position_title
                period = f"{_fmt_date(row.date_from)} - {_fmt_date(row.date_to) if row.date_to else t['present']}"
                records.append(_record(position or employer or t['none'],
                    [employer if position else '', _joined(_name(row.job_family, lang), _name(row.org_unit_type, lang))], period))
        elif key == 'education':
            for row in sorted(employee.educations, key=lambda r: (r.end_year or 9999, r.start_year or 0), reverse=True):
                period = ' - '.join(str(y) for y in (row.start_year, row.end_year) if y)
                field = _name(row.field, lang)
                records.append(_record(row.institution or _name(row.level, lang) or t['none'],
                    [_joined(_name(row.level, lang), field), row.qualification if row.qualification != field else ''], period))
        elif key == 'languages':
            for row in employee.languages:
                expired = row.valid_until and row.valid_until < today
                confirmation = labels['expired'] if row.is_confirmed and expired else f"{t['confirmed']}: {t['yes'] if row.is_confirmed else t['no']}"
                records.append(_record(_joined(_name(row.language, lang), row.level.code if row.level else ''),
                    [_joined(confirmation, f"{t['valid_until']}: {_fmt_date(row.valid_until)}" if row.valid_until else '')]))
        elif key == 'training':
            for row in sorted(employee.trainings, key=lambda r: r.date_to or r.date_from or date.min, reverse=True):
                period = ' - '.join(_fmt_date(d) for d in (row.date_from, row.date_to) if d)
                records.append(_record(row.name or t['none'],
                    [row.provider, _joined(_name(row.job_family, lang), row.result)], period))
        elif key == 'metrics':
            # Same exclusion and cut-off used in the employee card and methodology.
            excluded = disposal_intervals(db, [employee.id], today).get(employee.id, []) if db is not None else []
            for label, rows in ((labels['total'], career),
                                (labels['company'], [r for r in career if r.is_internal]),
                                (labels['management'], [r for r in career if (r.management_level or 0) > 0])):
                intervals = [_as_interval(row, today) for row in rows]
                value = f"{_total_years([iv for iv in intervals if iv], excluded):.1f}".replace('.', ',')
                records.append({**_record(f'{label}: {value}'), 'label': label, 'value': value})
        if records:
            result['sections'].append({'key': key, 'title': labels[key], 'records': records})
    return result


def _ordered_sections(data):
    return sorted(data['sections'], key=lambda block: 0 if block['key'] == 'metrics' else 1)


def _metric_values(record):
    if 'label' in record:
        return record['label'], record['value']
    label, _, value = record['title'].rpartition(':')
    return label or record['title'], value.strip()


def render_docx(data):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document()
    for node in list(doc.styles.element.iter(qn('w:pBdr'))):
        node.getparent().remove(node)
    doc.core_properties.author = ''
    doc.core_properties.last_modified_by = ''
    doc.core_properties.title = data['title']
    doc.core_properties.subject = ''
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.7), Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    section.footer_distance = Cm(.8)
    for name in ('Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2'):
        style = doc.styles[name]
        style.font.name = 'Calibri'
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.italic = False
        style.paragraph_format.space_after = Pt(3)
        style.paragraph_format.line_spacing = 1.08
        style.paragraph_format.widow_control = True
    normal = doc.styles['Normal']
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor.from_string(INK)
    title = doc.styles['Title']
    title.font.size, title.font.bold = Pt(25), True
    title.paragraph_format.space_after = Pt(7)
    title.paragraph_format.keep_with_next = True
    heading = doc.styles['Heading 1']
    heading.font.size, heading.font.bold = Pt(11.5), True
    heading.paragraph_format.space_before = Pt(15)
    heading.paragraph_format.space_after = Pt(7)
    heading.paragraph_format.keep_with_next = True

    def paragraph(text='', size=None, color=None, bold=False, before=0, after=3, keep=False, style=None):
        p = doc.add_paragraph(style=style)
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
        p.paragraph_format.keep_with_next = keep
        run = p.add_run(str(text))
        if size: run.font.size = Pt(size)
        if color: run.font.color.rgb = RGBColor.from_string(color)
        if bold: run.bold = True
        return p

    paragraph(data['title'].upper(), size=8.5, after=8, keep=True)
    doc.add_paragraph(data['name'], 'Title')
    if data['position']:
        paragraph(data['position'], size=12, bold=True, after=4, keep=bool(data['unit']))
    if data['unit']:
        paragraph(data['unit'], color=MUTED, after=5)
    if data['contacts']:
        paragraph(data['contacts'], size=9, color=MUTED, after=5)

    for block in _ordered_sections(data):
        doc.add_paragraph(block['title'], 'Heading 1')
        if block['key'] == 'metrics':
            metrics = block['records'][:3]
            table = doc.add_table(rows=2, cols=len(metrics))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = False
            properties = table._tbl.tblPr
            borders = OxmlElement('w:tblBorders')
            for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
                border = OxmlElement(f'w:{edge}')
                border.set(qn('w:val'), 'single'); border.set(qn('w:sz'), '4'); border.set(qn('w:color'), BORDER)
                borders.append(border)
            properties.append(borders)
            margins = OxmlElement('w:tblCellMar')
            for edge in ('top', 'left', 'bottom', 'right'):
                margin = OxmlElement(f'w:{edge}')
                margin.set(qn('w:w'), '100' if edge in ('top', 'bottom') else '140')
                margin.set(qn('w:type'), 'dxa'); margins.append(margin)
            properties.append(margins)
            table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            for i, metric in enumerate(metrics):
                label, value = _metric_values(metric)
                for row_index, content in enumerate((label, value)):
                    cell = table.cell(row_index, i)
                    cell.width = Cm(17 / len(metrics))
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_after = Pt(0)
                    p.paragraph_format.keep_with_next = row_index == 0
                    run = p.add_run(content)
                    run.font.size = Pt(8.5 if row_index == 0 else 19)
                    run.bold = row_index == 1
                    run.font.color.rgb = RGBColor.from_string('000000' if row_index == 0 else ACCENT)
                    if row_index == 0:
                        shading = OxmlElement('w:shd'); shading.set(qn('w:fill'), PALE); cell._tc.get_or_add_tcPr().append(shading)
            continue
        for index, record in enumerate(block['records']):
            period = record.get('period', '')
            if period:
                paragraph(period, size=8.5, color=ACCENT, before=7 if index else 1, after=2, keep=True)
            paragraph(record['title'], size=10.5, bold=True,
                      before=0 if period or not index else 7, after=2, keep=bool(record['lines']))
            for line_index, line in enumerate(record['lines']):
                paragraph(line, size=9.5, color=INK if line_index == 0 else MUTED,
                          after=2, keep=line_index < len(record['lines']) - 1 and len(line) < 700)
    if not data['sections']:
        paragraph(LABELS.get(data['lang'], LABELS['ru'])['empty'], color=MUTED, before=17)
    footer = section.footer.paragraphs[0]
    footer.style = doc.styles['Normal']
    footer.paragraph_format.tab_stops.add_tab_stop(Cm(17), WD_TAB_ALIGNMENT.RIGHT)
    run = footer.add_run(data['date'] + '\t')
    run.font.size, run.font.color.rgb = Pt(8), RGBColor.from_string(MUTED)
    field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    stream = io.BytesIO(); doc.save(stream)
    return stream.getvalue()


def render_pdf(data):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, Table, TableStyle
    regular, bold = _register_fonts()
    body = ParagraphStyle('ResumeBody', fontName=regular, fontSize=9.3, leading=12.3,
                          textColor=colors.HexColor('#' + INK), spaceAfter=3)
    styles = {
        'title': ParagraphStyle('ResumeTitle', parent=body, fontName=bold, fontSize=23, leading=27.5, textColor=colors.black, spaceAfter=9, keepWithNext=True),
        'eyebrow': ParagraphStyle('ResumeEyebrow', parent=body, fontSize=8, leading=11, textColor=colors.black, spaceAfter=9, keepWithNext=True),
        'position': ParagraphStyle('ResumePosition', parent=body, fontName=bold, fontSize=11.3, leading=15, textColor=colors.black, spaceAfter=4),
        'muted': ParagraphStyle('ResumeMuted', parent=body, textColor=colors.HexColor('#' + MUTED)),
        'heading': ParagraphStyle('ResumeHeading', parent=body, fontName=bold, fontSize=11.2, leading=15, textColor=colors.black, spaceBefore=15, spaceAfter=7, keepWithNext=True),
        'period': ParagraphStyle('ResumePeriod', parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor('#' + ACCENT), spaceAfter=2, keepWithNext=True),
        'record': ParagraphStyle('ResumeRecord', parent=body, fontName=bold, fontSize=9.8, leading=13, textColor=colors.black, spaceAfter=2),
        'metric_label': ParagraphStyle('ResumeMetricLabel', parent=body, fontSize=8, leading=11, textColor=colors.black, alignment=TA_CENTER, spaceAfter=0),
        'metric_value': ParagraphStyle('ResumeMetricValue', parent=body, fontName=bold, fontSize=18, leading=23, textColor=colors.HexColor('#' + ACCENT), alignment=TA_CENTER, spaceAfter=0),
    }
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                           topMargin=17*mm, bottomMargin=18*mm, title=data['title'], author='')
    def p(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story = [p(data['title'].upper(), styles['eyebrow']), p(data['name'], styles['title'])]
    for key in ('position', 'unit', 'contacts'):
        if data[key]: story.append(p(data[key], styles['position'] if key == 'position' else styles['muted']))
    for block in _ordered_sections(data):
        story.append(p(block['title'], styles['heading']))
        if block['key'] == 'metrics':
            metrics = [_metric_values(record) for record in block['records'][:3]]
            table = Table([[p(label, styles['metric_label']) for label, _ in metrics],
                           [p(value, styles['metric_value']) for _, value in metrics]],
                          colWidths=[(doc.width - 12) / len(metrics)] * len(metrics), repeatRows=1)
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#' + BORDER)),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#' + PALE)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(KeepTogether([table]))
            continue
        for index, record in enumerate(block['records']):
            if index: story.append(Spacer(1, 5))
            parts = []
            if record.get('period'): parts.append(p(record['period'], styles['period']))
            record_style = ParagraphStyle('RecordWithDetails', parent=styles['record'], keepWithNext=bool(record['lines']))
            parts.append(p(record['title'], record_style))
            parts.extend(p(line, body if i == 0 else styles['muted']) for i, line in enumerate(record['lines']))
            # Large records split naturally rather than leaving a blank page.
            if sum(len(str(value)) for value in [record['title'], record.get('period', ''), *record['lines']]) < 950:
                story.append(KeepTogether(parts))
            else:
                story.extend(parts)
    if not data['sections']:
        story.extend([Spacer(1, 15), p(LABELS.get(data['lang'], LABELS['ru'])['empty'], styles['muted'])])
    def footer(canvas, document):
        canvas.saveState(); canvas.setFont(regular, 7.5); canvas.setFillColor(colors.HexColor('#' + MUTED))
        canvas.drawString(20*mm + 6, 10*mm, data['date'])
        canvas.drawRightString(A4[0]-20*mm - 6, 10*mm, str(canvas.getPageNumber()))
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
