from flask import Blueprint, Response, render_template, request

from ..services import relatorio
from ..services.periodo import parse_mes

bp = Blueprint("main", __name__)


@bp.route("/")
def dashboard():
    ano, mes = parse_mes(None)
    return render_template("dashboard.html", d=relatorio.dados_mes(ano, mes),
                           serie=relatorio.serie_meses(ano, mes))


@bp.route("/relatorios/")
def relatorios():
    ano, mes = parse_mes(request.args.get("mes"))
    return render_template("relatorio.html", d=relatorio.dados_mes(ano, mes),
                           mes=f"{ano:04d}-{mes:02d}")


@bp.route("/relatorios/debitos")
def debitos():
    return render_template("relatorio_debitos.html", d=relatorio.debitos())


@bp.route("/relatorios/exportar.<formato>")
def exportar(formato):
    if formato not in ("pdf", "xlsx"):
        return Response(status=404)
    ano, mes = parse_mes(request.args.get("mes"))
    d = relatorio.dados_mes(ano, mes)
    nome = f"relatorio-{ano:04d}-{mes:02d}.{formato}"
    if formato == "pdf":
        corpo, tipo = relatorio.gerar_pdf(d), "application/pdf"
    else:
        corpo = relatorio.gerar_xlsx(d)
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(corpo, mimetype=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})
