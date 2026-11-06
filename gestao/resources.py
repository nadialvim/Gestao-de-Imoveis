from datetime import date

from .fields import Badge, Field, Resource
from .formatting import brl, data_br, mes_br
from .extensions import db
from .models import (Contrato, Despesa, Imovel, Inquilino, Pagamento, Predio,
                     Vaga)


# ---------- opções de selects ----------
def opcoes_predios():
    return [(p.id, p.nome) for p in Predio.query.order_by(Predio.nome).all()]


def opcoes_tipos_imovel():
    return Imovel.TIPOS


def _ordenar(itens):
    return sorted(itens, key=lambda x: x[1])


def opcoes_imoveis(obj=None):
    """Imóveis disponíveis (mais o do próprio contrato, ao editar)."""
    atual = getattr(obj, "imovel_id", None)
    return _ordenar((i.id, str(i)) for i in Imovel.query.all()
                    if i.disponivel or i.id == atual)


def opcoes_vagas(obj=None):
    atual = getattr(obj, "vaga_id", None)
    return _ordenar((v.id, str(v)) for v in Vaga.query.all()
                    if v.disponivel or v.id == atual)


def opcoes_inquilinos():
    return [(i.id, i.nome) for i in Inquilino.query.order_by(Inquilino.nome).all()]


def opcoes_contratos():
    return _ordenar((c.id, str(c) + ("" if c.ativo else " (encerrado)"))
                    for c in Contrato.query.all())


# ---------- situação ----------
def situacao(obj):
    return Badge("Disponível", "success") if obj.disponivel else Badge("Alugado", "warning")


def inquilino_atual(obj):
    c = obj.contrato_ativo
    return c.inquilino.nome if c else ""


# ---------- validações ----------
def validar_contrato(d, obj):
    erros = []
    if bool(d["imovel_id"]) == bool(d["vaga_id"]):
        erros.append("Informe o imóvel OU a vaga de garagem (apenas um).")
    if d["data_fim"] < d["data_inicio"]:
        erros.append("A data final não pode ser anterior à inicial.")
    if not 1 <= d["dia_vencimento"] <= 31:
        erros.append("Dia de vencimento deve estar entre 1 e 31.")
    ativo = obj is None or obj.ativo is not False  # contrato encerrado não bloqueia
    if not erros and ativo:
        q = Contrato.query.filter(Contrato.ativo.is_(True))
        if d["imovel_id"]:
            q = q.filter(Contrato.imovel_id == d["imovel_id"])
        else:
            q = q.filter(Contrato.vaga_id == d["vaga_id"])
        if obj is not None and obj.id is not None:
            q = q.filter(Contrato.id != obj.id)
        outro = q.first()
        if outro:
            erros.append(f"Já está alugado ({outro.inquilino.nome}). "
                         "Dê baixa no contrato atual antes de alugar novamente.")
    return erros


def validar_imovel(d, obj):
    erros = []
    if d["tipo"] == "casa":
        d["predio_id"] = None  # casa é independente
    elif not d["predio_id"]:
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


def criar_unidades(predio, dados):
    """Cria apartamentos/lojas informados em lote no cadastro/edição do prédio."""
    existentes = {(i.tipo, i.identificacao) for i in predio.imoveis}
    criados = {"apartamento": 0, "loja": 0}
    for tipo, campo in (("apartamento", "apartamentos_novos"), ("loja", "lojas_novas")):
        for ident in dados.get(campo) or []:
            if (tipo, ident) in existentes:
                continue
            db.session.add(Imovel(tipo=tipo, predio=predio, identificacao=ident))
            existentes.add((tipo, ident))
            criados[tipo] += 1
    if not any(criados.values()):
        return None
    db.session.commit()
    return (f"{criados['apartamento']} apartamento(s) e {criados['loja']} loja(s) "
            f"adicionados ao prédio {predio.nome}.")


def validar_positivo(campo):
    def _v(d, obj):
        return [] if d[campo] > 0 else ["O valor deve ser maior que zero."]
    return _v


# ---------- recursos ----------
RESOURCES = {r.slug: r for r in [
    Resource(
        "predios", Predio, "Prédio", "Prédios",
        fields=[Field("nome", "Nome"),
                Field("endereco", "Endereço", required=False, wide=True)],
        extra_fields=[
            Field("apartamentos_novos", "Apartamentos do prédio", "lista", required=False,
                  wide=True),
            Field("lojas_novas", "Lojas do prédio", "lista", required=False, wide=True)],
        columns=[("Nome", lambda o: o.nome), ("Endereço", lambda o: o.endereco or ""),
                 ("Apartamentos", lambda o: sum(i.tipo == "apartamento" for i in o.imoveis)),
                 ("Lojas", lambda o: sum(i.tipo == "loja" for i in o.imoveis))],
        order=lambda: [Predio.nome],
        after_save=criar_unidades,
    ),
    Resource(
        "imoveis", Imovel, "Imóvel", "Imóveis",
        fields=[Field("tipo", "Tipo", "choice", choices=opcoes_tipos_imovel,
                      default="apartamento"),
                Field("predio_id", "Prédio (não se aplica a casa)", "select",
                      required=False, choices=opcoes_predios),
                Field("identificacao", "Identificação (nº do apto, loja ou nome da casa)"),
                Field("valor_aluguel_padrao", "Aluguel padrão (R$)", "money",
                      required=False),
                Field("descricao", "Descrição", required=False, wide=True)],
        columns=[("Tipo", lambda o: o.tipo_nome),
                 ("Prédio", lambda o: o.predio.nome if o.predio else "—"),
                 ("Identificação", lambda o: o.identificacao),
                 ("Aluguel padrão", lambda o: brl(o.valor_aluguel_padrao)),
                 ("Situação", situacao),
                 ("Inquilino atual", inquilino_atual)],
        order=lambda: [Imovel.predio_id, Imovel.tipo, Imovel.identificacao],
        validate=validar_imovel,
        filters=[("tipo", "Tipo", Imovel.TIPOS)],
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
                 ("Aluguel padrão", lambda o: brl(o.valor_aluguel_padrao)),
                 ("Situação", situacao),
                 ("Inquilino atual", inquilino_atual)],
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
                Field("imovel_id", "Imóvel (apto, casa ou loja)", "select", required=False,
                      choices=opcoes_imoveis),
                Field("vaga_id", "Vaga de garagem", "select", required=False,
                      choices=opcoes_vagas),
                Field("data_inicio", "Início do contrato", "date"),
                Field("data_fim", "Fim do contrato", "date"),
                Field("valor_mensal", "Valor mensal (R$)", "money"),
                Field("dia_vencimento", "Dia de vencimento", "int", default=5)],
        columns=[("Inquilino", lambda o: o.inquilino.nome),
                 ("Imóvel", lambda o: str(o.imovel)),
                 ("Período", lambda o: f"{data_br(o.data_inicio)} a {data_br(o.data_fim)}"),
                 ("Valor mensal", lambda o: brl(o.valor_mensal)),
                 ("Situação", lambda o: Badge("Ativo", "success") if o.ativo
                  else Badge(f"Encerrado em {data_br(o.encerrado_em)}" if o.encerrado_em
                             else "Encerrado", "secondary"))],
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
                Field("observacao", "Observação", required=False, wide=True)],
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
