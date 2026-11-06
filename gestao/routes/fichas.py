from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..crud import destino_seguro
from ..extensions import db
from ..models import Contrato, Despesa, Imovel, Inquilino, Pagamento, Predio
from ..services import alugueis
from ..services.predio import montar_andares, ordem_natural

bp = Blueprint("fichas", __name__)


def _pagamentos_recentes(*filtros, limite=10):
    return (Pagamento.query.join(Contrato, Pagamento.contrato_id == Contrato.id)
            .filter(*filtros).order_by(Pagamento.data_pagamento.desc(), Pagamento.id.desc())
            .limit(limite).all())


@bp.route("/predios/<int:id>")
def predio(id):
    p = db.get_or_404(Predio, id)
    andares = montar_andares(p.imoveis)
    vagas = sorted((i for i in p.imoveis if i.tipo == "vaga"),
                   key=lambda v: ordem_natural(v.identificacao))
    alugadas = [i for i in p.imoveis if not i.disponivel]
    receita = sum((Decimal(str(i.contrato_ativo.valor_mensal)) for i in alugadas), Decimal("0"))
    despesas = (Despesa.query.filter_by(predio_id=p.id)
                .order_by(Despesa.data.desc(), Despesa.id.desc()).limit(5).all())
    return render_template("ficha_predio.html", p=p, andares=andares, vagas=vagas,
                           alugadas=len(alugadas), receita=receita, despesas=despesas)


@bp.route("/garagem")
def garagem():
    """Todas as vagas de garagem (por prédio e avulsas), verde = alugada, amarelo = vaga."""
    vagas = Imovel.query.filter_by(tipo="vaga").all()
    por_predio = {}
    for v in sorted(vagas, key=lambda v: ordem_natural(v.identificacao)):
        por_predio.setdefault(v.predio, []).append(v)
    grupos = [(pr.nome, pr, lista) for pr, lista in
              sorted(((pr, l) for pr, l in por_predio.items() if pr is not None),
                     key=lambda x: x[0].nome.lower())]
    if None in por_predio:
        grupos.append(("Vagas avulsas", None, por_predio[None]))
    alugadas = sum(not v.disponivel for v in vagas)
    return render_template("garagem.html", grupos=grupos, total=len(vagas), alugadas=alugadas)


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
