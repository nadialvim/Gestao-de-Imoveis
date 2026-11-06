"""Utilidades de PDF (reportlab) compartilhadas pelos relatórios: layout A4 limpo, tabelas
com células que quebram linha, números alinhados à direita e rodapé com paginação."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (CondPageBreak, HRFlowable, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

PETROLEO = colors.HexColor("#0f3d4c")
ACENTO = colors.HexColor("#0e7490")
TEXTO = colors.HexColor("#1d2b33")
CINZA = colors.HexColor("#6b7c86")
LINHA = colors.HexColor("#d9e2e7")
ZEBRA = colors.HexColor("#f4f7f9")
DESTAQUE = colors.HexColor("#e1f0f4")
VERDE = colors.HexColor("#15803d")
VERMELHO = colors.HexColor("#b42318")

MARGEM = 36
LARGURA = A4[0] - 2 * MARGEM - 12  # área útil do quadro (descontado o preenchimento de 6 pt)

_BASE = dict(fontName="Helvetica", textColor=TEXTO)
ESTILOS = {
    "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=18, leading=22,
                             textColor=PETROLEO, spaceAfter=2),
    "subtitulo": ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=10.5, leading=14,
                                textColor=CINZA, spaceAfter=10),
    "secao": ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                            textColor=PETROLEO, spaceBefore=14, spaceAfter=3),
    "nota": ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=8, leading=10,
                           textColor=CINZA, spaceBefore=3),
    "cel": ParagraphStyle("cel", fontSize=8.5, leading=10.5, **_BASE),
    "cel_dir": ParagraphStyle("cel_dir", fontSize=8.5, leading=10.5, alignment=TA_RIGHT, **_BASE),
    "cel_cen": ParagraphStyle("cel_cen", fontSize=8.5, leading=10.5, alignment=TA_CENTER, **_BASE),
    "cab": ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=8, leading=10,
                          textColor=colors.white),
    "cab_dir": ParagraphStyle("cab_dir", fontName="Helvetica-Bold", fontSize=8, leading=10,
                              textColor=colors.white, alignment=TA_RIGHT),
    "cab_cen": ParagraphStyle("cab_cen", fontName="Helvetica-Bold", fontSize=8, leading=10,
                              textColor=colors.white, alignment=TA_CENTER),
    "cartao_rotulo": ParagraphStyle("cartao_rotulo", fontName="Helvetica", fontSize=8, leading=10,
                                    textColor=CINZA),
    "cartao_valor": ParagraphStyle("cartao_valor", fontName="Helvetica-Bold", fontSize=14,
                                   leading=18, textColor=TEXTO),
}
_ALINH = {"l": ("cel", "cab"), "r": ("cel_dir", "cab_dir"), "c": ("cel_cen", "cab_cen")}


class _NumberedCanvas(canvas.Canvas):
    """Canvas que sabe o total de páginas (para 'Página X de Y')."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._rodape(total)
            super().showPage()
        super().save()

    def _rodape(self, total):
        self.setStrokeColor(LINHA)
        self.setLineWidth(0.6)
        self.line(MARGEM, 30, A4[0] - MARGEM, 30)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(CINZA)
        self.drawString(MARGEM, 19, f"Gestão de Imóveis · gerado em {datetime.now():%d/%m/%Y %H:%M}")
        self.drawRightString(A4[0] - MARGEM, 19, f"Página {self._pageNumber} de {total}")


def _faixa_topo(c, doc):
    c.saveState()
    c.setFillColor(PETROLEO)
    c.rect(0, A4[1] - 14, A4[0], 14, stroke=0, fill=1)
    c.restoreState()


def esc(texto):
    return escape("" if texto is None else str(texto))


def novo_documento(titulo, assunto):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                            topMargin=MARGEM + 6, bottomMargin=MARGEM + 6, title=titulo,
                            subject=assunto, author="Gestão de Imóveis")
    return buf, doc


def construir(buf, doc, historia):
    doc.build(historia, onFirstPage=_faixa_topo, onLaterPages=_faixa_topo,
              canvasmaker=_NumberedCanvas)
    return buf.getvalue()


def cabecalho(titulo, subtitulo):
    return [Paragraph(esc(titulo), ESTILOS["titulo"]), Paragraph(esc(subtitulo), ESTILOS["subtitulo"]),
            HRFlowable(width="100%", thickness=1.2, color=ACENTO, spaceAfter=8)]


def secao(titulo, altura_minima=110):
    """Título de seção que não fica sozinho no fim da página."""
    return [CondPageBreak(altura_minima), Paragraph(esc(titulo), ESTILOS["secao"])]


def nota(texto):
    return Paragraph(esc(texto), ESTILOS["nota"])


def cartoes(itens):
    """Linha de cartões de resumo. itens = [(rótulo, valor, cor)]."""
    n = len(itens)
    largura = (LARGURA - 8 * (n - 1)) / n
    celulas, estilo = [], []
    for k, (rotulo, valor, cor) in enumerate(itens):
        estilo_valor = ParagraphStyle(f"v{k}", parent=ESTILOS["cartao_valor"], textColor=cor or TEXTO)
        celulas.append([Paragraph(esc(rotulo), ESTILOS["cartao_rotulo"]),
                        Paragraph(esc(valor), estilo_valor)])
    # cada cartão é uma mini-tabela; a linha externa tem espaços entre os cartões
    minis = []
    for c in celulas:
        t = Table([[c[0]], [c[1]]], colWidths=[largura])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.7, LINHA),
                               ("BACKGROUND", (0, 0), (-1, -1), ZEBRA),
                               ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                               ("TOPPADDING", (0, 0), (0, 0), 7), ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                               ("TOPPADDING", (0, 1), (0, 1), 1), ("BOTTOMPADDING", (0, 1), (0, 1), 8)]))
        minis.append(t)
    linha = []
    for k, t in enumerate(minis):
        linha.append(t)
        if k < n - 1:
            linha.append("")
    larguras = []
    for k in range(n):
        larguras.append(largura)
        if k < n - 1:
            larguras.append(8)
    externa = Table([linha], colWidths=larguras)
    externa.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return externa


def tabela(cabecalho_cols, linhas, pesos, alinhamentos, n_totais=0, vazio=None):
    """Tabela com larguras proporcionais aos `pesos` (somam a área útil), células que
    quebram linha, zebra e linhas finais de total em destaque.

    alinhamentos: string com 'l', 'r' ou 'c' por coluna. Se `linhas` estiver vazia
    (sem contar totais) mostra `vazio` ocupando a linha toda.
    """
    soma = float(sum(pesos))
    larguras = [LARGURA * p / soma for p in pesos]
    cab = [Paragraph(esc(t), ESTILOS[_ALINH[a][1]]) for t, a in zip(cabecalho_cols, alinhamentos)]
    corpo = linhas[:len(linhas) - n_totais] if n_totais else list(linhas)
    totais = linhas[len(linhas) - n_totais:] if n_totais else []
    dados = [cab]
    for linha in corpo + totais:
        dados.append([Paragraph(v if isinstance(v, Html) else esc(v), ESTILOS[_ALINH[a][0]])
                      for v, a in zip(linha, alinhamentos)])
    estilo = [("BACKGROUND", (0, 0), (-1, 0), PETROLEO),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
              ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA),
              ("BOX", (0, 0), (-1, -1), 0.6, LINHA)]
    for i in range(len(corpo)):
        if i % 2 == 1:
            estilo.append(("BACKGROUND", (0, i + 1), (-1, i + 1), ZEBRA))
    if not corpo and vazio:
        dados = [cab, [Paragraph(esc(vazio), ESTILOS["cel"])] + [""] * (len(cab) - 1)] + dados[2:]
        estilo.append(("SPAN", (0, 1), (-1, 1)))
    if n_totais:
        primeiro = len(dados) - n_totais
        estilo += [("BACKGROUND", (0, primeiro), (-1, -1), DESTAQUE),
                   ("LINEABOVE", (0, primeiro), (-1, primeiro), 0.9, ACENTO)]
        if len(dados) - n_totais >= 2:  # nunca deixa o(s) total(is) sozinho(s) na página seguinte
            estilo.append(("NOSPLIT", (0, max(1, primeiro - 1)), (-1, -1)))
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle(estilo))
    return t


class Html(str):
    """Marcação reportlab (<b>, <font>) que não deve ser escapada dentro das células."""


def negrito(texto, cor=None):
    """Texto em negrito (e opcionalmente colorido) para células de total."""
    cor_hex = (cor or TEXTO).hexval().replace("0x", "#")
    return Html(f'<b><font color="{cor_hex}">{esc(texto)}</font></b>')


def juntos(*elementos):
    """Mantém os elementos na mesma página."""
    return KeepTogether(list(elementos))


def espaco(altura=10):
    return Spacer(1, altura)
