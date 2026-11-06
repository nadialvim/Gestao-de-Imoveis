from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .services.periodo import intervalo_mes, parse_mes

bp = Blueprint("crud", __name__, url_prefix="/c")


def _res(slug):
    from .resources import RESOURCES

    res = RESOURCES.get(slug)
    if res is None:
        abort(404)
    return res


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
    if res.order:
        query = query.order_by(*res.order())
    objetos = query.all()
    linhas = [(o.id, [fn(o) for _, fn in res.columns]) for o in objetos]
    return render_template(
        "list.html", res=res, linhas=linhas, mes=mes,
        titulos=[t for t, _ in res.columns],
    )


def _valores_iniciais(res, obj):
    if obj is not None:
        return {f.name: f.to_input(getattr(obj, f.name)) for f in res.fields}
    base = res.new_defaults() if res.new_defaults else {}
    return {f.name: f.to_input(base.get(f.name, f.default)) for f in res.fields}


def _salvar(res, obj):
    dados, erros = {}, []
    for f in res.fields:
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
    for k, v in dados.items():
        setattr(obj, k, v)
    if obj.id is None:
        db.session.add(obj)
    db.session.commit()
    flash(f"{res.singular} salvo(a) com sucesso.", "success")
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
