import calendar
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func

from ..extensions import db
from ..formatting import brl, data_br, mes_br
from ..models import Contrato, Despesa, Pagamento
from .periodo import intervalo_mes


def dados_mes(ano, mes):
    """Consolida recebimentos, despesas e pendências de um mês."""
    inicio, fim = intervalo_mes(ano, mes)
    competencia = date(ano, mes, 1)

    pagamentos = (Pagamento.query
                  .filter(Pagamento.data_pagamento >= inicio,
                          Pagamento.data_pagamento <= fim)
                  .order_by(Pagamento.data_pagamento, Pagamento.id).all())
    despesas = (Despesa.query
                .filter(Despesa.data >= inicio, Despesa.data <= fim)
                .order_by(Despesa.data, Despesa.id).all())

    total_recebido = sum((p.valor_pago for p in pagamentos), Decimal("0"))
    total_despesas = sum((d.valor for d in despesas), Decimal("0"))

    # Contratos vigentes no mês e quanto já foi pago para a competência.
    pagos = dict(
        db.session.query(Pagamento.contrato_id, func.sum(Pagamento.valor_pago))
        .filter(Pagamento.competencia == competencia)
        .group_by(Pagamento.contrato_id).all()
    )
    vigentes = (Contrato.query
                .filter(Contrato.data_inicio <= fim,
                        func.coalesce(Contrato.encerrado_em, Contrato.data_fim) >= inicio)
                .all())
    hoje = date.today()
    pendentes = []
    for c in vigentes:
        pago = Decimal(pagos.get(c.id) or 0)
        if pago < c.valor_mensal:
            venc = date(ano, mes, min(c.dia_vencimento, fim.day))
            pendentes.append({
                "contrato": c,
                "em_aberto": c.valor_mensal - pago,
                "vencimento": venc,
                "atrasado": hoje > venc,
            })
    pendentes.sort(key=lambda p: (p["vencimento"], str(p["contrato"])))

    return {
        "ano": ano, "mes": mes, "competencia": competencia,
        "pagamentos": pagamentos, "despesas": despesas,
        "total_recebido": total_recebido, "total_despesas": total_despesas,
        "saldo": total_recebido - total_despesas, "pendentes": pendentes,
    }


def serie_meses(ano, mes, n=6):
    """Totais recebidos e de despesas dos últimos n meses (inclui o mês dado)."""
    itens = []
    a, m = ano, mes
    for _ in range(n):
        itens.append((a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    itens.reverse()
    saida = []
    for a, m in itens:
        inicio, fim = intervalo_mes(a, m)
        rec = (db.session.query(func.coalesce(func.sum(Pagamento.valor_pago), 0))
               .filter(Pagamento.data_pagamento >= inicio,
                       Pagamento.data_pagamento <= fim).scalar())
        desp = (db.session.query(func.coalesce(func.sum(Despesa.valor), 0))
                .filter(Despesa.data >= inicio, Despesa.data <= fim).scalar())
        saida.append({"rotulo": mes_br(date(a, m, 1)), "recebido": float(rec),
                      "despesas": float(desp)})
    return saida


def debitos(hoje=None):
    """Inquilinos com valores vencidos e não pagos (todos os meses desde o início do contrato).

    Um mês só conta depois do dia de vencimento; meses cujo vencimento é anterior ao início
    do contrato não são cobrados. Usa o valor mensal atual do contrato.
    """
    hoje = hoje or date.today()
    pagos = defaultdict(Decimal)
    for cid, comp, total in (db.session.query(Pagamento.contrato_id, Pagamento.competencia,
                                              func.sum(Pagamento.valor_pago))
                             .group_by(Pagamento.contrato_id, Pagamento.competencia)):
        pagos[(cid, comp)] = Decimal(str(total))

    por_inquilino = {}
    for c in Contrato.query.all():
        limite = min(hoje, c.encerrado_em or c.data_fim)
        a, m = c.data_inicio.year, c.data_inicio.month
        while (a, m) <= (limite.year, limite.month):
            venc = date(a, m, min(c.dia_vencimento, calendar.monthrange(a, m)[1]))
            if c.data_inicio <= venc < hoje:
                devido = Decimal(str(c.valor_mensal))
                falta = devido - pagos.get((c.id, date(a, m, 1)), Decimal("0"))
                if falta > 0:
                    item = por_inquilino.setdefault(c.inquilino_id, {
                        "inquilino": c.inquilino, "total": Decimal("0"), "meses": []})
                    item["total"] += falta
                    item["meses"].append({
                        "contrato": c, "competencia": date(a, m, 1), "vencimento": venc,
                        "devido": devido, "em_aberto": falta,
                        "dias_atraso": (hoje - venc).days})
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)

    lista = sorted(por_inquilino.values(), key=lambda x: (-x["total"], x["inquilino"].nome))
    for item in lista:
        item["meses"].sort(key=lambda x: x["vencimento"])
    return {"hoje": hoje, "inquilinos": lista,
            "total": sum((i["total"] for i in lista), Decimal("0"))}


def gerar_xlsx(d):
    wb = Workbook()
    negrito = Font(bold=True)

    ws = wb.active
    ws.title = "Resumo"
    ws.append([f"Relatório de {mes_br(d['competencia'])}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Total recebido", float(d["total_recebido"])])
    ws.append(["Total de despesas", float(d["total_despesas"])])
    ws.append(["Saldo a repassar", float(d["saldo"])])
    for r in (3, 4, 5):
        ws.cell(r, 1).font = negrito
        ws.cell(r, 2).number_format = '"R$" #,##0.00'
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 18

    wr = wb.create_sheet("Recebimentos")
    wr.append(["Data", "Referência", "Inquilino", "Imóvel", "Forma", "Recebido por", "Valor"])
    for p in d["pagamentos"]:
        wr.append([p.data_pagamento, mes_br(p.competencia), p.contrato.inquilino.nome,
                   str(p.contrato.imovel), p.forma_pagamento or "", p.recebido_por or "",
                   float(p.valor_pago)])
    wr.append(["", "", "", "", "", "Total", float(d["total_recebido"])])

    wd = wb.create_sheet("Despesas")
    wd.append(["Data", "Descrição", "Categoria", "Prédio", "Valor"])
    for x in d["despesas"]:
        wd.append([x.data, x.descricao, x.categoria or "",
                   x.predio.nome if x.predio else "", float(x.valor)])
    wd.append(["", "", "", "Total", float(d["total_despesas"])])

    for sheet, money_col, widths in ((wr, 7, (12, 16, 28, 34, 30, 14, 14)),
                                     (wd, 5, (12, 40, 20, 24, 14))):
        for cell in sheet[1]:
            cell.font = negrito
            cell.alignment = Alignment(horizontal="center")
        for row in sheet.iter_rows(min_row=2):
            row[0].number_format = "DD/MM/YYYY"
            row[money_col - 1].number_format = '"R$" #,##0.00'
        for i, w in enumerate(widths, 1):
            sheet.column_dimensions[chr(64 + i)].width = w
        for cell in sheet[sheet.max_row]:
            cell.font = negrito

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gerar_pdf(d):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36,
                            topMargin=36, bottomMargin=36,
                            title=f"Relatório {mes_br(d['competencia'])}")
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(f"Relatório mensal — {mes_br(d['competencia'])}",
                           estilos["Title"])]

    def tabela(cabecalho, linhas, larguras, rodape=None):
        dados = [cabecalho] + linhas + ([rodape] if rodape else [])
        t = Table(dados, colWidths=larguras, repeatRows=1)
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if rodape:
            estilo.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        t.setStyle(TableStyle(estilo))
        return t

    resumo = Table([["Total recebido", brl(d["total_recebido"])],
                    ["Total de despesas", brl(d["total_despesas"])],
                    ["Saldo a repassar", brl(d["saldo"])]], colWidths=[150, 110])
    resumo.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 2), (-1, 2), 0.75, colors.black),
    ]))
    elementos += [resumo, Spacer(1, 14), Paragraph("Recebimentos", estilos["Heading2"])]

    linhas = [[data_br(p.data_pagamento), mes_br(p.competencia),
               p.contrato.inquilino.nome, str(p.contrato.imovel), p.recebido_por or "",
               brl(p.valor_pago)]
              for p in d["pagamentos"]]
    elementos.append(tabela(
        ["Data", "Referência", "Inquilino", "Imóvel", "Recebido por", "Valor"], linhas,
        [52, 66, 100, 160, 58, 70],
        ["", "", "", "", "Total", brl(d["total_recebido"])]))

    elementos += [Spacer(1, 14), Paragraph("Despesas", estilos["Heading2"])]
    linhas = [[data_br(x.data), x.descricao, x.categoria or "", brl(x.valor)]
              for x in d["despesas"]]
    elementos.append(tabela(
        ["Data", "Descrição", "Categoria", "Valor"], linhas,
        [58, 250, 120, 70], ["", "", "Total", brl(d["total_despesas"])]))

    doc.build(elementos)
    return buf.getvalue()
