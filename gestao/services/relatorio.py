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
from ..models import FORMAS_PAGAMENTO, NAO_INFORMADO, RECEBEDORES, Contrato, Despesa, Pagamento
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


def fechamento(ano, mes):
    """Fechamento do mês por pessoa: recebido (por forma de pagamento), despesas pagas e saldo."""
    d = dados_mes(ano, mes)
    ZERO = Decimal("0")

    def pessoa_de(nome):
        return nome if nome in RECEBEDORES else NAO_INFORMADO

    nomes = list(RECEBEDORES)
    if (any(pessoa_de(p.recebido_por) == NAO_INFORMADO for p in d["pagamentos"])
            or any(pessoa_de(x.pago_por) == NAO_INFORMADO for x in d["despesas"])):
        nomes.append(NAO_INFORMADO)

    pessoas = []
    for nome in nomes:
        pagamentos = [p for p in d["pagamentos"] if pessoa_de(p.recebido_por) == nome]
        despesas = [x for x in d["despesas"] if pessoa_de(x.pago_por) == nome]
        por_forma = {f: sum((p.valor_pago for p in pagamentos if p.forma_pagamento == f), ZERO)
                     for f in FORMAS_PAGAMENTO}
        por_forma["Outras / não informada"] = sum(
            (p.valor_pago for p in pagamentos if p.forma_pagamento not in FORMAS_PAGAMENTO), ZERO)
        recebido = sum((p.valor_pago for p in pagamentos), ZERO)
        gasto = sum((x.valor for x in despesas), ZERO)
        pessoas.append({"nome": nome, "pagamentos": pagamentos, "despesas": despesas,
                        "por_forma": por_forma, "qtd": len(pagamentos), "recebido": recebido,
                        "gasto": gasto, "saldo": recebido - gasto})
    formas = list(FORMAS_PAGAMENTO) + ["Outras / não informada"]
    totais_forma = {f: sum((p["por_forma"][f] for p in pessoas), ZERO) for f in formas}
    return {"ano": ano, "mes": mes, "competencia": d["competencia"], "pessoas": pessoas,
            "formas": formas, "totais_forma": totais_forma,
            "total_recebido": d["total_recebido"], "total_despesas": d["total_despesas"],
            "saldo": d["saldo"]}


def gerar_xlsx_fechamento(f):
    wb = Workbook()
    negrito = Font(bold=True)
    moeda = '"R$" #,##0.00'

    ws = wb.active
    ws.title = "Resumo"
    ws.append([f"Fechamento por pessoa — {mes_br(f['competencia'])}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Pessoa"] + f["formas"] + ["Total recebido", "Despesas pagas", "Saldo"])
    for c in ws[3]:
        c.font = negrito
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for p in f["pessoas"]:
        ws.append([p["nome"]] + [float(p["por_forma"][x]) for x in f["formas"]]
                  + [float(p["recebido"]), float(p["gasto"]), float(p["saldo"])])
    ws.append(["Total"] + [float(f["totais_forma"][x]) for x in f["formas"]]
              + [float(f["total_recebido"]), float(f["total_despesas"]), float(f["saldo"])])
    for c in ws[ws.max_row]:
        c.font = negrito
    for row in ws.iter_rows(min_row=4):
        for c in row[1:]:
            c.number_format = moeda
    ws.column_dimensions["A"].width = 18
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 18

    for p in f["pessoas"]:
        s = wb.create_sheet(p["nome"][:31])
        s.append([f"{p['nome']} — {mes_br(f['competencia'])}"])
        s["A1"].font = Font(bold=True, size=13)
        s.append([])
        s.append(["Pagamentos recebidos"])
        s.cell(s.max_row, 1).font = negrito
        s.append(["Data", "Referência", "Inquilino", "Imóvel", "Forma", "Valor"])
        for c in s[s.max_row]:
            c.font = negrito
        for x in p["pagamentos"]:
            s.append([x.data_pagamento, mes_br(x.competencia), x.contrato.inquilino.nome,
                      str(x.contrato.imovel), x.forma_pagamento or "", float(x.valor_pago)])
            s.cell(s.max_row, 1).number_format = "DD/MM/YYYY"
            s.cell(s.max_row, 6).number_format = moeda
        s.append(["", "", "", "", "Total recebido", float(p["recebido"])])
        s.cell(s.max_row, 5).font = negrito
        s.cell(s.max_row, 6).number_format = moeda
        s.cell(s.max_row, 6).font = negrito
        s.append([])
        s.append(["Despesas pagas"])
        s.cell(s.max_row, 1).font = negrito
        s.append(["Data", "Descrição", "Categoria", "Prédio", "", "Valor"])
        for c in s[s.max_row]:
            c.font = negrito
        for x in p["despesas"]:
            s.append([x.data, x.descricao, x.categoria or "", x.predio.nome if x.predio else "", "",
                      float(x.valor)])
            s.cell(s.max_row, 1).number_format = "DD/MM/YYYY"
            s.cell(s.max_row, 6).number_format = moeda
        s.append(["", "", "", "", "Total de despesas", float(p["gasto"])])
        s.append(["", "", "", "", "SALDO (recebido − despesas)", float(p["saldo"])])
        for r in (s.max_row - 1, s.max_row):
            s.cell(r, 5).font = negrito
            s.cell(r, 6).number_format = moeda
            s.cell(r, 6).font = negrito
        for col, w in zip("ABCDEF", (12, 34, 28, 34, 28, 16)):
            s.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gerar_pdf_fechamento(f):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36,
                            bottomMargin=36, title=f"Fechamento {mes_br(f['competencia'])}")
    estilos = getSampleStyleSheet()
    el = [Paragraph(f"Fechamento por pessoa — {mes_br(f['competencia'])}", estilos["Title"])]

    def tabela(dados, larguras, total_linhas=1, alinhar_direita_a_partir=1):
        t = Table(dados, colWidths=larguras, repeatRows=1)
        estilo = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                  ("ALIGN", (alinhar_direita_a_partir, 0), (-1, -1), "RIGHT"),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        if total_linhas:
            estilo.append(("FONTNAME", (0, -total_linhas), (-1, -1), "Helvetica-Bold"))
        t.setStyle(TableStyle(estilo))
        return t

    cab = ["Pessoa"] + [x.replace(" bancária (TED/DOC)", "") for x in f["formas"]] \
        + ["Recebido", "Despesas", "Saldo"]
    linhas = [[p["nome"]] + [brl(p["por_forma"][x]) for x in f["formas"]]
              + [brl(p["recebido"]), brl(p["gasto"]), brl(p["saldo"])] for p in f["pessoas"]]
    linhas.append(["Total"] + [brl(f["totais_forma"][x]) for x in f["formas"]]
                  + [brl(f["total_recebido"]), brl(f["total_despesas"]), brl(f["saldo"])])
    n = len(cab)
    el.append(tabela([cab] + linhas, [60] + [(523 - 60) / (n - 1)] * (n - 1)))

    for p in f["pessoas"]:
        el += [Spacer(1, 14), Paragraph(f"{p['nome']}", estilos["Heading2"])]
        linhas = [[data_br(x.data_pagamento), mes_br(x.competencia), x.contrato.inquilino.nome,
                   str(x.contrato.imovel), x.forma_pagamento or "", brl(x.valor_pago)]
                  for x in p["pagamentos"]]
        linhas.append(["", "", "", "", "Total recebido", brl(p["recebido"])])
        el.append(tabela([["Data", "Referência", "Inquilino", "Imóvel", "Forma", "Valor"]] + linhas,
                         [52, 62, 95, 150, 94, 70], alinhar_direita_a_partir=5))
        el.append(Spacer(1, 6))
        linhas = [[data_br(x.data), x.descricao, x.categoria or "", brl(x.valor)]
                  for x in p["despesas"]]
        linhas.append(["", "", "Total de despesas", brl(p["gasto"])])
        linhas.append(["", "", "SALDO (recebido − despesas)", brl(p["saldo"])])
        el.append(tabela([["Data", "Despesa", "Categoria", "Valor"]] + linhas,
                         [52, 230, 151, 90], total_linhas=2, alinhar_direita_a_partir=3))
    doc.build(el)
    return buf.getvalue()


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
