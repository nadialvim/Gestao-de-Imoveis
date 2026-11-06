from datetime import date
from decimal import Decimal

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Contrato, Pagamento
from .services.periodo import intervalo_mes, parse_mes

bp = Blueprint("crud", __name__, url_prefix="/c")


def _res(slug):
    from .resources import RESOURCES

    res = RESOURCES.get(slug)
    if res is None:
        abort(404)
    return res


def destino_seguro(url):
    """Aceita apenas caminhos internos (evita redirecionamento aberto)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


def _proximo():
    return destino_seguro(request.form.get("next") or request.args.get("next"))


# ---------- endereços antigos ----------
@bp.route("/apartamentos/")
def apartamentos_antigo():
    return redirect(url_for("crud.listar", slug="imoveis"))


@bp.route("/vagas/")
def vagas_antigo():
    return redirect(url_for("fichas.garagem"))


@bp.route("/contratos/")
def contratos_antigo():
    return redirect(url_for("crud.listar", slug="inquilinos"))


# ---------- pagamento: sugestão de valor ----------
@bp.route("/pagamentos/sugestao")
def sugestao_pagamento():
    """Valor do aluguel, já recebido e faltante no mês (pré-preenche o pagamento)."""
    contrato = db.session.get(Contrato, request.args.get("contrato_id", 0, type=int))
    if contrato is None:
        return jsonify({}), 404
    ano, mes = parse_mes(request.args.get("competencia"))
    recebido = db.session.query(func.coalesce(func.sum(Pagamento.valor_pago), 0)).filter(
        Pagamento.contrato_id == contrato.id,
        Pagamento.competencia == date(ano, mes, 1)).scalar()
    valor = Decimal(str(contrato.valor_mensal))
    recebido = Decimal(str(recebido))
    return jsonify(valor_mensal=f"{valor:.2f}", recebido=f"{recebido:.2f}",
                   falta=f"{max(Decimal('0'), valor - recebido):.2f}")


# ---------- CRUD genérico ----------
@bp.route("/<slug>/")
def listar(slug):
    res = _res(slug)
    if not res.lista:
        return redirect(url_for("main.dashboard"))
    query = res.model.query
    mes = None
    if res.month_field:
        ano, m = parse_mes(request.args.get("mes"))
        inicio, fim = intervalo_mes(ano, m)
        col = getattr(res.model, res.month_field)
        query = query.filter(col >= inicio, col <= fim)
        mes = f"{ano:04d}-{m:02d}"
    filtros, situacao = [], ""
    for coluna, rotulo, opcoes in res.filters:
        atual = request.args.get(coluna, "")
        if atual not in {str(v) for v, _ in opcoes}:
            atual = ""
        if atual and coluna == "situacao":
            situacao = atual  # filtro calculado (disponível/alugado), aplicado em Python
        elif atual:
            query = query.filter(getattr(res.model, coluna) == atual)
        filtros.append({"nome": coluna, "rotulo": rotulo, "opcoes": opcoes, "atual": atual})
    if res.order:
        query = query.order_by(*res.order())
    objetos = query.all()
    if situacao:
        objetos = [o for o in objetos if o.disponivel == (situacao == "disponivel")]
    linhas = [(o.id, [fn(o) for _, fn in res.columns], o) for o in objetos]
    return render_template(
        "list.html", res=res, linhas=linhas, mes=mes, filtros=filtros,
        titulos=[t for t, _ in res.columns], hoje=date.today().isoformat(),
    )


def _valores_iniciais(res, obj):
    if obj is not None and obj.id is not None:
        return {f.name: f.to_input(f.default if f.extra else getattr(obj, f.name))
                for f in res.fields}
    base = res.new_defaults() if res.new_defaults else {}
    valores = {f.name: f.to_input(base.get(f.name, f.default)) for f in res.fields}
    for f in res.fields:  # valores iniciais pela URL (ex.: ?aluguel_imoveis=3)
        if f.name in request.args:
            valores[f.name] = (request.args.getlist(f.name) if f.kind == "multi"
                               else request.args[f.name])
    return valores


def _valor_bruto(f):
    return request.form.getlist(f.name) if f.kind == "multi" else request.form.get(f.name)


def _salvar(res, obj):
    dados, erros = {}, []
    for f in list(res.fields) + list(res.extra_fields):
        try:
            dados[f.name] = f.parse(_valor_bruto(f))
        except ValueError as exc:
            erros.append(f"{f.label}: {exc}")
    if not erros and res.validate:
        erros.extend(res.validate(dados, obj))
    if erros:
        for e in erros:
            flash(e, "danger")
        return False
    if not res.sem_modelo:
        for f in res.fields:
            if not f.extra:
                setattr(obj, f.name, dados[f.name])
    if res.before_save:
        res.before_save(obj, dados)
    if obj.id is None and not res.sem_modelo:
        db.session.add(obj)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível salvar: registro duplicado ou inválido.", "danger")
        return False
    flash(f"{res.singular} salvo(a) com sucesso.", "success")
    if res.after_save:
        mensagem = res.after_save(obj, dados)
        if mensagem:
            flash(mensagem, "info")
    obj._dados_salvos = dados
    return True


def _url_depois(res, obj):
    proximo = _proximo()
    if proximo:
        return proximo
    if res.destino:
        return res.destino(obj, getattr(obj, "_dados_salvos", {}))
    if res.ficha and obj.id:
        return url_for(res.ficha, id=obj.id)
    return url_for("crud.listar", slug=res.slug)


def _form(res, obj, titulo):
    if request.method == "POST":
        if _salvar(res, obj):
            return redirect(_url_depois(res, obj))
        db.session.rollback()
        valores = request.form
    else:
        valores = _valores_iniciais(res, obj)
    return render_template("form.html", res=res, valores=valores, titulo=titulo,
                           obj=obj, proximo=_proximo() or "")


@bp.route("/<slug>/novo", methods=["GET", "POST"])
def novo(slug):
    res = _res(slug)
    return _form(res, res.model(), res.titulo_novo or f"Novo(a) {res.singular}")


@bp.route("/<slug>/<int:id>/editar", methods=["GET", "POST"])
def editar(slug, id):
    res = _res(slug)
    obj = db.get_or_404(res.model, id)
    return _form(res, obj, f"Editar {res.singular}")


@bp.route("/<slug>/<int:id>/excluir", methods=["POST"])
def excluir(slug, id):
    res = _res(slug)
    obj = db.get_or_404(res.model, id)
    try:
        db.session.delete(obj)
        db.session.commit()
        flash(f"{res.singular} excluído(a).", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Não é possível excluir: há registros vinculados.", "danger")
    return redirect(url_for("crud.listar", slug=slug))
