"""Gera a versão editável do relatório (docs/Relatorio_Visao_Computacional_Calcada_Livre.docx).

Usa exatamente o mesmo conteúdo do PDF (scripts/10_report.py): o texto, as tabelas e as figuras são
percorridos e reescritos como elementos nativos do Word, com a mesma formatação ABNT (Times New Roman 12,
espaçamento 1,5, recuo de 1,25 cm, margens 3/2 cm, títulos numerados, legendas acima e fonte abaixo,
tabelas abertas nas laterais e paginação a partir da introdução). Assim o arquivo abre no Word e no
Google Docs sem perder a formatação, o que não acontece ao converter o PDF.

Uso:  python scripts/10b_report_docx.py
"""
from __future__ import annotations

import html
import importlib.util
import io
import re
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, Spacer, Table

AQUI = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("relatorio", AQUI / "10_report.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

OUT = R.ROOT / "docs" / "Relatorio_Visao_Computacional_Calcada_Livre.docx"
FONTE = "Times New Roman"
# títulos que começam em página nova no Docs, para a tabela logo abaixo não ser dividida
QUEBRA_ANTES = {"5.2 TEMPO REAL E COMPARAÇÃO DE ARQUITETURAS"}
PRETO = RGBColor(0, 0, 0)


# ------------------------------------------------------------------ utilidades de formatação
def _fmt(par, alinhamento=WD_ALIGN_PARAGRAPH.JUSTIFY, recuo=True, espaco=1.5, antes=0, depois=0):
    pf = par.paragraph_format
    pf.alignment = alinhamento
    pf.first_line_indent = Cm(1.25) if recuo else Cm(0)
    pf.line_spacing = espaco
    pf.space_before = Pt(antes)
    pf.space_after = Pt(depois)
    return par


def _runs(par, markup: str, tamanho: float = 12, negrito: bool = False):
    """Converte o markup simples do reportlab (<b>, <i>, <br/>, <link>) em runs do Word."""
    markup = re.sub(r"<link[^>]*>(.*?)</link>", r"\1", markup)
    b, i = negrito, False
    for parte in re.split(r"(<b>|</b>|<i>|</i>|<br/>)", markup):
        if parte == "<b>":
            b = True
        elif parte == "</b>":
            b = negrito
        elif parte == "<i>":
            i = True
        elif parte == "</i>":
            i = False
        elif parte == "<br/>":
            par.add_run().add_break(WD_BREAK.LINE)
        elif parte:
            r = par.add_run(html.unescape(parte))
            r.bold, r.italic = b, i
            r.font.size = Pt(tamanho)
            r.font.name = FONTE
            r.font.color.rgb = PRETO
    return par


def _keep(par):
    par.paragraph_format.keep_with_next = True
    return par


def _bordas_tabela(tabela, quadro: bool):
    """Quadro: todas as bordas. Tabela (IBGE): traço no topo, sob o cabeçalho e no fim; laterais abertas."""
    tblPr = tabela._tbl.tblPr
    bordas = OxmlElement("w:tblBorders")
    lados = {"top": 8, "bottom": 8} if not quadro else {k: 6 for k in ("top", "left", "bottom", "right", "insideH", "insideV")}
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{lado}")
        if lado in lados:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(lados[lado]))
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
        bordas.append(el)
    tblPr.append(bordas)
    if not quadro:  # traço sob o cabeçalho
        for cel in tabela.rows[0].cells:
            tcPr = cel._tc.get_or_add_tcPr()
            tcb = OxmlElement("w:tcBorders")
            el = OxmlElement("w:bottom")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "000000")
            tcb.append(el)
            tcPr.append(tcb)


def _campo(par, instrucao: str, tamanho: float = 10):
    """Insere um campo do Word (ex.: PAGE) no parágrafo."""
    for tipo, texto in (("begin", None), (None, instrucao), ("separate", None), (None, "1"), ("end", None)):
        r = par.add_run()
        r.font.size = Pt(tamanho)
        r.font.name = FONTE
        if tipo:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), tipo)
            r._r.append(fc)
        elif texto == instrucao:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = f" {instrucao} "
            r._r.append(it)
        else:
            r.text = texto


def _desenho_png(desenho: Drawing) -> str:
    """Rasteriza um desenho vetorial do reportlab em PNG de alta resolução (via PDF temporário)."""
    import pymupdf
    from reportlab.graphics import renderPDF

    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / "d.pdf"
    renderPDF.drawToFile(desenho, str(pdf))
    pix = pymupdf.open(str(pdf))[0].get_pixmap(dpi=300)
    png = tmp / "d.png"
    pix.save(str(png))
    return str(png)


# ------------------------------------------------------------------ documento
class Construtor:
    def __init__(self):
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = FONTE
        st.font.size = Pt(12)
        st.font.color.rgb = PRETO
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONTE)
        st.paragraph_format.space_after = Pt(0)
        st.paragraph_format.line_spacing = 1.5
        for nome, negrito in (("Heading 1", True), ("Heading 2", False)):
            h = self.doc.styles[nome]
            h.font.name, h.font.size, h.font.bold, h.font.italic = FONTE, Pt(12), negrito, False
            h.font.color.rgb = PRETO
            rpr = h.element.get_or_add_rPr()
            rpr.rFonts.set(qn("w:ascii"), FONTE)
            rpr.rFonts.set(qn("w:hAnsi"), FONTE)
            h.paragraph_format.space_before = Pt(18 if nome == "Heading 2" else 0)
            h.paragraph_format.space_after = Pt(18)
            h.paragraph_format.line_spacing = 1.5
            h.paragraph_format.keep_with_next = True
        s = self.doc.sections[0]
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.top_margin, s.left_margin, s.bottom_margin, s.right_margin = Cm(3), Cm(3), Cm(2), Cm(2)
        s.header_distance = Cm(2)
        self.quebra_pendente = False

    # ---------------- elementos simples
    def par(self, markup="", alinhamento=WD_ALIGN_PARAGRAPH.JUSTIFY, recuo=True, espaco=1.5, tamanho=12, negrito=False,
            antes=0, depois=0, estilo=None):
        p = self.doc.add_paragraph(style=estilo) if estilo else self.doc.add_paragraph()
        _fmt(p, alinhamento, recuo, espaco, antes, depois)
        if self.quebra_pendente:
            p.paragraph_format.page_break_before = True
            self.quebra_pendente = False
        if markup:
            _runs(p, markup, tamanho, negrito)
        return p

    def quebra(self):
        self.quebra_pendente = True

    # ---------------- capa e folha de rosto
    def capa(self, rosto: bool):
        autores = "<br/>".join(f"{n.upper()} (RM {rm})" for n, rm in R.TEAM)
        titulo = "<b>CALÇADA LIVRE</b>:<br/>detecção de barreiras em calçadas em tempo real com YOLO26"
        c = WD_ALIGN_PARAGRAPH.CENTER
        if not rosto:
            self.par("<b>FIAP</b><br/><b>ENGENHARIA DE SOFTWARE</b>", c, False)
            self.par(autores, c, False, antes=60)
            self.par(titulo, c, False, antes=150)
            self.par("<b>SÃO PAULO</b><br/><b>2026</b>", c, False, antes=230)
        else:
            self.par(autores, c, False)
            self.par(titulo, c, False, antes=150)
            p = self.par(f"Relatório técnico apresentado à disciplina Applied Computer Vision do curso de Engenharia de "
                         f"Software da FIAP, como parte da Global Solution 2026.2 (desafio CitizenTech).<br/><br/>"
                         f"Professores: {R.PROFS.replace('Prof. ', '')}.",
                         WD_ALIGN_PARAGRAPH.LEFT, False, espaco=1.0, antes=50)
            p.paragraph_format.left_indent = Cm(8)
            self.par("<b>SÃO PAULO</b><br/><b>2026</b>", c, False, antes=120)

    # ---------------- sumário (campo TOC com as entradas já preenchidas)
    def sumario(self, reg, paginas_docs: dict | None = None):
        self.par("<b>SUMÁRIO</b>", WD_ALIGN_PARAGRAPH.CENTER, False, depois=18)
        entradas = [(t, n, txt, reg.pagina(ch)) for t, n, txt, ch in reg.itens if t in ("sec0", "sec1", "sec2")]
        for k, (tipo, n, txt, pag) in enumerate(entradas):
            p = self.par("", WD_ALIGN_PARAGRAPH.LEFT, False)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(1.4))
            p.paragraph_format.tab_stops.add_tab_stop(Cm(16), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            if k == 0:
                for tp, txt_campo in (("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None)):
                    r = p.add_run()
                    if tp:
                        fc = OxmlElement("w:fldChar")
                        fc.set(qn("w:fldCharType"), tp)
                        r._r.append(fc)
                    else:
                        it = OxmlElement("w:instrText")
                        it.set(qn("xml:space"), "preserve")
                        it.text = txt_campo
                        r._r.append(it)
            texto = (f"{n}\t{txt}" if n else txt) + f"\t{pag}"
            _runs(p, texto, 12, tipo in ("sec0", "sec1"))
            if k == len(entradas) - 1:
                r = p.add_run()
                fc = OxmlElement("w:fldChar")
                fc.set(qn("w:fldCharType"), "end")
                r._r.append(fc)

    # ---------------- seção textual com paginação
    def nova_secao_numerada(self, inicio: int):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.header.is_linked_to_previous = False
        p = sec.header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _campo(p, "PAGE")
        pg = OxmlElement("w:pgNumType")
        pg.set(qn("w:start"), str(inicio))
        sec._sectPr.append(pg)
        self.quebra_pendente = False

    # ---------------- ilustrações e tabelas
    def bloco(self, tabela_externa):
        linhas = tabela_externa._cellvalues
        legenda = linhas[0][0].text
        miolo = linhas[1][0]
        rodape = [l[0].text for l in linhas[2:]]
        cab = _keep(self.par(legenda, WD_ALIGN_PARAGRAPH.CENTER, False, espaco=1.0, tamanho=10, antes=6))
        if isinstance(miolo, Image):
            self._imagem(miolo.filename, miolo.drawWidth)
        elif isinstance(miolo, Drawing):
            self._imagem(_desenho_png(miolo), R.LARGURA)
        elif isinstance(miolo, Table) and isinstance(miolo._cellvalues[0][0], Image):
            for k, (img,) in enumerate(miolo._cellvalues):
                p = self._imagem(img.filename, img.drawWidth)
                if k < len(miolo._cellvalues) - 1:
                    _keep(p)
        elif isinstance(miolo, Table):
            self._tabela(miolo, quadro=legenda.startswith("Quadro"))
        cab.paragraph_format.keep_with_next = True
        for k, r in enumerate(rodape):
            self.par(r, WD_ALIGN_PARAGRAPH.LEFT if not isinstance(miolo, Table) or isinstance(miolo._cellvalues[0][0], Image)
                     else WD_ALIGN_PARAGRAPH.LEFT, False, espaco=1.0, tamanho=10, depois=(12 if k == len(rodape) - 1 else 0))
        if not rodape:
            self.par("", espaco=1.0, tamanho=6)

    def _imagem(self, caminho, largura_pt):
        p = self.par("", WD_ALIGN_PARAGRAPH.CENTER, False, espaco=1.0)
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(caminho), width=Cm(largura_pt / 72 * 2.54))
        return p

    def _tabela(self, t, quadro: bool):
        dados = t._cellvalues
        larguras = t._colWidths
        tab = self.doc.add_table(rows=len(dados), cols=len(dados[0]))
        tab.alignment = WD_TABLE_ALIGNMENT.CENTER
        tab.autofit = False
        for j, w in enumerate(larguras):
            tab.columns[j].width = Cm(w / 72 * 2.54)
        mar = OxmlElement("w:tblCellMar")
        for lado in ("left", "right"):
            el = OxmlElement(f"w:{lado}")
            el.set(qn("w:w"), "57")
            el.set(qn("w:type"), "dxa")
            mar.append(el)
        tab._tbl.tblPr.append(mar)
        for i, linha in enumerate(dados):
            for j, cel in enumerate(linha):
                c = tab.cell(i, j)
                c.width = Cm(larguras[j] / 72 * 2.54)
                p = c.paragraphs[0]
                cab = i == 0
                alinh = WD_ALIGN_PARAGRAPH.CENTER if (cab or (j > 0 and not quadro)) else WD_ALIGN_PARAGRAPH.LEFT
                _fmt(p, alinh, False, 1.0)
                _runs(p, cel.text if isinstance(cel, Paragraph) else str(cel), 10, cab)
                if i < len(dados) - 1:
                    p.paragraph_format.keep_with_next = True  # tabela não se divide entre páginas
            trPr = tab.rows[i]._tr.get_or_add_trPr()
            trPr.append(OxmlElement("w:cantSplit"))
        _bordas_tabela(tab, quadro)

    def formula(self, t):
        txt, num = t._cellvalues[0][1].text, t._cellvalues[0][2].text
        p = self.par("", WD_ALIGN_PARAGRAPH.LEFT, False, antes=4, depois=4)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(8), WD_TAB_ALIGNMENT.CENTER)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(16), WD_TAB_ALIGNMENT.RIGHT)
        _runs(p, f"\t{txt}\t{num}")

    # ---------------- corpo
    def corpo(self, flowables):
        for f in flowables:
            if isinstance(f, PageBreak):
                self.quebra_pendente = True
            elif isinstance(f, Spacer):
                continue
            elif isinstance(f, KeepTogether):
                for g in f._content:
                    if isinstance(g, Table) and getattr(g, "_chave", None) is not None:
                        self.bloco(g)
                    elif isinstance(g, Paragraph):
                        self.paragrafo(g)
            elif isinstance(f, Table):
                if getattr(f, "_chave", None) is not None:
                    self.bloco(f)
                else:
                    self.formula(f)
            elif isinstance(f, Paragraph):
                self.paragrafo(f)

    def paragrafo(self, p: Paragraph):
        nome = p.style.name
        if nome == "t1":
            _keep(self.par(p.text, WD_ALIGN_PARAGRAPH.LEFT, False, negrito=True, depois=18, estilo="Heading 1"))
        elif nome == "t2":
            h = _keep(self.par(p.text, WD_ALIGN_PARAGRAPH.LEFT, False, antes=18, depois=18, estilo="Heading 2"))
            if p.text in QUEBRA_ANTES:
                h.paragraph_format.page_break_before = True
                h.paragraph_format.space_before = Pt(0)
        elif nome == "tc":  # REFERÊNCIAS
            h = self.par(p.text, WD_ALIGN_PARAGRAPH.CENTER, False, negrito=True, depois=18, estilo="Heading 1")
            h.paragraph_format.page_break_before = True
        elif nome == "ref":
            self.par(p.text, WD_ALIGN_PARAGRAPH.LEFT, False, espaco=1.0, depois=12)
        elif nome == "sem_recuo":
            self.par(p.text, recuo=False)
        else:
            self.par(p.text)


def main() -> None:
    import json
    import sys

    # opcional: páginas medidas no Google Docs (json {título: página}) para o sumário bater com o Docs
    paginas_docs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
    doc_pdf, _, _ = R.montar({}, io.BytesIO())       # páginas do PDF para pré-preencher o sumário
    d = R.carregar()
    reg = R.Registro(doc_pdf.paginas)
    corpo, resumo, _abstract, nr, no = R.conteudo(reg, d)

    b = Construtor()
    b.capa(rosto=False)
    b.quebra()
    b.capa(rosto=True)
    b.quebra()
    b.par("<b>RESUMO</b>", WD_ALIGN_PARAGRAPH.CENTER, False, depois=18)
    b.par(resumo, recuo=False)
    b.par("<b>Palavras-chave:</b> visão computacional; detecção de objetos; YOLO26; acessibilidade urbana; calçadas.",
          recuo=False, antes=18)
    b.quebra()
    b.par("<b>LINKS DO PROJETO</b>", WD_ALIGN_PARAGRAPH.CENTER, False, depois=18)
    b.par(f"<b>Repositório no GitHub:</b> {R.REPO_URL}", recuo=False)
    b.par(f"<b>Vídeo de demonstração (YouTube):</b> {R.VIDEO_URL}", recuo=False, antes=18)
    b.quebra()
    b.sumario(reg, paginas_docs)
    # a introdução abre a seção numerada (a contagem começa na folha de rosto)
    b.nova_secao_numerada(int(reg.pagina("sec1-1") or 4))
    primeiro = True
    resto = []
    for f in corpo:
        if primeiro and isinstance(f, PageBreak):
            primeiro = False
            continue
        resto.append(f)
    b.corpo(resto)
    b.doc.core_properties.title = "Calçada Livre: detecção de barreiras em calçadas em tempo real com YOLO26"
    b.doc.core_properties.author = ", ".join(n for n, _ in R.TEAM)
    b.doc.save(str(OUT))
    print(f"Resumo: {nr} palavras | Objetivo: {no} palavras")
    print("DOCX gerado em", OUT)


if __name__ == "__main__":
    main()
