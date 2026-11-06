from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Contrato
from .services.periodo import intervalo_mes, parse_mes

bp = Blueprint("crud", __name__, url_prefix="/c")


def _res(slug):
    from .resources import RESOURCES

    res = RESOURCES.get(slug)
    if res is None:
        abort(404)
    return res


@bp.route("/apartamentos/")
def apartamentos_antigo():
    return redirect(url_for("crud.listar", slug="imoveis"))


@bp.route("/<slug>/")
def listar(slug):
    res = _res(slug)
    query = res.model.query
    mes = None
    if res.month_field:
        ano, m = parse_mes(request.args.get("mes"))
        inicio, fim = intervalo_mes(ano, m)
        col = getattr(res.model, res.month_field)
        query = query.filter(col >= inicio, col <= fim)
        mes = f"{ano:04d}-{m:02d}"
    filtros = []
    for coluna, rotulo, opcoes in res.filters:
        atual = request.args.get(coluna, "")
        if atual in {str(v) for v, _ in opcoes}:
            query = query.filter(getattr(res.model, coluna) == atual)
        else:
            atual = ""
        filtros.append({"nome": coluna, "rotulo": rotulo, "opcoes": opcoes, "atual": atual})
    if res.order:
        query = query.order_by(*res.order())
    objetos = query.all()
    linhas = [(o.id, [fn(o) for _, fn in res.columns], o) for o in objetos]
    return render_template(
        "list.html", res=res, linhas=linhas, mes=mes, filtros=filtros,
        titulos=[t for t, _ in res.columns], hoje=date.today().isoformat(),
    )


def _valores_iniciais(res, obj):
    if obj is not None and obj.id is not None:
        return {f.name: f.to_input(getattr(obj, f.name, None)) for f in res.fields}
    base = res.new_defaults() if res.new_defaults else {}
    valores = {f.name: f.to_input(base.get(f.name, f.default)) for f in res.fields}
    for f in res.fields:  # valores iniciais pela URL (ex.: ?imovel_id=3 no botão Alugar)
        if f.name in request.args:
            valores[f.name] = request.args[f.name]
    return valores


def _salvar(res, obj):
    dados, erros = {}, []
    for f in list(res.fields) + list(res.extra_fields):
        try:
            dados[f.name] = f.parse(request.form.get(f.name))
        except ValueError as exc:
            erros.append(f"{f.label}: {exc}")
    if not erros and res.validate:
        erros.extend(res.validate(dados, obj))
    if erros:
        for e in erros:
            flash(e, "danger")
        return False
    for f in res.fields:
        if not f.extra:
            setattr(obj, f.name, dados[f.name])
    if res.before_save:
        res.before_save(obj, dados)
    if obj.id is None:
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
    return True


def _form(res, obj, titulo):
    if request.method == "POST":
        if _salvar(res, obj):
            return redirect(url_for("crud.listar", slug=res.slug))
        db.session.rollback()
        valores = request.form
    else:
        valores = _valores_iniciais(res, obj)
    return render_template("form.html", res=res, valores=valores, titulo=titulo,
                           obj=obj)


@bp.route("/<slug>/novo", methods=["GET", "POST"])
def novo(slug):
    res = _res(slug)
    return _form(res, res.model(), f"Novo(a) {res.singular}")


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


@bp.route("/contratos/<int:id>/baixa", methods=["POST"])
def baixar_contrato(id):
    """Dá baixa no aluguel (devolução do imóvel/vaga), liberando-o para nova locação."""
    contrato = db.get_or_404(Contrato, id)
    voltar = request.form.get("voltar")
    destino = redirect(url_for("crud.listar",
                               slug=voltar if voltar in ("imoveis", "vagas") else "contratos"))
    if not contrato.ativo:
        flash("Este contrato já foi encerrado.", "warning")
        return destino
    try:
        data = date.fromisoformat(request.form.get("data_devolucao", ""))
    except ValueError:
        flash("Informe a data de devolução.", "danger")
        return destino
    if data < contrato.data_inicio:
        flash("A devolução não pode ser anterior ao início do contrato.", "danger")
        return destino
    contrato.ativo = False
    contrato.encerrado_em = data
    db.session.commit()
    flash(f"Baixa registrada: {contrato.imovel} está disponível para locação.", "success")
    return destino
