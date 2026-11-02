"""Word report rendering from an already authorised immutable snapshot."""
import io
from datetime import datetime


def render_report_docx(snapshot, spec):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    kk=snapshot['lang']=='kk'
    def tr(ru,kz): return kz if kk else ru
    doc=Document(); page=doc.sections[0]
    landscape=spec['orientation']=='landscape'
    page.orientation=WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    page.page_width=Cm(29.7 if landscape else 21); page.page_height=Cm(21 if landscape else 29.7)
    page.left_margin=page.right_margin=Cm(1.7)
    page.top_margin=Cm(1.6); page.bottom_margin=Cm(1.7)
    page.header_distance=page.footer_distance=Cm(.8)
    width=26.3 if landscape else 17.6
    # A black Title style without the default Word template's blue border.
    for node in list(doc.styles.element.iter(qn('w:pBdr'))): node.getparent().remove(node)
    for name in ('Normal','Title','Subtitle','Heading 1','Heading 2'):
        s=doc.styles[name]; s.font.name='Calibri'; s.font.color.rgb=RGBColor(0,0,0); s.font.italic=False
        s.paragraph_format.space_after=Pt(6); s.paragraph_format.line_spacing=1.08
        s.paragraph_format.widow_control=True
    doc.styles['Normal'].font.size=Pt(10)
    doc.styles['Title'].font.size=Pt(25); doc.styles['Title'].font.bold=True
    doc.styles['Title'].paragraph_format.keep_with_next=True
    doc.styles['Subtitle'].font.size=Pt(10)
    for name,size in [('Heading 1',14),('Heading 2',11)]:
        s=doc.styles[name];s.font.size=Pt(size);s.font.bold=True
        s.paragraph_format.space_before=Pt(14);s.paragraph_format.keep_with_next=True
    doc.core_properties.author='';doc.core_properties.last_modified_by='';doc.core_properties.title=snapshot['title']
    header=page.header.paragraphs[0]
    header.text=tr('КАДРОВАЯ АНАЛИТИКА','КАДРЛЫҚ ТАЛДАУ')
    for run in header.runs: run.font.size=Pt(8);run.font.color.rgb=RGBColor(0,0,0)
    stamp=datetime.fromisoformat(snapshot['generated_at'].replace('Z','+00:00')).strftime('%d.%m.%Y %H:%M UTC')
    doc.add_paragraph(snapshot['title'],'Title')
    doc.add_paragraph(tr('Срез данных на ','Деректер кесіндісі ')+stamp,'Subtitle')
    doc.add_paragraph(tr('Количество кадровых запросов: ','Кадрлық сұраулар саны: ')+str(len(snapshot['sections']))+
        tr('. Действующих сотрудников в базе: ','. Дерекқордағы жұмыс істейтін қызметкерлер: ')+str(snapshot['total_employees'])+'.')
    p=doc.add_paragraph(snapshot['notice']);p.paragraph_format.space_after=Pt(12)
    for run in p.runs: run.font.size=Pt(9);run.font.color.rgb=RGBColor.from_string('52606D')

    fills={'navy':('203B53','F1F5F8'),'teal':('344B4B','F1F6F5'),'mono':('343A40','F4F4F4')}
    head_fill,stripe=fills[spec['style']]
    def table(headers,rows,weights,short_columns=()):
        notes=[]
        t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
        widths=[width*w/sum(weights) for w in weights]
        for column,w in zip(t.columns,widths): column.width=Cm(w)
        props=t._tbl.tblPr
        borders=OxmlElement('w:tblBorders')
        for edge in ('top','left','bottom','right','insideH','insideV'):
            item=OxmlElement('w:'+edge);item.set(qn('w:val'),'single');item.set(qn('w:sz'),'4');item.set(qn('w:color'),'D9D9D9');borders.append(item)
        props.append(borders)
        margins=OxmlElement('w:tblCellMar')
        for edge,value in [('top','90'),('bottom','90'),('left','110'),('right','110')]:
            item=OxmlElement('w:'+edge);item.set(qn('w:w'),value);item.set(qn('w:type'),'dxa');margins.append(item)
        props.append(margins)
        def fill_row(row,values,header=False,index=0):
            if header:
                repeat=OxmlElement('w:tblHeader');row._tr.get_or_add_trPr().append(repeat)
            # Extremely long fields are reproduced in full immediately after
            # this table. A short excerpt and numbered reference keep the row
            # readable without silently dropping any source text.
            display=[]
            for i,value in enumerate(values):
                text=str(value)
                if not header and len(text)>500:
                    notes.append((index+1,headers[i],text))
                    preview=text[:170].rsplit(' ',1)[0] if ' ' in text[:170] else text[:170]
                    text=preview+' … ['+str(len(notes))+']'
                display.append(text)
            if max((len(v) for v in display),default=0)<700:
                row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for i,(cell,value) in enumerate(zip(row.cells,display)):
                cell.width=Cm(widths[i]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),head_fill if header else stripe if index%2 else 'FFFFFF');cell._tc.get_or_add_tcPr().append(shade)
                p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0)
                p.paragraph_format.keep_with_next=header
                if i in short_columns: p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                run=p.add_run(str(value));run.font.size=Pt(9.5);run.bold=header
                run.font.color.rgb=RGBColor.from_string('FFFFFF' if header else '18232C')
        fill_row(t.rows[0],headers,True)
        for index,values in enumerate(rows): fill_row(t.add_row(),values,index=index)
        if notes:
            doc.add_paragraph(tr('Полные значения длинных полей','Ұзын өрістердің толық мәндері'),'Heading 2')
            for number,(row_number,label,value) in enumerate(notes,1):
                caption=doc.add_paragraph(f'[{number}] '+tr('Строка ','Жол ')+str(row_number)+' · '+label)
                caption.paragraph_format.keep_with_next=True
                caption.paragraph_format.space_after=Pt(3)
                for run in caption.runs: run.bold=True;run.font.size=Pt(9)
                full=doc.add_paragraph(value)
                for run in full.runs: run.font.size=Pt(9)
        else:
            spacer=doc.add_paragraph();spacer.paragraph_format.space_after=Pt(1)
            spacer.paragraph_format.space_before=Pt(0);spacer.paragraph_format.line_spacing=Pt(3)
        return t

    sections=snapshot['sections']; columns=snapshot['columns']
    if spec['include_summary'] or spec['layout']=='summary':
        doc.add_paragraph(tr('Сводка по вопросам','Сұрақтар бойынша жиынтық'),'Heading 1')
        table([tr('№','№'),tr('Условия поиска','Іздеу шарттары'),tr('Найдено','Табылды'),tr('Доля','Үлесі')],
              [[i+1,s['summary'],s['count'],str(s['percent'])+' %'] for i,s in enumerate(sections)], [0.7,7,1.2,1.2],(0,2,3))

    if spec['layout']=='summary':
        doc.add_paragraph(tr('Вопросы диалога','Диалог сұрақтары'),'Heading 1')
        for i,s in enumerate(sections):
            question=doc.add_paragraph(f"{i+1}. {s['question']}")
            question.paragraph_format.keep_with_next=bool(s['breakdown'])
            if s['breakdown']:
                table([tr('Группа','Топ'),tr('Количество','Саны')],[[r['label'],r['count']] for r in s['breakdown']],[6,1],(1,))
    else:
        weights={'code':1.4,'name':3,'position':3.1,'unit':3.1,'profile_status':2,
                 'education':2.4,'languages':2.4,'company_experience_years':1.65,
                 'total_experience_years':1.65,'management_experience_years':1.65,
                 'candidate_points':1.7,'candidate_max_points':1.7,'candidate_percent':1.9,
                 'candidate_completeness':3,'candidate_version':1.5,'candidate_technical_profile':2}
        labels=[c['label'].replace(', ','\n') if c['key'].endswith('_years') else c['label'] for c in columns]
        keys=[c['key'] for c in columns]
        short=[i for i,key in enumerate(keys) if key.endswith('_years') or key in ('code','candidate_points','candidate_max_points','candidate_percent','candidate_version')]
        if spec['layout']=='table':
            doc.add_paragraph(tr('Вопросы отчёта','Есеп сұрақтары'),'Heading 1')
            for i,s in enumerate(sections): doc.add_paragraph(f"{i+1}. {s['question']}\n{s['summary']}")
            doc.add_paragraph(tr('Общая таблица сотрудников','Қызметкерлердің жалпы кестесі'),'Heading 1')
            rows=[[i+1,*[r.get(k,'—') for k in keys]] for i,s in enumerate(sections) for r in s['rows']]
            if rows: table([tr('Вопрос','Сұрақ'),*labels],rows,[1.2,*[weights[k] for k in keys]],(0,*[i+1 for i in short]))
            else: doc.add_paragraph(tr('Сотрудники по выбранным условиям не найдены.','Таңдалған шарттар бойынша қызметкерлер табылмады.'))
        else:
            for i,s in enumerate(sections):
                doc.add_paragraph(tr('Вопрос ','Сұрақ ')+str(i+1),'Heading 1')
                question=doc.add_paragraph(s['question'])
                question.paragraph_format.keep_with_next=True
                doc.add_paragraph(s['summary'],'Heading 2')
                count=doc.add_paragraph(tr('Найдено ','Табылды ')+str(s['count'])+tr(' из ',' / ')+str(s['total'])+f" ({s['percent']} %)")
                count.paragraph_format.keep_with_next=True
                if s['rows']: table(labels,[[r.get(k,'—') for k in keys] for r in s['rows']],[weights[k] for k in keys],short)
                else: doc.add_paragraph(tr('Подходящих сотрудников нет.','Сәйкес қызметкерлер жоқ.'))
    footer=page.footer.paragraphs[0]
    footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run(tr('Локальный отчёт   |   Страница ','Жергілікті есеп   |   Бет ')).font.size=Pt(8)
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    stream=io.BytesIO();doc.save(stream);return stream.getvalue()
