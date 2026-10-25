"""Deterministic text merge and print-ready US letter PDFs."""
import io,re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
from .core import require

def merge(text,recipient):
    return re.sub(r'\{\{\s*(\w+)\s*\}\}',lambda m:str(recipient.get(m[1],recipient.get('custom',{}).get(m[1],''))),text)
def letter_pdf(data,recipients=None,cover=False):
    require(data.get('kind','letter')!='postcard','Postcard artwork requires an uploaded PDF')
    buf=io.BytesIO(); styles=getSampleStyleSheet(); style=ParagraphStyle('letter',parent=styles['Normal'],fontName='Helvetica',fontSize=11,leading=16,spaceAfter=10)
    doc=SimpleDocTemplate(buf,pagesize=(612,792),rightMargin=54,leftMargin=54,topMargin=54,bottomMargin=54,title='Postmaster mailing',author='Postmaster')
    story=[]
    for i,recipient in enumerate(recipients or data.get('recipients',[])):
        if i: story.append(PageBreak())
        if cover:
            sender=data['sender']; story.append(Paragraph('<b>RETURN ADDRESS</b>',style))
            for k in ('name','company','street','street2'): 
                if sender.get(k): story.append(Paragraph(escape(sender[k]),style))
            story.append(Paragraph(escape(f"{sender['city']} {sender.get('state','')} {sender['postal_code']} {sender['country']}"),style)); story.append(Spacer(1,95));story.append(Paragraph('<b>DELIVER TO</b>',style))
            for k in ('name','company','street','street2'):
                if recipient.get(k): story.append(Paragraph(escape(recipient[k]),style))
            story.append(Paragraph(escape(f"{recipient['city']} {recipient.get('state','')} {recipient['postal_code']} {recipient['country']}"),style)); story.append(PageBreak())
        text=merge(str(data.get('body','')),recipient)
        for paragraph in text.split('\n\n'):
            story.append(Paragraph(escape(paragraph).replace('\n','<br/>') or ' ',style));story.append(Spacer(1,5))
    doc.build(story);return buf.getvalue()
def text_pages(data):
    from pypdf import PdfReader
    counts=[len(PdfReader(io.BytesIO(letter_pdf(data,[r]))).pages) for r in data['recipients']]
    return max(counts)
