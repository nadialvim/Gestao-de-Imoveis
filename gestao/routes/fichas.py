from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..crud import destino_seguro
from ..extensions import db
from ..models import Contrato, Despesa, Imovel, Inquilino, Pagamento, Predio
from ..services import alugueis

bp = Blueprint("fichas", __name__)


def _pagamentos_recentes(*filtros, limite=10):
    return (Pagamento.query.join(Contrato, Pagamento.contrato_id == Contrato.id)
            .filter(*filtros).order_by(Pagamento.data_pagamento.desc(), Pagamento.id.desc())
            .limit(limite).all())


@bp.route("/predios/<int:id>")
def predio(id):
    p = db.get_or_404(Predio, id)
    grupos = []
    plurais = {"apartamento": "Apartamentos", "casa": "Casas", "loja": "Lojas",
               "vaga": "Vagas de garagem"}
    for tipo, _ in Imovel.TIPOS:
        unidades = [i for i in p.imoveis if i.tipo == tipo]
        if unidades:
            grupos.append((plurais[tipo], unidades))
    alugadas = [i for i in p.imoveis if not i.disponivel]
    receita = sum((Decimal(str(i.contrato_ativo.valor_mensal)) for i in alugadas), Decimal("0"))
    despesas = (Despesa.query.filter_by(predio_id=p.id)
                .order_by(Despesa.data.desc(), Despesa.id.desc()).limit(5).all())
    return render_template("ficha_predio.html", p=p, grupos=grupos, alugadas=len(alugadas),
                           receita=receita, despesas=despesas)


@bp.route("/imoveis/<int:id>")
def imovel(id):
    i = db.get_or_404(Imovel, id)
    pagamentos = _pagamentos_recentes(Contrato.imovel_id == i.id)
    return render_template("ficha_imovel.html", i=i, pagamentos=pagamentos,
                           hoje=date.today().isoformat())


@bp.route("/inquilinos/<int:id>")
def inquilino(id):
    q = db.get_or_404(Inquilino, id)
    pagamentos = _pagamentos_recentes(Contrato.inquilino_id == q.id)
    return render_template("ficha_inquilino.html", q=q, pagamentos=pagamentos,
                           debito=alugueis.debito_do_inquilino(q.id),
                           hoje=date.today().isoformat())


@bp.route("/alugueis/<int:id>/baixa", methods=["POST"])
def baixar(id):
    """Dá baixa no aluguel (devolução), liberando o imóvel para nova locação."""
    contrato = db.get_or_404(Contrato, id)
    destino = (destino_seguro(request.form.get("next"))
               or url_for("fichas.inquilino", id=contrato.inquilino_id))
    try:
        data = date.fromisoformat(request.form.get("data_devolucao", ""))
    except ValueError:
        data = None
    erro = alugueis.dar_baixa(contrato, data)
    if erro:
        flash(erro, "danger")
    else:
        flash(f"Baixa registrada: {contrato.imovel} está disponível para locação.", "success")
    return redirect(destino)
