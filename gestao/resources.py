from datetime import date

from .fields import Field, Resource
from .formatting import brl, data_br, mes_br
from .models import (Apartamento, Contrato, Despesa, Inquilino, Pagamento,
                     Predio, Vaga)


# ---------- opções de selects ----------
def opcoes_predios():
    return [(p.id, p.nome) for p in Predio.query.order_by(Predio.nome).all()]


def opcoes_apartamentos():
    itens = Apartamento.query.all()
    return sorted(((a.id, str(a)) for a in itens), key=lambda x: x[1])


def opcoes_vagas():
    itens = Vaga.query.all()
    return sorted(((v.id, str(v)) for v in itens), key=lambda x: x[1])


def opcoes_inquilinos():
    return [(i.id, i.nome) for i in Inquilino.query.order_by(Inquilino.nome).all()]


def opcoes_contratos():
    itens = Contrato.query.filter_by(ativo=True).all()
    return sorted(((c.id, str(c)) for c in itens), key=lambda x: x[1])


# ---------- validações ----------
def validar_contrato(d, obj):
    erros = []
    if bool(d["apartamento_id"]) == bool(d["vaga_id"]):
        erros.append("Informe o apartamento OU a vaga de garagem (apenas um).")
    if d["data_fim"] < d["data_inicio"]:
        erros.append("A data final não pode ser anterior à inicial.")
    if not 1 <= d["dia_vencimento"] <= 31:
        erros.append("Dia de vencimento deve estar entre 1 e 31.")
    if not erros and d["ativo"]:
        q = Contrato.query.filter(
            Contrato.ativo.is_(True),
            Contrato.data_inicio <= d["data_fim"],
            Contrato.data_fim >= d["data_inicio"],
        )
        if d["apartamento_id"]:
            q = q.filter(Contrato.apartamento_id == d["apartamento_id"])
        else:
            q = q.filter(Contrato.vaga_id == d["vaga_id"])
        if obj is not None and obj.id is not None:
            q = q.filter(Contrato.id != obj.id)
        if q.first():
            erros.append("Já existe contrato ativo para este imóvel no período.")
    return erros


def validar_positivo(campo):
    def _v(d, obj):
        return [] if d[campo] > 0 else ["O valor deve ser maior que zero."]
    return _v


# ---------- recursos ----------
RESOURCES = {r.slug: r for r in [
    Resource(
        "predios", Predio, "Prédio", "Prédios",
        fields=[Field("nome", "Nome"),
                Field("endereco", "Endereço", required=False)],
        columns=[("Nome", lambda o: o.nome), ("Endereço", lambda o: o.endereco or "")],
        order=lambda: [Predio.nome],
    ),
    Resource(
        "apartamentos", Apartamento, "Apartamento", "Apartamentos",
        fields=[Field("predio_id", "Prédio", "select", choices=opcoes_predios),
                Field("numero", "Número / identificação"),
                Field("descricao", "Descrição", required=False),
                Field("valor_aluguel_padrao", "Aluguel padrão (R$)", "money",
                      required=False)],
        columns=[("Prédio", lambda o: o.predio.nome), ("Apto", lambda o: o.numero),
                 ("Descrição", lambda o: o.descricao or ""),
                 ("Aluguel padrão", lambda o: brl(o.valor_aluguel_padrao))],
        order=lambda: [Apartamento.predio_id, Apartamento.numero],
    ),
    Resource(
        "vagas", Vaga, "Vaga de garagem", "Vagas de garagem",
        fields=[Field("predio_id", "Prédio", "select", required=False,
                      choices=opcoes_predios),
                Field("identificacao", "Identificação (ex.: 12, G2-05)"),
                Field("valor_aluguel_padrao", "Aluguel padrão (R$)", "money",
                      required=False)],
        columns=[("Prédio", lambda o: o.predio.nome if o.predio else ""),
                 ("Vaga", lambda o: o.identificacao),
                 ("Aluguel padrão", lambda o: brl(o.valor_aluguel_padrao))],
        order=lambda: [Vaga.identificacao],
    ),
    Resource(
        "inquilinos", Inquilino, "Inquilino", "Inquilinos",
        fields=[Field("nome", "Nome"),
                Field("telefone", "Telefone", required=False),
                Field("email", "E-mail", required=False),
                Field("documento", "CPF / documento", required=False)],
        columns=[("Nome", lambda o: o.nome), ("Telefone", lambda o: o.telefone or ""),
                 ("E-mail", lambda o: o.email or "")],
        order=lambda: [Inquilino.nome],
    ),
    Resource(
        "contratos", Contrato, "Contrato", "Contratos",
        fields=[Field("inquilino_id", "Inquilino", "select", choices=opcoes_inquilinos),
                Field("apartamento_id", "Apartamento", "select", required=False,
                      choices=opcoes_apartamentos),
                Field("vaga_id", "Vaga de garagem", "select", required=False,
                      choices=opcoes_vagas),
                Field("data_inicio", "Início do contrato", "date"),
                Field("data_fim", "Fim do contrato", "date"),
                Field("valor_mensal", "Valor mensal (R$)", "money"),
                Field("dia_vencimento", "Dia de vencimento", "int", default=5),
                Field("ativo", "Contrato ativo", "bool", default=True)],
        columns=[("Inquilino", lambda o: o.inquilino.nome),
                 ("Imóvel", lambda o: str(o.imovel)),
                 ("Período", lambda o: f"{data_br(o.data_inicio)} a {data_br(o.data_fim)}"),
                 ("Valor mensal", lambda o: brl(o.valor_mensal)),
                 ("Ativo", lambda o: "Sim" if o.ativo else "Não")],
        order=lambda: [Contrato.ativo.desc(), Contrato.data_inicio.desc()],
        validate=validar_contrato,
    ),
    Resource(
        "pagamentos", Pagamento, "Pagamento", "Pagamentos recebidos",
        fields=[Field("contrato_id", "Contrato", "select", choices=opcoes_contratos),
                Field("competencia", "Mês de referência", "month"),
                Field("data_pagamento", "Data do pagamento", "date"),
                Field("valor_pago", "Valor recebido (R$)", "money"),
                Field("forma_pagamento", "Forma (Pix, dinheiro...)", required=False),
                Field("observacao", "Observação", required=False)],
        columns=[("Data", lambda o: data_br(o.data_pagamento)),
                 ("Referência", lambda o: mes_br(o.competencia)),
                 ("Contrato", lambda o: str(o.contrato)),
                 ("Valor", lambda o: brl(o.valor_pago)),
                 ("Forma", lambda o: o.forma_pagamento or "")],
        order=lambda: [Pagamento.data_pagamento.desc(), Pagamento.id.desc()],
        month_field="data_pagamento",
        validate=validar_positivo("valor_pago"),
        new_defaults=lambda: {"data_pagamento": date.today(),
                              "competencia": date.today().replace(day=1)},
    ),
    Resource(
        "despesas", Despesa, "Despesa", "Despesas",
        fields=[Field("data", "Data", "date"),
                Field("descricao", "Descrição"),
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
