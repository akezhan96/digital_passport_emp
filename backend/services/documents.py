"""Employee CV generation in PDF and DOCX.

Both formats are rendered from one intermediate structure, so the two outputs
can never drift apart: `build_cv_data()` gathers everything once, and the two
renderers only lay it out.

The layout here is a sensible default. When the agreed template arrives, only
the section list and the renderers need to change -- the data gathering stays.
"""

import io
import os
from html import escape
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import Employee
from services.metrics import compute_employee_metrics

# ---------------------------------------------------------------------------
# Localisation for document labels
# ---------------------------------------------------------------------------

L = {
    "ru": {
        "title": "Личный листок по учёту кадров",
        "subtitle": "Цифровой профиль сотрудника",
        "generated": "Сформировано",
        "code": "Код",
        "personal": "1. Общие сведения",
        "education": "2. Образование",
        "languages": "3. Владение иностранными языками",
        "training": "4. Повышение квалификации",
        "career": "5. Трудовая деятельность",
        "competencies": "6. Профессиональные качества",
        "metrics": "7. Расчётные показатели",
        "extra": "8. Дополнительные сведения",
        "full_name": "Ф. И. О.",
        "personnel_number": "Личный номер",
        "birth": "Дата и место рождения",
        "nationality": "Национальность",
        "hire_date": "Дата приёма на работу",
        "position": "Должность",
        "org_unit": "Подразделение",
        "email": "Электронная почта",
        "phone": "Телефон",
        "status": "Статус профиля",
        "level": "Уровень",
        "institution": "Учебное заведение",
        "field": "Специальность",
        "years": "Годы",
        "language": "Язык",
        "lang_level": "Уровень",
        "confirmed": "Подтверждён",
        "document": "Документ",
        "valid_until": "Действителен до",
        "course": "Курс",
        "provider": "Организация",
        "period": "Период",
        "result": "Результат",
        "employer": "Организация / подразделение",
        "job_family": "Функция",
        "unit_type": "Тип подразделения",
        "from_to": "Период работы",
        "appointment": "Основание",
        "present": "по наст. время",
        "competency": "Компетенция",
        "score": "Балл",
        "assessed": "Дата оценки",
        "metric": "Показатель",
        "value": "Значение",
        "yes": "да", "no": "нет", "none": "нет данных",
        "footer": "Показатели стажа рассчитаны системой по интервалам "
                  "трудовой деятельности и не вводятся вручную.",
        "appointment_types": {
            "initial": "первичное назначение", "transfer": "перевод",
            "promotion": "повышение", "return": "возвращение",
            "external": "внешний работодатель",
        },
        "statuses": {"draft": "черновик", "in_review": "на проверке",
                     "verified": "подтверждён", "archived": "в архиве"},
        "metric_names": {
            "company_experience_years": "Стаж в компании, лет",
            "total_experience_years": "Общий стаж, лет",
            "management_experience_years": "Управленческий стаж, лет",
        },
        "metric_function": "Опыт по функции",
        "metric_unit": "Опыт в подразделениях типа",
        "metric_country": "Опыт работы в стране",
    },
    "kk": {
        "title": "Кадрларды есепке алу жөніндегі жеке парақ",
        "subtitle": "Қызметкердің цифрлық профилі",
        "generated": "Жасалды",
        "code": "Коды",
        "personal": "1. Жалпы мәліметтер",
        "education": "2. Білімі",
        "languages": "3. Шет тілдерін білуі",
        "training": "4. Біліктілікті арттыру",
        "career": "5. Еңбек қызметі",
        "competencies": "6. Кәсіби қасиеттері",
        "metrics": "7. Есептік көрсеткіштер",
        "extra": "8. Қосымша мәліметтер",
        "full_name": "Аты-жөні",
        "personnel_number": "Жеке нөмірі",
        "birth": "Туған күні мен жері",
        "nationality": "Ұлты",
        "hire_date": "Жұмысқа қабылданған күні",
        "position": "Лауазымы",
        "org_unit": "Бөлімшесі",
        "email": "Электрондық поштасы",
        "phone": "Телефоны",
        "status": "Профиль мәртебесі",
        "level": "Деңгейі",
        "institution": "Оқу орны",
        "field": "Мамандығы",
        "years": "Жылдары",
        "language": "Тіл",
        "lang_level": "Деңгейі",
        "confirmed": "Расталған",
        "document": "Құжат",
        "valid_until": "Жарамдылық мерзімі",
        "course": "Курс",
        "provider": "Ұйым",
        "period": "Кезеңі",
        "result": "Нәтижесі",
        "employer": "Ұйым / бөлімше",
        "job_family": "Функциясы",
        "unit_type": "Бөлімше түрі",
        "from_to": "Жұмыс кезеңі",
        "appointment": "Негіздеме",
        "present": "қазіргі уақытқа дейін",
        "competency": "Құзыреттілік",
        "score": "Ұпай",
        "assessed": "Бағалау күні",
        "metric": "Көрсеткіш",
        "value": "Мәні",
        "yes": "иә", "no": "жоқ", "none": "дерек жоқ",
        "footer": "Өтіл көрсеткіштерін жүйе еңбек қызметінің аралықтары "
                  "бойынша есептеген, олар қолмен енгізілмейді.",
        "appointment_types": {
            "initial": "бастапқы тағайындау", "transfer": "ауыстыру",
            "promotion": "жоғарылату", "return": "қайта оралу",
            "external": "сыртқы жұмыс беруші",
        },
        "statuses": {"draft": "жоба", "in_review": "тексерілуде",
                     "verified": "расталған", "archived": "мұрағатта"},
        "metric_names": {
            "company_experience_years": "Компаниядағы өтіл, жыл",
            "total_experience_years": "Жалпы өтіл, жыл",
            "management_experience_years": "Басшылық өтілі, жыл",
        },
        "metric_function": "Функция бойынша тәжірибе",
        "metric_unit": "Бөлімше түріндегі тәжірибе",
        "metric_country": "Елдегі жұмыс тәжірибесі",
    },
    "en": {
        "title": "Employee Record Sheet",
        "subtitle": "Digital employee profile",
        "generated": "Generated",
        "code": "Code",
        "personal": "1. General information",
        "education": "2. Education",
        "languages": "3. Foreign languages",
        "training": "4. Professional development",
        "career": "5. Employment history",
        "competencies": "6. Professional qualities",
        "metrics": "7. Derived figures",
        "extra": "8. Additional information",
        "full_name": "Full name",
        "personnel_number": "Personnel number",
        "birth": "Date and place of birth",
        "nationality": "Nationality",
        "hire_date": "Hire date",
        "position": "Position",
        "org_unit": "Organisational unit",
        "email": "Email",
        "phone": "Phone",
        "status": "Profile status",
        "level": "Level",
        "institution": "Institution",
        "field": "Field of study",
        "years": "Years",
        "language": "Language",
        "lang_level": "Level",
        "confirmed": "Confirmed",
        "document": "Document",
        "valid_until": "Valid until",
        "course": "Course",
        "provider": "Provider",
        "period": "Period",
        "result": "Result",
        "employer": "Employer / unit",
        "job_family": "Function",
        "unit_type": "Unit type",
        "from_to": "Period",
        "appointment": "Basis",
        "present": "present",
        "competency": "Competency",
        "score": "Score",
        "assessed": "Assessed on",
        "metric": "Figure",
        "value": "Value",
        "yes": "yes", "no": "no", "none": "no data",
        "footer": "Tenure figures are computed by the system from employment "
                  "intervals and are never entered by hand.",
        "appointment_types": {
            "initial": "initial appointment", "transfer": "transfer",
            "promotion": "promotion", "return": "return",
            "external": "external employer",
        },
        "statuses": {"draft": "draft", "in_review": "in review",
                     "verified": "verified", "archived": "archived"},
        "metric_names": {
            "company_experience_years": "Company tenure, years",
            "total_experience_years": "Total experience, years",
            "management_experience_years": "Management experience, years",
        },
        "metric_function": "Experience in function",
        "metric_unit": "Experience in units of type",
        "metric_country": "Experience in country",
    },
}


def _t(lang: str) -> Dict[str, Any]:
    return L.get(lang, L["ru"])


def _name(row, lang: str, attr: str = "name") -> str:
    if not row:
        return ""
    return (getattr(row, f"{attr}_{lang}", None)
            or getattr(row, f"{attr}_ru", None)
            or getattr(row, f"{attr}_en", None) or "")


def _fmt_date(value: Optional[date]) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


# ---------------------------------------------------------------------------
# Gather once, render twice
# ---------------------------------------------------------------------------

def build_cv_data(db: Session, employee: Employee, lang: str = "ru",
                  include_confidential: bool = False) -> Dict[str, Any]:
    t = _t(lang)
    metrics = compute_employee_metrics(db, employee)

    personal = [
        (t["full_name"], employee.full_name),
        (t["personnel_number"], employee.personnel_number or "—"),
        (t["code"], employee.anonymous_code or "—"),
        (t["birth"], " · ".join(p for p in (
            _fmt_date(employee.birth_date), employee.birth_place) if p) or "—"),
        (t["nationality"], _name(employee.nationality, lang) or "—"),
        (t["hire_date"], _fmt_date(employee.hire_date) or "—"),
        (t["position"], _name(employee.current_position, lang) or "—"),
        (t["org_unit"], _name(employee.current_org_unit, lang) or "—"),
        (t["email"], employee.email or "—"),
        (t["phone"], employee.phone or "—"),
        (t["status"], t["statuses"].get(employee.profile_status,
                                        employee.profile_status)),
    ]

    education = [[
        _name(row.level, lang),
        row.institution or "",
        _name(row.field, lang) or (row.qualification or ""),
        f"{row.start_year or ''}–{row.end_year or ''}".strip("–"),
    ] for row in sorted(employee.educations,
                        key=lambda r: r.end_year or 0, reverse=True)]

    languages = [[
        _name(row.language, lang),
        row.level.code if row.level else "",
        t["yes"] if row.is_confirmed else t["no"],
        row.document or "",
        _fmt_date(row.valid_until),
    ] for row in employee.languages]

    training = [[
        row.name or "",
        _name(row.job_family, lang),
        row.provider or "",
        f"{_fmt_date(row.date_from)} – {_fmt_date(row.date_to)}".strip(" –"),
        row.result or "",
    ] for row in sorted(employee.trainings,
                        key=lambda r: r.date_to or date.min, reverse=True)]

    career = []
    for row in sorted(employee.work_experience, key=lambda r: r.date_from,
                      reverse=True):
        employer = (_name(row.org_unit, lang) if row.is_internal
                    else (row.external_employer or ""))
        position = (_name(row.position, lang) if row.is_internal
                    else (row.external_position_title or ""))
        period = (f"{_fmt_date(row.date_from)} – "
                  f"{_fmt_date(row.date_to) if row.date_to else t['present']}")
        career.append([
            period, employer, position,
            _name(row.job_family, lang),
            _name(row.org_unit_type, lang),
            t["appointment_types"].get(row.appointment_type,
                                       row.appointment_type or ""),
        ])

    competencies = []
    sessions = sorted(employee.assessment_sessions,
                      key=lambda s: s.session_date, reverse=True)
    seen = set()
    for session in sessions:
        if session.session_type != "professional" and not include_confidential:
            continue
        for score in session.scores:
            if score.competency.is_confidential and not include_confidential:
                continue
            code = score.competency.code
            if code in seen:
                continue
            seen.add(code)
            scale_max = float(session.scale.max_value) if session.scale else None
            competencies.append([
                _name(score.competency, lang),
                f"{float(score.score):g}" + (f" / {scale_max:g}" if scale_max else ""),
                _fmt_date(session.session_date),
            ])

    derived = []
    for code, label in t["metric_names"].items():
        if code in metrics:
            derived.append([label, f"{metrics[code]:.1f}"])
    for key, value in sorted(metrics.items()):
        if key.startswith("function_experience_years:"):
            derived.append([f"{t['metric_function']} {key.split(':')[1]}",
                            f"{value:.1f}"])
        elif key.startswith("org_unit_experience_years:"):
            derived.append([f"{t['metric_unit']} {key.split(':')[1]}",
                            f"{value:.1f}"])
        elif key.startswith("country_experience_years:"):
            derived.append([f"{t['metric_country']} {key.split(':')[1]}",
                            f"{value:.1f}"])

    return {
        "lang": lang,
        "t": t,
        "employee": employee,
        "generated_at": date.today(),
        "personal": personal,
        "sections": [
            {"key": "education", "title": t["education"],
             "headers": [t["level"], t["institution"], t["field"], t["years"]],
             "rows": education, "widths": [22, 33, 27, 18]},
            {"key": "languages", "title": t["languages"],
             "headers": [t["language"], t["lang_level"], t["confirmed"],
                         t["document"], t["valid_until"]],
             "rows": languages, "widths": [22, 14, 16, 28, 20]},
            {"key": "training", "title": t["training"],
             "headers": [t["course"], t["job_family"], t["provider"],
                         t["period"], t["result"]],
             "rows": training, "widths": [28, 18, 22, 20, 12]},
            {"key": "career", "title": t["career"],
             "headers": [t["from_to"], t["employer"], t["position"],
                         t["job_family"], t["unit_type"], t["appointment"]],
             "rows": career, "widths": [19, 20, 20, 14, 14, 13]},
            {"key": "competencies", "title": t["competencies"],
             "headers": [t["competency"], t["score"], t["assessed"]],
             "rows": competencies, "widths": [50, 25, 25]},
            {"key": "metrics", "title": t["metrics"],
             "headers": [t["metric"], t["value"]],
             "rows": derived, "widths": [70, 30]},
        ],
    }


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _register_fonts():
    """Embed a Cyrillic-capable font; fall back to Helvetica if absent."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular, bold = FONT_CANDIDATES[0], FONT_CANDIDATES[1]
    if not os.path.exists(regular):
        return "Helvetica", "Helvetica-Bold"

    try:
        if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("DejaVuSans", regular))
        if os.path.exists(bold):
            if "DejaVuSans-Bold" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
            return "DejaVuSans", "DejaVuSans-Bold"
        return "DejaVuSans", "DejaVuSans"
    except Exception:                                            # noqa: BLE001
        return "Helvetica", "Helvetica-Bold"


def render_pdf(data: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)

    regular, bold = _register_fonts()
    t = data["t"]
    employee = data["employee"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{t['title']} — {employee.full_name}",
        author="Цифровой профиль сотрудника",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("T", parent=styles["Title"], fontName=bold,
                           fontSize=15, leading=19, alignment=TA_CENTER,
                           textColor=colors.HexColor("#0f172a"))
    sub = ParagraphStyle("S", parent=styles["Normal"], fontName=regular,
                         fontSize=9, leading=12, alignment=TA_CENTER,
                         textColor=colors.HexColor("#64748b"))
    head = ParagraphStyle("H", parent=styles["Heading2"], fontName=bold,
                          fontSize=10.5, leading=14, spaceBefore=9, spaceAfter=4,
                          textColor=colors.HexColor("#0f6b6b"))
    cell = ParagraphStyle("C", parent=styles["Normal"], fontName=regular,
                          fontSize=8.2, leading=10.5)
    cell_b = ParagraphStyle("CB", parent=cell, fontName=bold)
    note = ParagraphStyle("N", parent=styles["Normal"], fontName=regular,
                          fontSize=7.5, leading=10,
                          textColor=colors.HexColor("#64748b"))

    story = [Paragraph(t["title"], title),
             Paragraph(f"{t['subtitle']} · {t['generated']}: "
                       f"{_fmt_date(data['generated_at'])}", sub),
             Spacer(1, 7 * mm)]

    grid = TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])

    # --- personal block (label / value) ---
    story.append(Paragraph(t["personal"], head))
    width = doc.width
    personal_rows = [[Paragraph(escape(str(k)), cell_b), Paragraph(escape(str(v)), cell)]
                     for k, v in data["personal"]]
    table = Table(personal_rows, colWidths=[width * 0.32, width * 0.68])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    # --- tabular sections ---
    for section in data["sections"]:
        story.append(Paragraph(section["title"], head))
        if not section["rows"]:
            story.append(Paragraph(t["none"], note))
            continue
        header = [Paragraph(escape(str(h)), cell_b) for h in section["headers"]]
        body = [[Paragraph(escape(str(c or "")), cell) for c in row]
                for row in section["rows"]]
        widths = [width * (w / 100.0) for w in section["widths"]]
        table = Table([header] + body, colWidths=widths, repeatRows=1)
        table.setStyle(grid)
        story.append(table)

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(t["footer"], note))

    def _footer(canvas, document):
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(18 * mm, 10 * mm, employee.full_name)
        canvas.drawRightString(document.pagesize[0] - 18 * mm, 10 * mm,
                               str(canvas.getPageNumber()))
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def render_docx(data: Dict[str, Any]) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor, Cm

    t = data["t"]
    employee = data["employee"]

    document = Document()

    for section in document.sections:
        section.top_margin = Cm(1.6)
        section.bottom_margin = Cm(1.6)
        section.left_margin = Cm(1.8)
        section.right_margin = Cm(1.8)

    normal = document.styles["Normal"]
    normal.font.name = "DejaVu Sans"
    normal.font.size = Pt(9)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(t["title"])
    run.bold = True
    run.font.size = Pt(15)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(f"{t['subtitle']} · {t['generated']}: "
                           f"{_fmt_date(data['generated_at'])}")
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    def add_heading(text):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(10)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(text)
        run.bold = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = RGBColor(0x0F, 0x6B, 0x6B)

    add_heading(t["personal"])
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in data["personal"]:
        cells = table.add_row().cells
        cells[0].text = str(label)
        cells[0].paragraphs[0].runs[0].bold = True
        cells[1].text = str(value)

    for section in data["sections"]:
        add_heading(section["title"])
        if not section["rows"]:
            paragraph = document.add_paragraph()
            run = paragraph.add_run(t["none"])
            run.italic = True
            run.font.size = Pt(8.5)
            run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
            continue

        table = document.add_table(rows=1, cols=len(section["headers"]))
        table.style = "Table Grid"
        for index, header in enumerate(section["headers"]):
            cell = table.rows[0].cells[index]
            cell.text = str(header)
            cell.paragraphs[0].runs[0].bold = True

        for row in section["rows"]:
            cells = table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = str(value or "")

    document.add_paragraph()
    footer = document.add_paragraph()
    run = footer.add_run(t["footer"])
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def safe_filename(employee: Employee, extension: str) -> str:
    """A strictly ASCII filename for the Content-Disposition header.

    HTTP headers are latin-1, and str.isalnum() is True for Cyrillic, so
    filtering on isalnum() alone lets "А" through and the response blows up
    when Starlette encodes the header. Only ASCII letters and digits survive
    here; the readable Unicode name travels in filename*=UTF-8'' instead.
    """
    parts = [employee.personnel_number or "", f"id{employee.id}"]
    stem = "_".join(p for p in parts if p)
    ascii_stem = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "-_")) else "_"
        for ch in stem
    ).strip("_")
    return f"CV_{ascii_stem or f'id{employee.id}'}.{extension}"
