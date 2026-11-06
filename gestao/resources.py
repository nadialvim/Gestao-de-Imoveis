from datetime import date

from flask import url_for

from .extensions import db
from .fields import Badge, Field, Resource
from .formatting import brl, data_br, mes_br
from .models import (FORMAS_PAGAMENTO, RECEBEDORES, Contrato, Despesa, Imovel, Inquilino,
                     Pagamento, Predio)
from .services import alugueis


# ---------- opções de selects ----------
def opcoes_predios():
    return [(p.id, p.nome) for p in Predio.query.order_by(Predio.nome).all()]


def opcoes_tipos_imovel():
    return Imovel.TIPOS


def _ordenar(itens):
    return sorted(itens, key=lambda x: x[1])


def _com_valor(obj):
    valor = brl(obj.valor_aluguel_padrao) if obj.valor_aluguel_padrao else "sem valor definido"
    return f"{obj} — {valor}"


def opcoes_imoveis_disponiveis():
    """Apartamentos, casas, lojas e vagas livres (com o valor no rótulo)."""
    return _ordenar((i.id, _com_valor(i)) for i in Imovel.query.all() if i.disponivel)


def opcoes_inquilinos():
    return [(i.id, i.nome) for i in Inquilino.query.order_by(Inquilino.nome).all()]


def opcoes_contratos():
    return _ordenar((c.id, str(c) + ("" if c.ativo else " (encerrado)"))
                    for c in Contrato.query.all())


def opcoes_formas():
    return [(f, f) for f in FORMAS_PAGAMENTO]


def opcoes_recebedores():
    return [(r, r) for r in RECEBEDORES]


# ---------- colunas ----------
def situacao(obj):
    return Badge("Disponível", "success") if obj.disponivel else Badge("Alugado", "warning")


def inquilino_atual(obj):
    c = obj.contrato_ativo
    return c.inquilino.nome if c else ""


def faltante_badge(pagamento):
    falta = pagamento.faltante
    return Badge(brl(falta), "danger") if falta > 0 else Badge("Quitado", "success")


# ---------- validações / hooks ----------
def validar_imovel(d, obj):
    erros = []
    if d["tipo"] == "casa":
        d["predio_id"] = None  # casa é independente
    elif d["tipo"] in ("apartamento", "loja") and not d["predio_id"]:
        erros.append("Apartamento e loja precisam estar vinculados a um prédio.")
    if not erros:
        mesmo_predio = (Imovel.predio_id == d["predio_id"] if d["predio_id"]
                        else Imovel.predio_id.is_(None))
        q = Imovel.query.filter(Imovel.tipo == d["tipo"],
                                Imovel.identificacao == d["identificacao"], mesmo_predio)
        if obj is not None and obj.id is not None:
            q = q.filter(Imovel.id != obj.id)
        if q.first():
            erros.append("Já existe um imóvel com essa identificação.")
    return erros


def propagar_valor(obj, dados):
    """Reajuste: o aluguel ativo acompanha o valor do imóvel."""
    contrato = obj.contrato_ativo
    if contrato and obj.valor_aluguel_padrao and contrato.valor_mensal != obj.valor_aluguel_padrao:
        contrato.valor_mensal = obj.valor_aluguel_padrao
        db.session.commit()
        return f"Aluguel ativo de {contrato.inquilino.nome} atualizado para o novo valor."
    return None


UNIDADES_EM_LOTE = (  # (tipo, campo da lista, campo do valor do aluguel)
    ("apartamento", "apartamentos_novos", "aluguel_apartamentos"),
    ("loja", "lojas_novas", "aluguel_lojas"),
    ("vaga", "vagas_novas", "aluguel_vagas"),
)


def criar_unidades(predio, dados):
    """Cria apartamentos/lojas/vagas informados em lote no cadastro/edição do prédio."""
    existentes = {(i.tipo, i.identificacao) for i in predio.imoveis}
    criados = {tipo: 0 for tipo, _, _ in UNIDADES_EM_LOTE}
    for tipo, campo, campo_valor in UNIDADES_EM_LOTE:
        for ident in dados.get(campo) or []:
            if (tipo, ident) in existentes:
                continue
            db.session.add(Imovel(tipo=tipo, predio=predio, identificacao=ident,
                                  valor_aluguel_padrao=dados.get(campo_valor)))
            existentes.add((tipo, ident))
            criados[tipo] += 1
    if not any(criados.values()):
        return None
    db.session.commit()
    return (f"{criados['apartamento']} apartamento(s), {criados['loja']} loja(s) e "
            f"{criados['vaga']} vaga(s) adicionados ao prédio {predio.nome}.")


def _campos_aluguel(obrigatorio=True, secao=None):
    """Campos do aluguel, compartilhados pelo cadastro de inquilino e por 'Novo aluguel'."""
    return [
        Field("aluguel_imoveis", "Imóvel(is) ou vaga(s) a alugar", "multi", extra=True,
              required=obrigatorio, choices=opcoes_imoveis_disponiveis, section=secao),
        Field("aluguel_inicio", "Início do aluguel", "date", required=obrigatorio, extra=True),
        Field("aluguel_fim", "Fim do aluguel", "date", required=obrigatorio, extra=True),
        Field("aluguel_dia_vencimento", "Dia de vencimento", "int", required=obrigatorio,
              default=5, extra=True),
    ]


def validar_inquilino(d, obj):
    """Aluguel opcional no cadastro do inquilino."""
    if not d["aluguel_imoveis"]:
        return []
    return alugueis.validar_alugueis(d["aluguel_imoveis"], d["aluguel_inicio"],
                                     d["aluguel_fim"], d["aluguel_dia_vencimento"])


def criar_alugueis_do_inquilino(obj, d):
    if not d["aluguel_imoveis"]:
        return
    db.session.add(obj)
    db.session.flush()
    alugueis.criar_alugueis(obj, d["aluguel_imoveis"], d["aluguel_inicio"],
                            d["aluguel_fim"], d["aluguel_dia_vencimento"])


def validar_novo_aluguel(d, obj):
    erros = []
    if not d["inquilino_id"] and not d["novo_inquilino_nome"]:
        erros.append("Escolha um inquilino ou informe o nome de um novo.")
    erros.extend(alugueis.validar_alugueis(d["aluguel_imoveis"], d["aluguel_inicio"],
                                           d["aluguel_fim"], d["aluguel_dia_vencimento"]))
    return erros


def criar_novo_aluguel(obj, d):
    if d["inquilino_id"]:
        inq = db.session.get(Inquilino, d["inquilino_id"])
    else:
        inq = Inquilino(nome=d["novo_inquilino_nome"], telefone=d["novo_inquilino_telefone"])
        db.session.add(inq)
        db.session.flush()
    d["_inquilino"] = inq
    alugueis.criar_alugueis(inq, d["aluguel_imoveis"], d["aluguel_inicio"],
                            d["aluguel_fim"], d["aluguel_dia_vencimento"])


def validar_positivo(campo):
    def _v(d, obj):
        return [] if d[campo] > 0 else ["O valor deve ser maior que zero."]
    return _v


# ---------- recursos ----------
RESOURCES = {r.slug: r for r in [
    Resource(
        "predios", Predio, "Prédio", "Prédios",
        ficha="fichas.predio",
        fields=[Field("nome", "Nome"),
                Field("endereco", "Endereço", required=False, wide=True)],
        extra_fields=[
            Field("apartamentos_novos", "Apartamentos do prédio", "lista", required=False,
                  wide=True),
            Field("aluguel_apartamentos", "Aluguel dos apartamentos novos (R$)", "money",
                  required=False),
            Field("lojas_novas", "Lojas do prédio", "lista", required=False, wide=True),
            Field("aluguel_lojas", "Aluguel das lojas novas (R$)", "money", required=False),
            Field("vagas_novas", "Vagas de garagem do prédio", "lista", required=False,
                  wide=True),
            Field("aluguel_vagas", "Aluguel das vagas novas (R$)", "money", required=False)],
        columns=[("Prédio", lambda o: o.nome), ("Endereço", lambda o: o.endereco or ""),
                 ("Unidades", lambda o: len(o.imoveis)),
                 ("Alugadas", lambda o: sum(not i.disponivel for i in o.imoveis))],
        order=lambda: [Predio.nome],
        after_save=criar_unidades,
    ),
    Resource(
        "imoveis", Imovel, "Imóvel", "Imóveis",
        ficha="fichas.imovel",
        fields=[Field("tipo", "Tipo", "choice", choices=opcoes_tipos_imovel,
                      default="apartamento"),
                Field("predio_id", "Prédio (não se aplica a casa)", "select",
                      required=False, choices=opcoes_predios),
                Field("identificacao", "Identificação (nº do apto, loja, vaga ou nome da casa)"),
                Field("valor_aluguel_padrao", "Valor do aluguel (R$)", "money",
                      required=False),
                Field("descricao", "Descrição", required=False, wide=True)],
        columns=[("Imóvel", str),
                 ("Tipo", lambda o: o.tipo_nome),
                 ("Aluguel", lambda o: brl(o.valor_aluguel_padrao)),
                 ("Situação", situacao),
                 ("Inquilino atual", inquilino_atual)],
        order=lambda: [Imovel.predio_id, Imovel.tipo, Imovel.identificacao],
        validate=validar_imovel,
        after_save=propagar_valor,
        filters=[("tipo", "Tipo", Imovel.TIPOS),
                 ("situacao", "Situação", [("disponivel", "Disponíveis"),
                                            ("alugado", "Alugados")])],
    ),
    Resource(
        "inquilinos", Inquilino, "Inquilino", "Inquilinos",
        ficha="fichas.inquilino",
        fields=[Field("nome", "Nome"),
                Field("telefone", "Telefone", required=False),
                Field("email", "E-mail", required=False),
                Field("documento", "CPF / documento", required=False)]
        + _campos_aluguel(obrigatorio=False,
                          secao="Aluguel (opcional) — vincule o imóvel já neste cadastro"),
        columns=[("Inquilino", lambda o: o.nome), ("Telefone", lambda o: o.telefone or ""),
                 ("E-mail", lambda o: o.email or ""),
                 ("Aluguéis ativos",
                  lambda o: ", ".join(str(c.imovel) for c in o.alugueis_ativos) or "—")],
        order=lambda: [Inquilino.nome],
        validate=validar_inquilino,
        before_save=criar_alugueis_do_inquilino,
    ),
    Resource(
        "alugueis", Contrato, "Aluguel", "Aluguéis",
        sem_modelo=True, lista=False, titulo_novo="Novo aluguel",
        destino=lambda obj, d: url_for("fichas.inquilino", id=d["_inquilino"].id),
        fields=[Field("inquilino_id", "Inquilino já cadastrado", "select", required=False,
                      choices=opcoes_inquilinos, extra=True),
                Field("novo_inquilino_nome", "Ou cadastre um novo inquilino (nome)",
                      required=False, extra=True),
                Field("novo_inquilino_telefone", "Telefone do novo inquilino",
                      required=False, extra=True)] + _campos_aluguel(),
        columns=[],
        validate=validar_novo_aluguel,
        before_save=criar_novo_aluguel,
    ),
    Resource(
        "pagamentos", Pagamento, "Pagamento", "Pagamentos recebidos",
        fields=[Field("contrato_id", "Aluguel (inquilino — imóvel)", "select",
                      choices=opcoes_contratos),
                Field("competencia", "Mês de referência", "month"),
                Field("data_pagamento", "Data do pagamento", "date"),
                Field("valor_pago", "Valor recebido (R$)", "money"),
                Field("forma_pagamento", "Forma de pagamento", "choice",
                      choices=opcoes_formas),
                Field("recebido_por", "Recebido por", "choice", choices=opcoes_recebedores),
                Field("observacao", "Observação", required=False, wide=True)],
        columns=[("Data", lambda o: data_br(o.data_pagamento)),
                 ("Referência", lambda o: mes_br(o.competencia)),
                 ("Aluguel", lambda o: str(o.contrato)),
                 ("Valor", lambda o: brl(o.valor_pago)),
                 ("Forma", lambda o: o.forma_pagamento or ""),
                 ("Recebido por", lambda o: o.recebido_por or ""),
                 ("Faltante", faltante_badge)],
        order=lambda: [Pagamento.data_pagamento.desc(), Pagamento.id.desc()],
        month_field="data_pagamento",
        validate=validar_positivo("valor_pago"),
        new_defaults=lambda: {"data_pagamento": date.today(),
                              "competencia": date.today().replace(day=1)},
    ),
    Resource(
        "despesas", Despesa, "Despesa", "Despesas",
        fields=[Field("data", "Data", "date"),
                Field("descricao", "Descrição", wide=True),
                Field("categoria", "Categoria (condomínio, reparo...)", required=False),
                Field("valor", "Valor (R$)", "money"),
                Field("predio_id", "Prédio (opcional)", "select", required=False,
                      choices=opcoes_predios)],
        columns=[("Data", lambda o: data_br(o.data)),
                 ("Descrição", lambda o: o.descricao),
                 ("Categoria", lambda o: o.categoria or ""),
                 ("Prédio", lambda o: o.predio.nome if o.predio else ""),
                 ("Valor", lambda o: brl(o.valor))],
        order=lambda: [Despesa.data.desc(), Despesa.id.desc()],
        month_field="data",
        validate=validar_positivo("valor"),
        new_defaults=lambda: {"data": date.today()},
    ),
]}
