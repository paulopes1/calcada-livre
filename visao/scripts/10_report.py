"""Gera o relatório da disciplina em PDF, no padrão ABNT (docs/Relatorio_Visao_Computacional_Calcada_Livre.pdf).

Itens pedidos pela disciplina: título, integrantes, resumo (até 250 palavras), introdução, objetivo
(até 50 palavras), explicação técnica das ferramentas, metodologia passo a passo, exemplos de resultados
e conclusão. Formatação segundo a ABNT (NBR 14724, 6023, 6024, 6027, 6028 e 10520): papel A4, margens
de 3 cm (superior e esquerda) e 2 cm (inferior e direita), Times New Roman 12, espaçamento 1,5, recuo de
1,25 cm, títulos numerados, legendas acima das ilustrações com a fonte abaixo, tabelas abertas nas laterais,
paginação no canto superior direito a partir da introdução e referências em ordem alfabética.

Todos os números vêm dos arquivos de results/, e os limites de palavras são conferidos automaticamente.
O sumário e as listas são montados em duas passagens, para que os números de página saiam corretos.

Uso:  python scripts/10_report.py
      (links: variáveis de ambiente REPO_URL, VIDEO_URL e MVP_URL)
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = RES / "figuras"
OUT = ROOT / "docs" / "Relatorio_Visao_Computacional_Calcada_Livre.pdf"
REPO_URL = os.environ.get("REPO_URL", "https://github.com/paulopes1/calcada-livre")
MVP_REPO = "https://github.com/CarlosGanzerli/calcada-livre"
VIDEO_URL = os.environ.get("VIDEO_URL", "https://www.youtube.com/watch?v=oh_gcKEkcOc")  # vídeo de demonstração
MVP_URL = os.environ.get("MVP_URL", "")
ACESSO = "16 nov. 2026"
CARDEAL = 'Calçada abandonada na rua Cardeal Leme - "rua da Feira" (Bela Vista).webm'

TEAM = [("Carlos Ganzerli", "99840"), ("Paulo Lopes", "551137"), ("Lucas Bandeira", "98640"), ("Gustavo Melo", "98809")]
PROFS = "Prof. Arnaldo Viana e Prof. Paulo Rodrigues"
PRETO = colors.black

# ------------------------------------------------------------------ fonte (Times New Roman, com acentos)
def _fontes() -> tuple[str, str, str, str]:
    for pasta in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/msttcorefonts"), Path("/Library/Fonts")):
        arqs = [pasta / n for n in ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf")]
        if all(a.exists() for a in arqs):
            for nome, a in zip(("TNR", "TNR-B", "TNR-I", "TNR-BI"), arqs):
                pdfmetrics.registerFont(TTFont(nome, str(a)))
            pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-B", italic="TNR-I", boldItalic="TNR-BI")
            return "TNR", "TNR-B", "TNR-I", "TNR-BI"
    return "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"


T, TB, TI, TBI = _fontes()
LINHA = 18      # espaçamento 1,5 para corpo 12
SIMPLES = 14    # espaçamento simples para corpo 12

S = {
    "corpo": ParagraphStyle("corpo", fontName=T, fontSize=12, leading=LINHA, alignment=TA_JUSTIFY,
                            firstLineIndent=1.25 * cm, textColor=PRETO),
    "sem_recuo": ParagraphStyle("sem_recuo", fontName=T, fontSize=12, leading=LINHA, alignment=TA_JUSTIFY, textColor=PRETO),
    "t1": ParagraphStyle("t1", fontName=TB, fontSize=12, leading=LINHA, spaceAfter=LINHA, keepWithNext=1, textColor=PRETO),
    "t2": ParagraphStyle("t2", fontName=T, fontSize=12, leading=LINHA, spaceBefore=LINHA, spaceAfter=LINHA,
                         keepWithNext=1, textColor=PRETO),
    "t_centro": ParagraphStyle("tc", fontName=TB, fontSize=12, leading=LINHA, alignment=TA_CENTER, spaceAfter=LINHA,
                               textColor=PRETO),
    "legenda": ParagraphStyle("leg", fontName=T, fontSize=10, leading=12, alignment=TA_LEFT, textColor=PRETO),
    "fonte": ParagraphStyle("fonte", fontName=T, fontSize=10, leading=12, alignment=TA_LEFT, textColor=PRETO),
    "celula": ParagraphStyle("cel", fontName=T, fontSize=10, leading=12, alignment=TA_LEFT, textColor=PRETO),
    "celula_c": ParagraphStyle("celc", fontName=T, fontSize=10, leading=12, alignment=TA_CENTER, textColor=PRETO),
    "celula_b": ParagraphStyle("celb", fontName=TB, fontSize=10, leading=12, alignment=TA_CENTER, textColor=PRETO),
    "referencia": ParagraphStyle("ref", fontName=T, fontSize=12, leading=SIMPLES, alignment=TA_LEFT, spaceAfter=SIMPLES,
                                 textColor=PRETO),
    "centro": ParagraphStyle("centro", fontName=T, fontSize=12, leading=SIMPLES, alignment=TA_CENTER, textColor=PRETO),
    "centro_b": ParagraphStyle("centro_b", fontName=TB, fontSize=12, leading=LINHA, alignment=TA_CENTER, textColor=PRETO),
    "natureza": ParagraphStyle("nat", fontName=T, fontSize=12, leading=SIMPLES, alignment=TA_LEFT, textColor=PRETO),
    "formula": ParagraphStyle("formula", fontName=T, fontSize=12, leading=LINHA, alignment=TA_CENTER, textColor=PRETO),
}
LARGURA = A4[0] - 5 * cm   # 16 cm de área útil


def P(texto: str, estilo: str = "corpo") -> Paragraph:
    return Paragraph(texto, S[estilo])


def palavras(texto: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", texto).split())


def pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def milhar(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def link(url: str) -> str:
    return f"<link href='{url}' color='black'>{url}</link>"


# ------------------------------------------------------------------ registro para sumário e listas
class Registro:
    def __init__(self, paginas: dict[str, int]):
        self.paginas = paginas
        self.itens: list[tuple[str, str, str, str]] = []  # (tipo, número, texto, chave)
        self.cont = {"fig": 0, "tab": 0, "quadro": 0}

    def novo(self, tipo: str, texto: str) -> tuple[int, str]:
        self.cont[tipo] += 1
        n = self.cont[tipo]
        chave = f"{tipo}-{n}"
        self.itens.append((tipo, str(n), texto, chave))
        return n, chave

    def secao(self, tipo: str, numero: str, texto: str) -> str:
        chave = f"{tipo}-{numero or texto}"
        self.itens.append((tipo, numero, texto, chave))
        return chave

    def pagina(self, chave: str) -> str:
        return str(self.paginas.get(chave, ""))


class Linha(Flowable):
    """Linha de sumário ou de lista: indicativo, título, pontilhado e página."""

    def __init__(self, indicativo: str, texto: str, pagina: str, fonte: str = T, recuo: float = 1.4 * cm):
        super().__init__()
        self.indicativo, self.texto, self.pag, self.fonte, self.recuo = indicativo, texto, pagina, fonte, recuo

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, LINHA

    def draw(self):
        c = self.canv
        c.setFont(self.fonte, 12)
        y = 5
        if self.indicativo:
            c.drawString(0, y, self.indicativo)
        x = self.recuo if self.indicativo or self.recuo else 0
        c.drawString(x, y, self.texto)
        fim_txt = x + pdfmetrics.stringWidth(self.texto, self.fonte, 12) + 4
        larg_pag = pdfmetrics.stringWidth("000", T, 12)
        c.setFont(T, 12)
        ponto = pdfmetrics.stringWidth(". ", T, 12)
        xp = fim_txt
        while xp + ponto < self.aw - larg_pag - 4:
            c.drawString(xp, y, ".")
            xp += ponto
        c.drawRightString(self.aw, y, self.pag)
        assert fim_txt < self.aw - larg_pag, f"título longo demais para o sumário/lista: {self.texto}"


# ------------------------------------------------------------------ elementos de página
class Capa(Flowable):
    def __init__(self, folha_de_rosto: bool = False):
        super().__init__()
        self.rosto = folha_de_rosto

    def wrap(self, aw, ah):
        self.aw, self.ah = aw, ah
        return aw, ah

    def _centro(self, paragrafo: Paragraph, y_topo: float) -> float:
        w, h = paragrafo.wrap(self.aw, self.ah)
        paragrafo.drawOn(self.canv, 0, y_topo - h)
        return y_topo - h

    def draw(self):
        topo = self.ah
        if not self.rosto:
            y = self._centro(P("<b>FIAP</b>", "centro_b"), topo)
            y = self._centro(P("<b>ENGENHARIA DE SOFTWARE</b>", "centro_b"), y)
            y -= 2.2 * cm
        else:
            y = topo
        autores = "<br/>".join(f"{n.upper()} (RM {rm})" for n, rm in TEAM)
        y = self._centro(Paragraph(autores, ParagraphStyle("a", parent=S["centro"], leading=LINHA)), y)
        titulo = Paragraph("<b>CALÇADA LIVRE</b>:<br/>detecção de barreiras em calçadas em tempo real com YOLO26",
                           ParagraphStyle("tit", parent=S["centro"], leading=LINHA))
        w, h = titulo.wrap(self.aw - 2 * cm, self.ah)
        y_tit = self.ah * (0.56 if not self.rosto else 0.66)
        titulo.drawOn(self.canv, 1 * cm, y_tit - h)
        if self.rosto:
            natureza = P("Relatório técnico apresentado à disciplina Applied Computer Vision do curso de Engenharia de "
                         "Software da FIAP, como parte da Global Solution 2026.2 (desafio CitizenTech).<br/><br/>"
                         f"Professores: {PROFS.replace('Prof. ', '')}.", "natureza")
            w2, h2 = natureza.wrap(self.aw / 2, self.ah)
            natureza.drawOn(self.canv, self.aw / 2, y_tit - h - 2.0 * cm - h2)
        cidade = Paragraph("SÃO PAULO<br/>2026", ParagraphStyle("cid", parent=S["centro_b"], fontName=TB))
        w3, h3 = cidade.wrap(self.aw, self.ah)
        cidade.drawOn(self.canv, 0, 0)


def titulo1(reg: Registro, numero: str, texto: str) -> list:
    chave = reg.secao("sec1", numero, texto.upper())
    p = P(f"{numero} {texto.upper()}", "t1")
    p._chave = chave
    return [PageBreak(), p]


def titulo2(reg: Registro, numero: str, texto: str) -> Paragraph:
    chave = reg.secao("sec2", numero, texto.upper())
    p = P(f"{numero} {texto.upper()}", "t2")
    p._chave = chave
    return p


def titulo_sem_numero(reg: Registro | None, texto: str, no_sumario: bool = False) -> list:
    p = P(texto.upper(), "t_centro")
    if reg is not None and no_sumario:
        p._chave = reg.secao("sec0", "", texto.upper())
    return [PageBreak(), p]


class TabelaComChave(Table):
    """Table que repassa a chave (página no sumário/listas) para a primeira parte, se for dividida."""

    def split(self, aw, ah):
        partes = super().split(aw, ah)
        if partes and getattr(self, "_chave", None):
            partes[0]._chave = self._chave
        return partes


def _bloco(cabecalho: str, miolo, rodape: list[str], largura: float, chave: str):
    linhas = [[P(cabecalho, "legenda")], [miolo]] + [[P(r, "fonte")] for r in rodape]
    t = TabelaComChave(linhas, colWidths=[largura], hAlign="CENTER")
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("ALIGN", (0, 1), (0, 1), "CENTER")]))
    t._chave = chave
    return KeepTogether([t])


def figura(reg: Registro, caminhos, largura_cm: float, titulo: str, fonte: str):
    from PIL import Image as PILImage

    n, chave = reg.novo("fig", titulo)
    imgs = []
    for c in ([caminhos] if isinstance(caminhos, Path) else caminhos):
        with PILImage.open(c) as im:
            w, h = im.size
        imgs.append([Image(str(c), width=largura_cm * cm, height=largura_cm * cm * h / w)])
    miolo = imgs[0][0] if len(imgs) == 1 else Table(imgs, colWidths=[largura_cm * cm],
                                                     style=[("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                                            ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    return [Spacer(1, 6), _bloco(f"Figura {n} – {titulo}", miolo, [f"Fonte: {fonte}"] if fonte else [], largura_cm * cm, chave),
            Spacer(1, 12)]


def tabela(reg: Registro, linhas: list[list], larguras: list[float], titulo: str, fonte: str, nota: str = ""):
    """Tabela no padrão IBGE: traço acima e abaixo do cabeçalho e no fim, laterais abertas."""
    n, chave = reg.novo("tab", titulo)
    dados = [[P(str(c), "celula_b" if r == 0 else ("celula" if j == 0 else "celula_c")) for j, c in enumerate(row)]
             for r, row in enumerate(linhas)]
    t = Table(dados, colWidths=larguras)
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, PRETO), ("LINEBELOW", (0, 0), (-1, 0), 0.6, PRETO),
                           ("LINEBELOW", (0, -1), (-1, -1), 1, PRETO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    rodape = ([f"Fonte: {fonte}"] if fonte else []) + ([f"Nota: {nota}"] if nota else [])
    return [Spacer(1, 6), _bloco(f"Tabela {n} – {titulo}", t, rodape, sum(larguras), chave), Spacer(1, 12)]


def quadro(reg: Registro, linhas: list[list], larguras: list[float], titulo: str, fonte: str):
    """Quadro (conteúdo textual): todas as bordas fechadas."""
    n, chave = reg.novo("quadro", titulo)
    dados = [[P(str(c), "celula_b" if r == 0 else "celula") for c in row] for r, row in enumerate(linhas)]
    t = Table(dados, colWidths=larguras)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, PRETO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return [Spacer(1, 6), _bloco(f"Quadro {n} – {titulo}", t, [f"Fonte: {fonte}"] if fonte else [], sum(larguras), chave),
            Spacer(1, 12)]


def formula(texto: str, n: int) -> Table:
    t = Table([["", P(texto, "formula"), P(f"({n})", "formula")]], colWidths=[2 * cm, LARGURA - 4 * cm, 2 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def fluxograma() -> Drawing:
    """Etapas da metodologia, em preto e branco."""
    etapas = ["Definição das\nclasses", "Coleta de dados\npúblicos", "Curadoria e\ndeduplicação", "Treinamento\ndo YOLO26n",
              "Avaliação no\nconjunto de teste", "Adaptação às\ncalçadas brasileiras", "Integração\nao MVP"]
    W, bw, bh, gap = LARGURA, 3.3 * cm, 1.5 * cm, 0.9 * cm
    d = Drawing(W, 4.6 * cm)

    def caixa(x, y, texto, k):
        d.add(Rect(x, y, bw, bh, strokeColor=PRETO, fillColor=colors.white, strokeWidth=0.8))
        partes = texto.split("\n")
        for i, p in enumerate(partes):
            d.add(String(x + bw / 2, y + bh / 2 + 3 - i * 12 + (len(partes) - 1) * 6, p, fontName=T, fontSize=10,
                         textAnchor="middle"))

    def seta(x0, y0, x1, y1):
        d.add(Line(x0, y0, x1, y1, strokeColor=PRETO, strokeWidth=0.8))
        if x1 > x0:
            d.add(Polygon([x1, y1, x1 - 5, y1 + 3, x1 - 5, y1 - 3], fillColor=PRETO, strokeColor=PRETO))
        else:
            d.add(Polygon([x1, y1, x1 + 3, y1 + 5, x1 - 3, y1 + 5], fillColor=PRETO, strokeColor=PRETO))

    x0 = (W - (4 * bw + 3 * gap)) / 2
    y_cima, y_baixo = 2.9 * cm, 0.3 * cm
    for i in range(4):
        x = x0 + i * (bw + gap)
        caixa(x, y_cima, etapas[i], i + 1)
        if i < 3:
            seta(x + bw, y_cima + bh / 2, x + bw + gap, y_cima + bh / 2)
    x1 = x0 + (bw + gap) / 2
    for i in range(3):
        x = x1 + i * (bw + gap)
        caixa(x, y_baixo, etapas[4 + i], 5 + i)
        if i < 2:
            seta(x + bw, y_baixo + bh / 2, x + bw + gap, y_baixo + bh / 2)
    # da etapa 4 (fim da linha de cima) para a etapa 5 (início da linha de baixo)
    xa, xb = x0 + 3 * (bw + gap) + bw / 2, x1 + bw / 2
    ym = (y_cima + y_baixo + bh) / 2
    d.add(Line(xa, y_cima, xa, ym, strokeColor=PRETO, strokeWidth=0.8))
    d.add(Line(xa, ym, xb, ym, strokeColor=PRETO, strokeWidth=0.8))
    seta(xb, ym, xb, y_baixo + bh)
    return d


# ------------------------------------------------------------------ documento
class Documento(BaseDocTemplate):
    def __init__(self, destino, **kw):
        super().__init__(destino, pagesize=A4, leftMargin=3 * cm, rightMargin=2 * cm, topMargin=3 * cm,
                         bottomMargin=2 * cm, **kw)
        frame = Frame(3 * cm, 2 * cm, LARGURA, A4[1] - 5 * cm, leftPadding=0, rightPadding=0, topPadding=0,
                      bottomPadding=0)
        self.addPageTemplates([PageTemplate("abnt", [frame], onPageEnd=self._numerar)])
        self.paginas: dict[str, int] = {}
        self.inicio_numeracao: int | None = None

    def afterFlowable(self, flowable):
        chave = getattr(flowable, "_chave", None)
        if chave:
            self.paginas[chave] = self.page - 1   # a capa não é contada (ABNT)
            if chave == "sec1-1" and self.inicio_numeracao is None:
                self.inicio_numeracao = self.page

    def _numerar(self, canv, doc):
        if self.inicio_numeracao and doc.page >= self.inicio_numeracao:
            canv.saveState()
            canv.setFont(T, 10)
            canv.drawRightString(A4[0] - 2 * cm, A4[1] - 2 * cm, str(doc.page - 1))
            canv.restoreState()


def carregar() -> dict:
    j = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    d = {"m": j(RES / "calcada_yolo26n" / "metrics.json"), "ad": j(RES / "adaptacao_br.json"),
         "ds": j(RES / "dataset_stats.json"), "tinfo": j(RES / "treino" / "yolo26n_calcada" / "train_info.json")}
    for k, nome in (("mb", "calcada_yolo26n_base"), ("m11", "calcada_yolo11n")):
        p = RES / nome / "metrics.json"
        d[k] = j(p) if p.exists() else None
    return d


def conteudo(reg: Registro, d: dict) -> tuple[list, str, str, int, int]:
    m, ad, ds, tinfo, mb, m11 = d["m"], d["ad"], d["ds"], d["tinfo"], d["mb"], d["m11"]
    g, pc, sp, cnt = m["geral"], m["por_classe"], m["velocidade"], m["contagem_conf_0.25_iou_0.5"]
    br0, br1 = ad["antes"]["teste_brasil"]["geral"], ad["depois"]["teste_brasil"]["geral"]
    or0, or1 = ad["antes"]["teste_original"]["geral"], ad["depois"]["teste_original"]["geral"]
    pcb0, pcb1 = ad["antes"]["teste_brasil"]["por_classe"], ad["depois"]["teste_brasil"]["por_classe"]
    tr, va, te = (ds["splits"][s] for s in ("train", "val", "test"))
    nome = {"buraco": "buraco", "obstaculo": "obstáculo", "piso_quebrado": "piso quebrado"}
    n_inst = {c: tr["instances"].get(c, 0) + va["instances"].get(c, 0) + te["instances"].get(c, 0) for c in pc}
    melhor, pior = max(pc, key=lambda c: pc[c]["mAP50"]), min(pc, key=lambda c: pc[c]["mAP50"])
    fundo_pct = (tr["background"] + va["background"] + te["background"]) / ds["final"]
    gpu = sp["gpu"]

    resumo = (
        "Buracos, obstáculos e pisos quebrados nas calçadas dificultam a circulação de pessoas com deficiência, idosos e "
        "pessoas com carrinhos de bebê, e as prefeituras não dispõem de um levantamento atualizado dessas barreiras. Este "
        "relatório descreve o componente de visão computacional do Calçada Livre, um mapa colaborativo de barreiras em "
        "calçadas desenvolvido na Global Solution 2026.2. Foi treinado um detector de objetos de tempo real, baseado na "
        "arquitetura YOLO26n pré-treinada no conjunto COCO, para reconhecer três classes: buraco, obstáculo e piso "
        f"quebrado. O conjunto de dados, com {milhar(ds['final'])} imagens, foi montado a partir de três bases públicas "
        "com visão de pedestre, cujas classes foram remapeadas, filtradas e deduplicadas por hash perceptual antes da "
        "divisão em treino, validação e teste. Testes com vídeos de calçadas de São Paulo mostraram que o modelo quase "
        "não reconhecia o piso quebrado das calçadas brasileiras. Por isso, quadros desses vídeos foram anotados e "
        "usados em uma etapa de adaptação de domínio, avaliada em trechos que não participaram do treinamento. O modelo "
        f"final obteve mAP50 de {pct(g['mAP50'])} no teste original e de {pct(br1['mAP50'])} no teste brasileiro, "
        f"contra {pct(br0['mAP50'])} antes da adaptação, com precisão de {pct(g['precisao'])} e revocação de "
        f"{pct(g['revocacao'])}, e processou cerca de {sp['fps_gpu_batch1']:.0f} quadros por segundo em GPU e "
        f"{sp['fps_cpu_batch1']:.0f} em CPU. O detector foi integrado a uma API e a uma página web que recebem fotos e "
        "vídeos, borram rostos, removem metadados e registram cada barreira como ocorrência georreferenciada, com "
        "validação humana nos casos de baixa confiança."
    )
    abstract = (
        "Potholes, obstacles and broken pavement on sidewalks hinder the mobility of people with disabilities, older "
        "adults and parents with strollers, and city governments lack an up-to-date survey of these barriers. This "
        "report describes the computer vision component of Calçada Livre, a collaborative map of sidewalk barriers "
        "developed for the FIAP Global Solution 2026.2. A real-time object detector based on YOLO26n, pre-trained on "
        "COCO, was fine-tuned to recognize three classes: pothole, obstacle and broken pavement. The dataset, with "
        f"{ds['final']:,} images, was built from three public pedestrian-view datasets whose classes were remapped, "
        "filtered and deduplicated with perceptual hashing before the train, validation and test split. Tests on "
        "sidewalk videos from São Paulo showed that the model barely recognized the broken pavement typical of "
        "Brazilian sidewalks, so frames from these videos were annotated and used for domain adaptation, evaluated on "
        "segments never used in training. The final model reached an mAP50 of "
        f"{g['mAP50'] * 100:.1f}% on the original test set and {br1['mAP50'] * 100:.1f}% on the Brazilian test set "
        f"(versus {br0['mAP50'] * 100:.1f}% before adaptation), running at about {sp['fps_gpu_batch1']:.0f} frames "
        f"per second on GPU and {sp['fps_cpu_batch1']:.0f} on CPU. The detector was integrated into an API and a web "
        "page that receive photos and videos, blur faces, remove metadata and register each barrier as a geolocated "
        "report, with human review for low-confidence detections."
    )
    objetivo = (
        "Treinar e avaliar um detector de objetos YOLO capaz de identificar, em tempo real, buracos, obstáculos e pisos "
        "quebrados em fotos e vídeos de calçadas, e integrá-lo ao MVP Calçada Livre para que cada barreira detectada se "
        "torne uma ocorrência georreferenciada no mapa colaborativo."
    )
    nr, no = palavras(resumo), palavras(objetivo)
    if nr > 250 or no > 50:
        sys.exit(f"Limite de palavras excedido: resumo={nr}/250, objetivo={no}/50")

    h = []
    # ================================================================ 1 INTRODUÇÃO
    h += titulo1(reg, "1", "Introdução")
    h += [P("A calçada é o espaço da cidade destinado à circulação de pedestres e, para muitas pessoas, é o principal "
            "meio de deslocamento. A NBR 9050 estabelece que a faixa livre, reservada à circulação, deve ter largura "
            "mínima admissível de 1,20 m e piso com superfície regular, firme, estável e antiderrapante (ABNT, 2020). "
            "Na prática, buracos, objetos deixados no caminho e placas de piso soltas são comuns e afetam sobretudo quem "
            "tem mobilidade reduzida. Segundo o IBGE (2023), o Brasil tinha 18,6 milhões de pessoas com deficiência em "
            "2022, o equivalente a 8,9% da população com dois anos ou mais."),
          P("Em São Paulo, a conservação da calçada cabe ao proprietário do imóvel, e a fiscalização, à prefeitura, que "
            "depende principalmente de reclamações registradas pelos moradores no canal SP156. Esse modelo produz "
            "informação dispersa e sem padronização, o que dificulta saber onde estão as barreiras e quais devem ser "
            "corrigidas primeiro. A Lei Brasileira de Inclusão assegura à pessoa com deficiência o direito à "
            "acessibilidade e à mobilidade (BRASIL, 2015), mas o poder público raramente dispõe de um levantamento "
            "atualizado das calçadas."),
          P("O Calçada Livre, desenvolvido pela equipe na Global Solution 2026.2 (desafio CitizenTech), é um mapa "
            "colaborativo dessas barreiras. O cidadão envia uma foto ou um vídeo da calçada, a ocorrência é registrada "
            "no mapa e segue para triagem automática e encaminhamento à subprefeitura responsável. O produto inclui "
            "também um carrinho inspetor, um assistente baseado em modelo de linguagem e um pipeline de dados. Este "
            "relatório trata do componente de visão computacional, que reconhece a barreira na imagem e preenche o tipo "
            "da ocorrência sem intervenção manual, tarefa que, feita por pessoas, não acompanharia o volume de envios."),
          P("Do ponto de vista técnico, trata-se de um problema de detecção de objetos: o modelo precisa indicar se há uma "
            "barreira, onde ela está, por meio de uma caixa delimitadora, e a qual classe pertence, com velocidade "
            "suficiente para processar vídeo. Como não há modelo público treinado para as três classes de interesse, foi "
            "realizado um treinamento customizado de uma arquitetura YOLO sobre um conjunto de dados montado e revisado "
            "pela equipe.")]

    # ================================================================ 2 OBJETIVO
    h += titulo1(reg, "2", "Objetivo")
    h += [P(objetivo)]

    # ================================================================ 3 FERRAMENTAS
    h += titulo1(reg, "3", "Explicação técnica das ferramentas")
    h += [titulo2(reg, "3.1", "Detector YOLO26"),
          P("O YOLO (<i>You Only Look Once</i>) é uma família de detectores de estágio único: uma rede neural convolucional "
            "analisa a imagem inteira em uma só passagem e prevê, ao mesmo tempo, as caixas delimitadoras, as classes e as "
            "confianças (REDMON <i>et al.</i>, 2016). Por dispensar uma etapa separada de geração de regiões candidatas, "
            "essa abordagem alcança velocidade compatível com o processamento de vídeo. A rede tem três partes: o "
            "<i>backbone</i>, que extrai características visuais; o <i>neck</i>, que combina mapas de características em "
            "diferentes escalas, o que permite detectar tanto um bueiro próximo quanto uma lixeira distante; e o "
            "<i>head</i>, que produz as previsões."),
          P(f"Foi utilizada a versão nano do YOLO26 (YOLO26n), com cerca de {num(m['parametros'] / 1e6, 1)} milhões de "
            f"parâmetros e {num(m['tamanho_mb'], 1)} MB. Em relação às gerações anteriores, o YOLO26 dispensa a supressão "
            "de não máximos (NMS) na inferência, pois a rede já entrega uma única caixa por objeto, e elimina o módulo DFL "
            "(<i>Distribution Focal Loss</i>), o que simplifica a exportação para dispositivos móveis e reduz a latência em "
            "CPU (ULTRALYTICS, 2026). Para comparação, o YOLO11n (JOCHER; QIU, 2024), da geração anterior, foi treinado "
            "com a mesma configuração."),
          titulo2(reg, "3.2", "Aprendizado por transferência"),
          P("O aprendizado por transferência reaproveita o conhecimento de um modelo treinado em uma tarefa ampla para "
            "resolver uma tarefa mais específica com menos dados (PAN; YANG, 2010). O treinamento partiu de pesos "
            "pré-treinados no conjunto COCO, que tem 80 classes e cerca de 118 mil imagens de treino (LIN <i>et al.</i>, "
            "2014). As primeiras camadas da rede já reconhecem bordas, texturas e formas. Durante o ajuste fino, todas as "
            "camadas foram atualizadas, e a camada de saída foi recriada para as três classes do projeto."),
          titulo2(reg, "3.3", "Rastreamento de objetos em vídeo"),
          P("Em vídeo, a mesma barreira aparece em dezenas de quadros seguidos. Para não a registrar várias vezes, foi "
            "usado o ByteTrack, algoritmo de rastreamento multiobjeto que associa as detecções de quadros consecutivos e "
            "atribui a cada objeto um identificador estável, aproveitando também as detecções de baixa confiança para "
            "manter a continuidade da trajetória (ZHANG <i>et al.</i>, 2022). No sistema, uma barreira só gera ocorrência "
            "depois de rastreada por quatro quadros com confiança mínima de 0,5."),
          titulo2(reg, "3.4", "Proteção de dados nas imagens"),
          P("Fotos de rua podem conter rostos e placas de veículos. Antes de qualquer gravação, essas regiões são "
            "localizadas com classificadores em cascata de Haar (VIOLA; JONES, 2001), disponíveis na biblioteca OpenCV, e "
            "borradas: rostos nas fotos e nos vídeos, e placas também nos vídeos. A imagem é recodificada a partir dos "
            "pixels, o que elimina os metadados EXIF, entre eles a posição GPS e o modelo do aparelho, e o vídeo enviado "
            "é apagado ao fim da análise. Essas medidas seguem o princípio da necessidade previsto na Lei Geral de "
            "Proteção de Dados Pessoais (BRASIL, 2018)."),
          titulo2(reg, "3.5", "Bibliotecas e serviços"),
          P("O Quadro 2 resume as demais bibliotecas e serviços utilizados no trabalho.")]
    h += quadro(reg, [
        ["Ferramenta", "Função no projeto"],
        ["Python 3.12 e PyTorch 2", f"Linguagem e biblioteca de aprendizado profundo, com aceleração em GPU ({gpu})."],
        ["Ultralytics 8.4", "Treinamento, validação, aumento de dados e rastreamento dos modelos YOLO."],
        ["OpenCV 4", "Leitura de vídeo, desenho das caixas e anonimização de rostos e placas."],
        ["ImageHash", "Cálculo do hash perceptual (pHash) para localizar imagens repetidas (ZAUNER, 2010)."],
        ["FastAPI e SQLite", "API que recebe fotos e vídeos e banco de dados das ocorrências."],
        ["Leaflet e OpenStreetMap", "Mapa interativo da página web."],
        ["Hugging Face e Wikimedia Commons", "Fontes públicas dos conjuntos de dados e dos vídeos de São Paulo."],
        ["pytest", "Testes automatizados da API."],
    ], [5.0 * cm, 11.0 * cm], "Bibliotecas e serviços utilizados", "")
    h += [titulo2(reg, "3.6", "Métricas de avaliação"),
          P("Uma detecção é considerada correta, ou verdadeiro positivo (VP), quando a classe coincide com a anotada e a "
            "sobreposição entre as caixas, medida pela razão entre a área da interseção e a área da união (IoU), é de pelo "
            "menos 0,5. Detecções sem correspondência são falsos positivos (FP), e barreiras anotadas que não foram "
            "encontradas são falsos negativos (FN). A partir dessas contagens, calculam-se a precisão e a revocação:"),
          formula("Precisão = VP / (VP + FP)", 1), formula("Revocação = VP / (VP + FN)", 2),
          P("A precisão média (AP) de uma classe é a área sob a curva precisão-revocação, e o mAP50 é a média das AP das "
            "classes com limiar de IoU de 0,5 (EVERINGHAM <i>et al.</i>, 2010). O mAP50-95 repete o cálculo para limiares "
            "de 0,5 a 0,95 e, por isso, também avalia o ajuste das caixas. A velocidade foi medida em quadros por segundo "
            "(FPS), somando pré-processamento, inferência e pós-processamento de uma imagem por vez, como no uso real.")]

    # ================================================================ 4 METODOLOGIA
    h += titulo1(reg, "4", "Metodologia")
    h += [P("O trabalho seguiu as etapas da Figura 1. Cada etapa corresponde a um script numerado no repositório, "
            "executado com semente aleatória fixa (42), o que permite reproduzir os resultados.")]
    n_fig, chave = reg.novo("fig", "Etapas da metodologia")
    h += [Spacer(1, 6), _bloco(f"Figura {n_fig} – Etapas da metodologia", fluxograma(),
                               [], LARGURA, chave), Spacer(1, 12)]
    h += [titulo2(reg, "4.1", "Definição das classes"),
          P("As classes foram definidas a partir do problema, considerando barreiras que afetam quem anda a pé e que "
            "exigem ações diferentes da zeladoria: buraco, que inclui buracos e bueiros abertos; obstáculo, para objetos "
            "que bloqueiam a faixa livre, como lixeiras, postes, cones, cavaletes, bancos, mesas e cadeiras; e piso "
            "quebrado, para pisos rachados, soltos ou desnivelados."),
          titulo2(reg, "4.2", "Coleta dos dados"),
          P("Foram reunidos três conjuntos públicos com licença MIT e imagens tomadas do ponto de vista do pedestre: o "
            "Unified Obstacles Dataset, do projeto AssistEye (DDEREDOR, 2026); o ROD-Dataset, com fotos de calçadas feitas "
            "com celular (ZANDI, 2026); e um conjunto de imagens de buracos (RUPESH002, 2025). Do ROD-Dataset, foram "
            "baixadas apenas as imagens com classes úteis, a partir do manifesto oficial. Outras fontes foram avaliadas "
            "visualmente e descartadas por apresentarem anotações de baixa qualidade, como mosaicos, imagens invertidas e "
            "rachaduras rotuladas como buracos."),
          titulo2(reg, "4.3", "Curadoria e mapeamento das classes"),
          P("Cada classe de origem foi associada a uma das três classes do projeto após a inspeção de amostras. Classes "
            "ambíguas foram descartadas, como <i>bump</i>, que mistura meio-fio e desnível, e <i>fence</i>, que "
            "corresponde a grades na borda da calçada e não bloqueia a passagem. Polígonos foram convertidos em caixas, "
            f"caixas degeneradas foram removidas, e {milhar(ds['descartadas_na_leitura'].get('so_classes_descartadas', 0))} "
            "imagens que só continham classes descartadas foram excluídas, assim como "
            f"{ds['descartadas_na_leitura'].get('rotulo_corrompido', 0)} arquivo de rótulo corrompido e "
            f"{ds['descartadas_na_leitura'].get('caixa_gigante', 0)} imagens em que a caixa cobria mais de 70% da foto, "
            "situação típica de fotos feitas muito de perto, diferentes do uso real."),
          titulo2(reg, "4.4", "Deduplicação e divisão do conjunto"),
          P(f"Foi calculado o hash perceptual das {milhar(ds['candidatas'])} imagens candidatas. As "
            f"{milhar(ds['duplicatas_exatas_removidas'])} duplicatas exatas foram removidas, pois um dos conjuntos usava "
            "cópias para equilibrar as classes, e as imagens quase idênticas (distância de Hamming de até 6) foram "
            "agrupadas para permanecer sempre na mesma divisão. A separação em 80% para treino, 10% para validação e 10% "
            "para teste foi feita por grupo e estratificada pela classe mais rara. Sem esse cuidado, cópias de uma mesma "
            "foto apareceriam no treino e no teste, e as métricas ficariam artificialmente altas. A Tabela 1 apresenta o "
            "conjunto final, e a Figura 2 mostra exemplos de imagens anotadas.")]
    h += tabela(reg, [
        ["Divisão", "Imagens", "Sem barreira", "Buraco", "Obstáculo", "Piso quebrado"],
        ["Treino", milhar(tr["images"]), tr["background"], milhar(tr["instances"].get("buraco", 0)),
         milhar(tr["instances"].get("obstaculo", 0)), tr["instances"].get("piso_quebrado", 0)],
        ["Validação", va["images"], va["background"], va["instances"].get("buraco", 0), va["instances"].get("obstaculo", 0),
         va["instances"].get("piso_quebrado", 0)],
        ["Teste", te["images"], te["background"], te["instances"].get("buraco", 0), te["instances"].get("obstaculo", 0),
         te["instances"].get("piso_quebrado", 0)],
        ["Total", milhar(ds["final"]), tr["background"] + va["background"] + te["background"],
         milhar(n_inst["buraco"]), milhar(n_inst["obstaculo"]), n_inst["piso_quebrado"]],
    ], [2.6 * cm, 2.4 * cm, 2.6 * cm, 2.4 * cm, 2.6 * cm, 2.9 * cm], "Composição do conjunto de dados final",
        "",
        f"as colunas das classes indicam instâncias (caixas anotadas); o treino recebeu ainda "
        f"{milhar(tr['oversampled_copies'])} cópias por sobreamostragem (seção 4.5).")
    h += figura(reg, FIG / "dataset_amostras.jpg", 15.5, "Amostras do conjunto de dados com as anotações",
                "Dderedor (2026), Zandi (2026) e Rupesh002 (2025).")
    h += [titulo2(reg, "4.5", "Balanceamento"),
          P(f"Piso quebrado é a classe com menos exemplos ({n_inst['piso_quebrado']} instâncias). Para compensar, as "
            "imagens de treino que contêm essa classe foram triplicadas, e os aumentos de dados aplicados a cada época "
            "tornam as cópias diferentes entre si. Os conjuntos de validação e de teste não foram alterados. Cerca de "
            f"{fundo_pct * 100:.0f}% das imagens não contêm barreiras e foram mantidas para reduzir os falsos positivos."),
          titulo2(reg, "4.6", "Treinamento"),
          P("O ajuste fino do YOLO26n usou imagens de 640 pixels, lotes de 32 imagens e o otimizador AdamW, com taxa de "
            f"aprendizado inicial de 0,002 e decaimento cosseno, por até {tinfo['epocas_max']} épocas, com parada "
            "antecipada após 25 épocas sem melhora na validação. Os aumentos de dados foram escolhidos para fotos de "
            "calçada feitas com celular: variação de brilho e saturação, para simular sol e sombra, pequenas rotações, "
            "mudança de escala, espelhamento horizontal, mosaico e mistura de imagens (<i>mixup</i>). O espelhamento "
            "vertical não foi usado, porque uma calçada não aparece de cabeça para baixo, e o mosaico foi desligado nas "
            f"dez últimas épocas. O treinamento levou {num(tinfo['tempo_treino_min'], 0)} minutos em uma {gpu}. O YOLO11n "
            "foi treinado com a mesma configuração."),
          titulo2(reg, "4.7", "Avaliação"),
          P("Os modelos foram avaliados no conjunto de teste, que não participou do treinamento nem da escolha de "
            "parâmetros. Além das métricas da seção 3.6, foram geradas a matriz de confusão e as curvas "
            "precisão-revocação, foi medida a velocidade em GPU e em CPU e foram selecionados exemplos de acertos e de "
            "erros, exibidos ao lado da anotação correspondente."),
          titulo2(reg, "4.8", "Adaptação às calçadas brasileiras"),
          P("Para verificar o comportamento do modelo fora dos dados originais, ele foi aplicado a oito vídeos de calçadas "
            "do bairro da Bela Vista, em São Paulo, publicados no Wikimedia Commons sob licença CC BY 3.0 (FRAGA, 2010a, "
            "2010b, 2010c, 2010d, 2010e, 2010f, 2010g; VIDEOJOURNALISMS, 2013). Um nono vídeo, gravado à noite, foi "
            "descartado. As gravações foram feitas com outra câmera, em outra cidade e em outra época. O modelo "
            "reconheceu caçambas e postes, mas praticamente não detectou o piso quebrado típico das calçadas brasileiras, "
            "como concreto rachado, pedra portuguesa solta e ladrilhos faltando."),
          P("Para reduzir essa diferença de domínio, foram extraídos dois quadros por segundo de cada vídeo, com divisão "
            "temporal: os primeiros 65% de cada vídeo foram usados na adaptação, os 10% seguintes foram descartados como "
            "intervalo de segurança e os 25% finais formaram o teste brasileiro, que não entrou no treinamento. A equipe "
            f"anotou {ad['quadros_adaptacao']} quadros de adaptação e os {ad['quadros_teste_brasil']} quadros de teste de "
            "forma assistida: o modelo sugeria as caixas, e a pessoa responsável as conferia, corrigia e completava. Em "
            f"seguida, foi feito um ajuste fino curto ({ad['epocas']} épocas, taxa de aprendizado de 0,0005) a partir do "
            "modelo da seção 4.6, combinando o treino original com os quadros brasileiros replicados "
            f"{ad['oversampling']} vezes. O critério de aceitação, definido antes do experimento, foi melhorar no teste "
            "brasileiro sem perder mais de 2 pontos percentuais de mAP50 no teste original."),
          titulo2(reg, "4.9", "Integração ao MVP"),
          P("O detector foi disponibilizado por meio de uma API desenvolvida com FastAPI. Quando o cidadão envia uma foto, "
            "a imagem é recodificada, os rostos são borrados e o detector identifica as barreiras. A ocorrência é criada "
            "com protocolo, tipo, confiança, prioridade sugerida e situação. Detecções com confiança inferior a 0,6 ficam "
            "pendentes de validação, e uma pessoa da zeladoria as confirma ou corrige. Quando o envio é um vídeo, o "
            "arquivo é analisado quadro a quadro com rastreamento, a página exibe a análise em tempo real e cada barreira "
            "confirmada se torna uma ocorrência. A localização pode ser informada por endereço, por clique no mapa ou "
            "pelo GPS do celular."),
          P("Cada ocorrência é replicada na API central do MVP do grupo, com a origem identificada como visão, de acordo "
            "com as regras da triagem automática: coordenada dentro do município de São Paulo, endereço da foto e "
            "confiança mínima de 0,5. Quinze testes automatizados verificam esses fluxos, incluindo a remoção dos "
            "metadados, a validação humana, a análise de vídeo e o formato enviado ao MVP.")]

    # ================================================================ 5 RESULTADOS
    h += titulo1(reg, "5", "Exemplos de resultados")
    h += [titulo2(reg, "5.1", "Desempenho no conjunto de teste"),
          P(f"A Tabela 2 apresenta as métricas do modelo final no conjunto de teste, com {m['imagens_teste']} imagens.")]
    linhas = [["Classe", "Precisão", "Revocação", "mAP50", "mAP50-95", "Instâncias"]]
    for c in ("buraco", "obstaculo", "piso_quebrado"):
        linhas.append([nome[c].capitalize(), num(pc[c]["precisao"]), num(pc[c]["revocacao"]), num(pc[c]["mAP50"]),
                       num(pc[c]["mAP50_95"]), te["instances"].get(c, 0)])
    linhas.append(["Todas", num(g["precisao"]), num(g["revocacao"]), num(g["mAP50"]), num(g["mAP50_95"]),
                   sum(te["instances"].values())])
    h += tabela(reg, linhas, [3.4 * cm, 2.4 * cm, 2.4 * cm, 2.2 * cm, 2.4 * cm, 2.6 * cm],
                "Desempenho do modelo final no conjunto de teste", "")
    conf_txt = (f"e {cnt['confusoes_de_classe']} detecções localizaram a barreira com a classe errada"
                if cnt["confusoes_de_classe"] else "e não houve confusão entre classes")
    h += [P(f"O modelo atingiu mAP50 de {pct(g['mAP50'])}. O melhor desempenho foi o da classe {nome[melhor]} (mAP50 de "
            f"{pct(pc[melhor]['mAP50'])}), e o mais baixo, o da classe {nome[pior]} ({pct(pc[pior]['mAP50'])}). Com limiar "
            f"de confiança de 0,25, houve {cnt['verdadeiros_positivos']} acertos, {cnt['falsos_positivos']} falsos "
            f"positivos e {cnt['falsos_negativos']} barreiras não detectadas, {conf_txt}."),
          P("A Figura 3 mostra que as perdas de treino e de validação diminuem de forma estável e que as métricas de "
            "validação se estabilizam nas últimas épocas, sem indício de sobreajuste acentuado. A queda das perdas de "
            "treino perto da época 90 coincide com o desligamento do mosaico, quando as imagens passam a ser vistas "
            "inteiras.")]
    h += figura(reg, FIG / "treino_curvas.png", 16, "Perdas e métricas de validação ao longo do treinamento",
                "")
    h += [P("Na matriz de confusão (Figura 4), cada coluna corresponde à classe real e soma 1. Os erros acontecem entre "
            "as barreiras e o fundo, e não entre as classes: cerca de 10% dos buracos e 11% dos pisos quebrados não foram "
            "detectados, enquanto quase todos os obstáculos foram encontrados. A coluna do fundo mostra que os falsos "
            "positivos se concentram nas classes buraco e obstáculo. A Figura 5 apresenta as curvas precisão-revocação "
            "de cada classe.")]
    h += figura(reg, FIG / "matriz_confusao.png", 10.5, "Matriz de confusão normalizada no conjunto de teste",
                "")
    h += figura(reg, FIG / "curva_pr.png", 10.5, "Curvas precisão-revocação no conjunto de teste",
                "")

    h += [titulo2(reg, "5.2", "Tempo real e comparação de arquiteturas"),
          P("A Tabela 3 compara o YOLO26n e o YOLO11n treinados com a mesma receita e o YOLO26n final, após a adaptação. "
            "A velocidade considera uma imagem por vez.")]
    comp = [["Modelo", "Precisão", "Revocação", "mAP50", "mAP50-95", "FPS (GPU)", "FPS (CPU)", "Tamanho"]]
    rot = {"calcada_yolo26n_base": "YOLO26n", "calcada_yolo11n": "YOLO11n", "calcada_yolo26n": "YOLO26n adaptado"}
    for mm in [x for x in (mb, m11, m) if x]:
        gg, vv = mm["geral"], mm["velocidade"]
        comp.append([rot.get(mm["modelo"], mm["modelo"]), num(gg["precisao"]), num(gg["revocacao"]), num(gg["mAP50"]),
                     num(gg["mAP50_95"]), f"{vv['fps_gpu_batch1']:.0f}", f"{vv['fps_cpu_batch1']:.0f}",
                     f"{num(mm['tamanho_mb'], 1)} MB"])
    h += tabela(reg, comp, [2.8 * cm, 1.8 * cm, 2.3 * cm, 1.6 * cm, 2.2 * cm, 1.7 * cm, 1.7 * cm, 1.9 * cm],
                "Comparação entre arquiteturas no conjunto de teste", "",
                f"FPS medidos somando pré-processamento, inferência e pós-processamento, em uma {gpu} e na CPU.")
    if mb and m11:
        g11, gb = m11["geral"], mb["geral"]
        dif, dif95 = (gb["mAP50"] - g11["mAP50"]) * 100, (gb["mAP50_95"] - g11["mAP50_95"]) * 100
        h += [P(f"Com a mesma receita, o {'YOLO26n' if dif >= 0 else 'YOLO11n'} ficou {num(abs(dif), 1)} ponto percentual "
                f"acima em mAP50 e {num(abs(dif95), 1)} em mAP50-95, além de apresentar precisão maior ({num(gb['precisao'])} "
                f"contra {num(g11['precisao'])}). O YOLO26n foi escolhido para o MVP também por dispensar o NMS e ter "
                "exportação mais simples para celulares. Mesmo apenas em CPU, o modelo final processa cerca de "
                f"{sp['fps_cpu_batch1']:.0f} quadros por segundo, velocidade suficiente para o uso em tempo real.")]

    ex = RES / "calcada_yolo26n" / "exemplos"
    h += [titulo2(reg, "5.3", "Exemplos de acertos e de erros"),
          P("Nas Figuras 6 a 8, a imagem da esquerda mostra a anotação de referência, e a da direita, a predição do modelo "
            "com a confiança. A Figura 6 reúne acertos das três classes: um bueiro aberto, lixeiras e um trecho de piso "
            "quebrado.")]
    acertos = [p for p in (ex / "acerto_2.jpg", ex / "acerto_3.jpg", ex / "acerto_5.jpg") if p.exists()]
    h += figura(reg, acertos, 12.5, "Acertos do modelo no conjunto de teste", "")
    h += [P("A Figura 7 mostra um falso negativo: um poste distante, com poucos pixels, não foi detectado. A Figura 8 "
            "mostra um falso positivo, em que o modelo dividiu um único buraco em duas caixas de baixa confiança, nenhuma "
            "com sobreposição suficiente com a anotação.")]
    h += figura(reg, ex / "erro_fn_1.jpg", 12.5, "Falso negativo no conjunto de teste", "")
    h += figura(reg, ex / "erro_fp_1.jpg", 12.5, "Falso positivo no conjunto de teste", "")

    h += [titulo2(reg, "5.4", "Adaptação às calçadas brasileiras"),
          P("A Tabela 4 compara o modelo antes e depois da adaptação nos dois conjuntos de teste, e a Tabela 5 detalha o "
            "teste brasileiro por classe.")]
    h += tabela(reg, [
        ["Conjunto de teste", "Modelo", "Precisão", "Revocação", "mAP50", "mAP50-95"],
        ["Brasil (São Paulo)", "Antes", num(br0["precisao"]), num(br0["revocacao"]), num(br0["mAP50"]), num(br0["mAP50_95"])],
        ["Brasil (São Paulo)", "Depois", num(br1["precisao"]), num(br1["revocacao"]), num(br1["mAP50"]), num(br1["mAP50_95"])],
        ["Original", "Antes", num(or0["precisao"]), num(or0["revocacao"]), num(or0["mAP50"]), num(or0["mAP50_95"])],
        ["Original", "Depois", num(or1["precisao"]), num(or1["revocacao"]), num(or1["mAP50"]), num(or1["mAP50_95"])],
    ], [3.9 * cm, 1.9 * cm, 2.1 * cm, 2.4 * cm, 1.9 * cm, 2.3 * cm], "Efeito da adaptação de domínio",
        "",
        f"teste brasileiro com {ad['quadros_teste_brasil']} quadros do trecho final de cada vídeo, separados no tempo "
        "dos quadros de adaptação.")
    por_classe = [["Classe", "mAP50 antes", "mAP50 depois"]]
    for c in ("buraco", "obstaculo", "piso_quebrado"):
        if c in pcb0 or c in pcb1:
            por_classe.append([nome[c].capitalize(), num(pcb0.get(c, {}).get("mAP50", 0.0)),
                               num(pcb1.get(c, {}).get("mAP50", 0.0))])
    h += tabela(reg, por_classe, [5.0 * cm, 3.5 * cm, 3.5 * cm], "mAP50 por classe no teste brasileiro",
                "")
    ganho, queda = (br1["mAP50"] - br0["mAP50"]) * 100, (or0["mAP50"] - or1["mAP50"]) * 100
    h += [P(f"Antes da adaptação, o modelo treinado apenas com dados estrangeiros tinha mAP50 de {pct(br0['mAP50'])} nas "
            f"calçadas brasileiras, bem abaixo dos {pct(or0['mAP50'])} do teste original, o que caracteriza uma diferença "
            f"de domínio. Com {ad['quadros_adaptacao']} quadros anotados, o mAP50 brasileiro passou para "
            f"{pct(br1['mAP50'])}, um ganho de {num(ganho, 1)} pontos percentuais, enquanto o teste original "
            f"{'caiu' if queda > 0 else 'subiu'} apenas {num(abs(queda), 1)} ponto (de {pct(or0['mAP50'])} para "
            f"{pct(or1['mAP50'])}). O modelo, portanto, se adaptou sem "
            "perder o que já havia aprendido, e o critério de aceitação foi cumprido."),
          P(f"O ganho não foi igual entre as classes. Obstáculo passou de {pct(pcb0['obstaculo']['mAP50'])} para "
            f"{pct(pcb1['obstaculo']['mAP50'])}, e o modelo deixou de apontar muros e fachadas como barreiras. Piso "
            f"quebrado subiu de {pct(pcb0['piso_quebrado']['mAP50'])} para {pct(pcb1['piso_quebrado']['mAP50'])}: o modelo "
            "passou a reconhecer pedras soltas e ladrilhos faltando, mas ainda erra grandes áreas de concreto rachado. "
            "Parte dessa dificuldade vem da própria anotação, pois é difícil definir onde começa e termina uma área "
            "rachada, e uma caixa plausível com sobreposição menor que 50% conta como erro no mAP50. Como o teste "
            "brasileiro é pequeno, esses números têm variância maior e devem ser lidos como tendência. A Figura 9 mostra "
            "quadros do teste brasileiro antes e depois da adaptação.")]
    h += figura(reg, FIG / "adaptacao_antes_depois.jpg", 11.0, "Teste brasileiro antes e depois da adaptação",
                "Fraga (2010c, 2010e, 2010f, 2010g) e Videojournalisms (2013).")

    h += [titulo2(reg, "5.5", "Aplicação no MVP"),
          P("A Figura 10 mostra a página web do Calçada Livre. O cidadão escolhe uma foto ou um vídeo, informa a "
            "localização e envia; a ocorrência aparece no mapa e na tabela, onde a zeladoria pode confirmá-la ou "
            "rejeitá-la. A tabela reproduz as informações do mapa para quem usa leitor de tela.")]
    if (FIG / "mvp_tela.png").exists():
        h += figura(reg, FIG / "mvp_tela.png", 14.5, "Página web com o formulário e o mapa de ocorrências",
                    "mapa de © colaboradores do OpenStreetMap.")
    h += [P("A Figura 11 mostra a análise de vídeo em tempo real. A página exibe cada quadro com as caixas, o "
            "identificador de rastreamento e a contagem por classe, e a lista ao lado recebe as ocorrências à medida que "
            "as barreiras são confirmadas. No vídeo de 29 segundos da rua Cardeal Leme, a análise acompanhou o ritmo do "
            "vídeo original, com capacidade de cerca de 50 quadros por segundo, e registrou dez barreiras. Em teste com a "
            "API do MVP do grupo executada localmente, as 13 ocorrências geradas por três fotos e esse vídeo foram "
            "recebidas e aprovadas pela regra de validação da triagem automática.")]
    if (FIG / "mvp_video_ao_vivo.png").exists():
        h += figura(reg, FIG / "mvp_video_ao_vivo.png", 14.5, "Análise de vídeo em tempo real na página web",
                    "Fraga (2010c).")


    # ================================================================ 6 CONCLUSÃO
    h += titulo1(reg, "6", "Conclusão")
    h += [P("O objetivo do trabalho foi atingido. Foi construído um conjunto de dados próprio, com curadoria, remoção de "
            "duplicatas e divisão sem vazamento, e o YOLO26n foi treinado por aprendizado por transferência para detectar "
            f"buracos, obstáculos e pisos quebrados. No conjunto de teste, o modelo alcançou mAP50 de {pct(g['mAP50'])}, "
            f"precisão de {pct(g['precisao'])} e revocação de {pct(g['revocacao'])}, com desempenho superior ao do YOLO11n "
            "treinado nas mesmas condições."),
          P("O teste com vídeos reais de São Paulo revelou uma diferença de domínio que as métricas do conjunto original "
            f"não mostravam. A adaptação com poucos quadros anotados elevou o mAP50 brasileiro de {pct(br0['mAP50'])} para "
            f"{pct(br1['mAP50'])} sem prejudicar o desempenho original, embora o piso quebrado brasileiro continue sendo "
            f"o ponto mais fraco do modelo. O detector funciona em tempo real, com cerca de {sp['fps_gpu_batch1']:.0f} "
            f"quadros por segundo em GPU e {sp['fps_cpu_batch1']:.0f} em CPU, e já está integrado ao MVP: fotos e vídeos "
            "enviados pelo cidadão se tornam ocorrências georreferenciadas, com proteção de dados pessoais e validação "
            "humana nos casos de dúvida."),
          P("Como próximos passos, a equipe pretende ampliar a base brasileira com fotos de outras cidades, sobretudo de "
            "piso quebrado, e retreinar o modelo com os casos corrigidos pela zeladoria; exportar o modelo para formatos "
            "móveis, como ONNX e TFLite, para que a detecção ocorra no próprio celular, inclusive sem internet; e estimar "
            "a gravidade da barreira, considerando seu tamanho e sua posição na faixa livre, para refinar a prioridade "
            "enviada à triagem.")]

    # ================================================================ REFERÊNCIAS
    h += titulo_sem_numero(reg, "Referências", no_sumario=True)
    def wmurl(arquivo: str) -> str:
        return link("https://commons.wikimedia.org/wiki/File:" + arquivo.replace(" ", "_").replace('"', "%22"))

    refs = [
        "ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. <b>NBR 9050</b>: acessibilidade a edificações, mobiliário, espaços e "
        "equipamentos urbanos. 4. ed. Rio de Janeiro: ABNT, 2020.",
        "BRASIL. Lei nº 13.146, de 6 de julho de 2015. Institui a Lei Brasileira de Inclusão da Pessoa com Deficiência "
        "(Estatuto da Pessoa com Deficiência). <b>Diário Oficial da União</b>: seção 1, Brasília, DF, 7 jul. 2015.",
        "BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de Dados Pessoais (LGPD). <b>Diário "
        "Oficial da União</b>: seção 1, Brasília, DF, 15 ago. 2018.",
        "DDEREDOR. <b>Obstacles on the road</b>: unified obstacles dataset (AssistEye). [<i>S. l.</i>]: Hugging Face, "
        f"2026. Conjunto de dados. Disponível em: {link('https://huggingface.co/datasets/Dderedor/obstacles_on_the_road')}. "
        f"Acesso em: {ACESSO}.",
        "EVERINGHAM, M. <i>et al.</i> The Pascal Visual Object Classes (VOC) challenge. <b>International Journal of "
        "Computer Vision</b>, v. 88, n. 2, p. 303-338, 2010.",
        f"FRAGA, D. <b>Acesso danificado acumulando água na rua São Carlos do Pinhal</b>. São Paulo, 2010a. 1 vídeo. "
        f"Licença CC BY 3.0. Disponível em: {wmurl('Acesso danificado acumulando água na rua São Carlos do Pinhal.webm')}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Buraco sem tampa na calçada</b>. São Paulo, 2010b. 1 vídeo. Licença CC BY 3.0. Disponível em: "
        f"{wmurl('Buraco sem tampa na calçada.webm')}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Calçada abandonada na rua Cardeal Leme</b>: rua da Feira (Bela Vista). São Paulo, 2010c. 1 vídeo. "
        f"Licença CC BY 3.0. Disponível em: {wmurl(CARDEAL)}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Calçada danificada na alameda Ribeirão Preto, 314 (Bela Vista)</b>. São Paulo, 2010d. 1 vídeo. "
        f"Licença CC BY 3.0. Disponível em: {wmurl('Calçada danificada na alameda Ribeirão Preto, 314 (Bela Vista).webm')}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Calçada danificada na alameda Ribeirão Preto, 362 (Bela Vista)</b>. São Paulo, 2010e. 1 vídeo. "
        f"Licença CC BY 3.0. Disponível em: {wmurl('Calçada danificada na alameda Ribeirão Preto, 362 (Bela Vista).webm')}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Calçada danificada na rua Rocha, 206 (Bela Vista)</b>. São Paulo, 2010f. 1 vídeo. Licença CC BY "
        f"3.0. Disponível em: {wmurl('Calçada danificada na rua Rocha, 206 (Bela Vista).webm')}. Acesso em: {ACESSO}.",
        f"FRAGA, D. <b>Madeira jogada na calçada</b>. São Paulo, 2010g. 1 vídeo. Licença CC BY 3.0. Disponível em: "
        f"{wmurl('Madeira jogada na calçada.webm')}. Acesso em: {ACESSO}.",
        "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA. <b>Pessoas com deficiência</b>: 2022. Rio de Janeiro: IBGE, "
        "2023. (Pesquisa Nacional por Amostra de Domicílios Contínua).",
        "JOCHER, G.; QIU, J. <b>Ultralytics YOLO11</b>. Versão 11.0.0. [<i>S. l.</i>]: Ultralytics, 2024. Disponível em: "
        f"{link('https://github.com/ultralytics/ultralytics')}. Acesso em: {ACESSO}.",
        "LIN, T.-Y. <i>et al.</i> Microsoft COCO: common objects in context. <i>In</i>: EUROPEAN CONFERENCE ON COMPUTER "
        "VISION, 13., 2014, Zurique. <b>Proceedings</b> [...]. Cham: Springer, 2014. p. 740-755.",
        "PAN, S. J.; YANG, Q. A survey on transfer learning. <b>IEEE Transactions on Knowledge and Data Engineering</b>, "
        "v. 22, n. 10, p. 1345-1359, 2010.",
        "REDMON, J. <i>et al.</i> You only look once: unified, real-time object detection. <i>In</i>: IEEE CONFERENCE ON "
        "COMPUTER VISION AND PATTERN RECOGNITION, 2016, Las Vegas. <b>Proceedings</b> [...]. Piscataway: IEEE, 2016. "
        "p. 779-788.",
        "RUPESH002. <b>Pothole detection dataset</b>. [<i>S. l.</i>]: Hugging Face, 2025. Conjunto de dados. Disponível "
        f"em: {link('https://huggingface.co/datasets/rupesh002/pothole-detection-dataset')}. Acesso em: {ACESSO}.",
        "ULTRALYTICS. <b>Ultralytics YOLO26</b>. [<i>S. l.</i>]: Ultralytics, 2026. Documentação. Disponível em: "
        f"{link('https://docs.ultralytics.com/models/yolo26/')}. Acesso em: {ACESSO}.",
        f"VIDEOJOURNALISMS. <b>Nova lixeira na calçada atrapalha pedestres</b>. São Paulo, 2013. 1 vídeo. Licença CC BY "
        f"3.0. Disponível em: {wmurl('Nova lixeira na calçada atrapalha pedestres.webm')}. Acesso em: {ACESSO}.",
        "VIOLA, P.; JONES, M. Rapid object detection using a boosted cascade of simple features. <i>In</i>: IEEE COMPUTER "
        "SOCIETY CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION, 2001, Kauai. <b>Proceedings</b> [...]. Los "
        "Alamitos: IEEE, 2001. v. 1, p. 511-518.",
        "ZANDI, A. <b>Obstacle detection dataset (ROD-Dataset)</b>. Teerã: Amirkabir University of Technology, 2026. "
        "Conjunto de dados. Disponível em: "
        f"{link('https://huggingface.co/datasets/Abtinzandi/Obstacle-Detection-Dataset-YOLO')}. Acesso em: {ACESSO}.",
        "ZAUNER, C. <b>Implementation and benchmarking of perceptual image hash functions</b>. 2010. Dissertação "
        "(Mestrado em Secure Information Systems) – Upper Austria University of Applied Sciences, Hagenberg, 2010.",
        "ZHANG, Y. <i>et al.</i> ByteTrack: multi-object tracking by associating every detection box. <i>In</i>: EUROPEAN "
        "CONFERENCE ON COMPUTER VISION, 17., 2022, Tel Aviv. <b>Proceedings</b> [...]. Cham: Springer, 2022. p. 1-21.",
    ]
    h += [KeepTogether([P(r, "referencia")]) for r in refs]
    return h, resumo, abstract, nr, no


def pre_textuais(reg: Registro, resumo: str, abstract: str) -> list:
    pre = [Capa(), PageBreak(), Capa(folha_de_rosto=True)]
    pre += titulo_sem_numero(None, "Resumo")
    pre += [P(resumo, "sem_recuo"), Spacer(1, LINHA),
            P("<b>Palavras-chave:</b> visão computacional; detecção de objetos; YOLO26; acessibilidade urbana; calçadas.",
              "sem_recuo")]
    pre += titulo_sem_numero(None, "Links do projeto")
    pre += [P(f"<b>Repositório no GitHub:</b> {link(REPO_URL)}", "sem_recuo"), Spacer(1, LINHA),
            P(f"<b>Vídeo de demonstração (YouTube):</b> {link(VIDEO_URL)}", "sem_recuo")]
    pre += titulo_sem_numero(None, "Sumário")
    for tipo, n, texto, ch in reg.itens:
        if tipo == "sec1":
            pre.append(Linha(n, texto, reg.pagina(ch), TB))
        elif tipo == "sec2":
            pre.append(Linha(n, texto, reg.pagina(ch), T))
        elif tipo == "sec0":
            pre.append(Linha("", texto, reg.pagina(ch), TB, 0))
    return pre


def montar(paginas: dict[str, int], destino) -> tuple[Documento, int, int]:
    d = carregar()
    reg = Registro(paginas)
    corpo, resumo, abstract, nr, no = conteudo(reg, d)
    doc = Documento(destino, title="Calçada Livre: detecção de barreiras em calçadas em tempo real com YOLO26",
                    author=", ".join(n for n, _ in TEAM), subject="Applied Computer Vision, FIAP Global Solution 2026.2")
    doc.build(pre_textuais(reg, resumo, abstract) + corpo)
    return doc, nr, no


def main() -> None:
    doc1, _, _ = montar({}, io.BytesIO())          # 1ª passagem: descobre as páginas
    OUT.parent.mkdir(exist_ok=True)
    doc2, nr, no = montar(doc1.paginas, str(OUT))  # 2ª passagem: sumário e listas com as páginas certas
    if doc2.paginas != doc1.paginas:
        sys.exit("As páginas mudaram entre as passagens; rode de novo.")
    print(f"Resumo: {nr} palavras | Objetivo: {no} palavras | páginas: {doc2.page}")
    print("PDF gerado em", OUT)


if __name__ == "__main__":
    main()
