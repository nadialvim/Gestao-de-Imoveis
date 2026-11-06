from datetime import date

from .fields import Badge, Field, Resource
from .formatting import brl, data_br, mes_br
from .extensions import db
from .models import (FORMAS_PAGAMENTO, RECEBEDORES, Contrato, Despesa, Imovel,
                     Inquilino, Pagamento, Predio, Vaga)


# ---------- opções de selects ----------
def opcoes_predios():
    return [(p.id, p.nome) for p in Predio.query.order_by(Predio.nome).all()]


def opcoes_tipos_imovel():
    return Imovel.TIPOS


def _com_valor(obj):
    valor = brl(obj.valor_aluguel_padrao) if obj.valor_aluguel_padrao else "sem valor definido"
    return f"{obj} — {valor}"


def _ordenar(itens):
    return sorted(itens, key=lambda x: x[1])


def opcoes_imoveis(obj=None):
    """Imóveis disponíveis (mais o do próprio contrato, ao editar)."""
    atual = getattr(obj, "imovel_id", None)
    return _ordenar((i.id, _com_valor(i)) for i in Imovel.query.all()
                    if i.disponivel or i.id == atual)


def opcoes_vagas(obj=None):
    atual = getattr(obj, "vaga_id", None)
    return _ordenar((v.id, _com_valor(v)) for v in Vaga.query.all()
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
def erros_alvo(imovel_id, vaga_id, excluir_contrato_id=None):
    """Valor definido e disponibilidade do imóvel/vaga que será alugado."""
    alvo = (db.session.get(Imovel, imovel_id) if imovel_id else db.session.get(Vaga, vaga_id))
    if alvo is None or not alvo.valor_aluguel_padrao:
        return ["Defina o valor do aluguel no cadastro do imóvel/vaga antes de alugar."]
    q = Contrato.query.filter(Contrato.ativo.is_(True))
    q = q.filter(Contrato.imovel_id == imovel_id if imovel_id else Contrato.vaga_id == vaga_id)
    if excluir_contrato_id is not None:
        q = q.filter(Contrato.id != excluir_contrato_id)
    outro = q.first()
    if outro:
        return [f"Já está alugado: {alvo} ({outro.inquilino.nome}). "
                "Dê baixa no contrato atual antes de alugar novamente."]
    return []


def validar_contrato(d, obj):
    erros = []
    if bool(d["imovel_id"]) == bool(d["vaga_id"]):
        erros.append("Informe o imóvel OU a vaga de garagem (apenas um).")
    if d["data_fim"] < d["data_inicio"]:
        erros.append("A data final não pode ser anterior à inicial.")
    if not 1 <= d["dia_vencimento"] <= 31:
        erros.append("Dia de vencimento deve estar entre 1 e 31.")
    if not d["inquilino_id"] and not d["novo_inquilino_nome"]:
        erros.append("Escolha um inquilino ou informe o nome de um novo.")
    ativo = obj is None or obj.ativo is not False  # contrato encerrado não bloqueia
    if not erros and ativo:
        erros.extend(erros_alvo(d["imovel_id"], d["vaga_id"],
                                obj.id if obj is not None else None))
    return erros


def validar_inquilino(d, obj):
    """Aluguel opcional no cadastro do inquilino (imóvel e/ou vaga + período)."""
    if not (d["aluguel_imovel_id"] or d["aluguel_vaga_id"]):
        return []
    erros = []
    if not d["aluguel_inicio"] or not d["aluguel_fim"]:
        erros.append("Informe o início e o fim do aluguel.")
    elif d["aluguel_fim"] < d["aluguel_inicio"]:
        erros.append("A data final não pode ser anterior à inicial.")
    if not d["aluguel_dia_vencimento"] or not 1 <= d["aluguel_dia_vencimento"] <= 31:
        erros.append("Dia de vencimento deve estar entre 1 e 31.")
    if not erros:
        for imovel_id, vaga_id in ((d["aluguel_imovel_id"], None), (None, d["aluguel_vaga_id"])):
            if imovel_id or vaga_id:
                erros.extend(erros_alvo(imovel_id, vaga_id))
    return erros


def criar_alugueis(obj, d):
    """Salva o inquilino e cria os contratos escolhidos na mesma transação."""
    if not (d["aluguel_imovel_id"] or d["aluguel_vaga_id"]):
        return
    db.session.add(obj)
    db.session.flush()
    for imovel_id, vaga_id in ((d["aluguel_imovel_id"], None), (None, d["aluguel_vaga_id"])):
        if not (imovel_id or vaga_id):
            continue
        alvo = db.session.get(Imovel, imovel_id) if imovel_id else db.session.get(Vaga, vaga_id)
        db.session.add(Contrato(
            inquilino_id=obj.id, imovel_id=imovel_id, vaga_id=vaga_id,
            data_inicio=d["aluguel_inicio"], data_fim=d["aluguel_fim"],
            dia_vencimento=d["aluguel_dia_vencimento"], valor_mensal=alvo.valor_aluguel_padrao,
            ativo=True))


def preparar_contrato(obj, d):
    """Cria o inquilino novo (se informado) e fixa o valor mensal pelo imóvel/vaga."""
    if not d["inquilino_id"]:
        inq = Inquilino(nome=d["novo_inquilino_nome"],
                        telefone=d["novo_inquilino_telefone"])
        db.session.add(inq)
        db.session.flush()
        obj.inquilino_id = inq.id
    if obj.ativo is not False:
        alvo = (db.session.get(Imovel, d["imovel_id"]) if d["imovel_id"]
                else db.session.get(Vaga, d["vaga_id"]))
        obj.valor_mensal = alvo.valor_aluguel_padrao


def propagar_valor(obj, dados):
    """Reajuste: o contrato ativo acompanha o valor do imóvel/vaga."""
    contrato = obj.contrato_ativo
    if contrato and obj.valor_aluguel_padrao and contrato.valor_mensal != obj.valor_aluguel_padrao:
        contrato.valor_mensal = obj.valor_aluguel_padrao
        db.session.commit()
        return f"Contrato ativo de {contrato.inquilino.nome} atualizado para o novo valor."
    return None


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
            db.session.add(Imovel(tipo=tipo, predio=predio, identificacao=ident,
                                  valor_aluguel_padrao=dados.get(
                                      "aluguel_apartamentos" if tipo == "apartamento"
                                      else "aluguel_lojas")))
            existentes.add((tipo, ident))
            criados[tipo] += 1
    if not any(criados.values()):
        return None
    db.session.commit()
    return (f"{criados['apartamento']} apartamento(s) e {criados['loja']} loja(s) "
            f"adicionados ao prédio {predio.nome}.")


def faltante_badge(pagamento):
    falta = pagamento.faltante
    return Badge(brl(falta), "danger") if falta > 0 else Badge("Quitado", "success")


def opcoes_formas():
    return [(f, f) for f in FORMAS_PAGAMENTO]


def opcoes_recebedores():
    return [(r, r) for r in RECEBEDORES]


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
            Field("aluguel_apartamentos", "Aluguel dos apartamentos novos (R$)", "money",
                  required=False),
            Field("lojas_novas", "Lojas do prédio", "lista", required=False, wide=True),
            Field("aluguel_lojas", "Aluguel das lojas novas (R$)", "money",
                  required=False)],
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
                Field("valor_aluguel_padrao", "Valor do aluguel (R$)", "money",
                      required=False),
                Field("descricao", "Descrição", required=False, wide=True)],
        columns=[("Tipo", lambda o: o.tipo_nome),
                 ("Prédio", lambda o: o.predio.nome if o.predio else "—"),
                 ("Identificação", lambda o: o.identificacao),
                 ("Aluguel", lambda o: brl(o.valor_aluguel_padrao)),
                 ("Situação", situacao),
                 ("Inquilino atual", inquilino_atual)],
        order=lambda: [Imovel.predio_id, Imovel.tipo, Imovel.identificacao],
        validate=validar_imovel,
        after_save=propagar_valor,
        filters=[("tipo", "Tipo", Imovel.TIPOS)],
    ),
    Resource(
        "vagas", Vaga, "Vaga de garagem", "Vagas de garagem",
        fields=[Field("predio_id", "Prédio", "select", required=False,
                      choices=opcoes_predios),
                Field("identificacao", "Identificação (ex.: 12, G2-05)"),
                Field("valor_aluguel_padrao", "Valor do aluguel (R$)", "money",
                      required=False)],
        columns=[("Prédio", lambda o: o.predio.nome if o.predio else ""),
                 ("Vaga", lambda o: o.identificacao),
                 ("Aluguel", lambda o: brl(o.valor_aluguel_padrao)),
                 ("Situação", situacao),
                 ("Inquilino atual", inquilino_atual)],
        order=lambda: [Vaga.identificacao],
        after_save=propagar_valor,
    ),
    Resource(
        "inquilinos", Inquilino, "Inquilino", "Inquilinos",
        fields=[Field("nome", "Nome"),
                Field("telefone", "Telefone", required=False),
                Field("email", "E-mail", required=False),
                Field("documento", "CPF / documento", required=False),
                Field("aluguel_imovel_id", "Imóvel (apto, casa ou loja)", "select",
                      required=False, choices=opcoes_imoveis, extra=True,
                      section="Aluguel (opcional) — vincule o imóvel já neste cadastro"),
                Field("aluguel_vaga_id", "Vaga de garagem", "select", required=False,
                      choices=opcoes_vagas, extra=True),
                Field("aluguel_inicio", "Início do aluguel", "date", required=False,
                      extra=True),
                Field("aluguel_fim", "Fim do aluguel", "date", required=False, extra=True),
                Field("aluguel_dia_vencimento", "Dia de vencimento", "int", required=False,
                      default=5, extra=True)],
        columns=[("Nome", lambda o: o.nome), ("Telefone", lambda o: o.telefone or ""),
                 ("E-mail", lambda o: o.email or ""),
                 ("Aluguéis ativos",
                  lambda o: ", ".join(str(c.imovel) for c in o.alugueis_ativos) or "—")],
        order=lambda: [Inquilino.nome],
        validate=validar_inquilino,
        before_save=criar_alugueis,
    ),
    Resource(
        "contratos", Contrato, "Contrato", "Contratos",
        fields=[Field("inquilino_id", "Inquilino", "select", required=False,
                      choices=opcoes_inquilinos),
                Field("novo_inquilino_nome", "Ou cadastre um novo inquilino: nome",
                      required=False, extra=True),
                Field("novo_inquilino_telefone", "Telefone do novo inquilino",
                      required=False, extra=True),
                Field("imovel_id", "Imóvel (apto, casa ou loja)", "select", required=False,
                      choices=opcoes_imoveis),
                Field("vaga_id", "Vaga de garagem", "select", required=False,
                      choices=opcoes_vagas),
                Field("data_inicio", "Início do contrato", "date"),
                Field("data_fim", "Fim do contrato", "date"),
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
        before_save=preparar_contrato,
    ),
    Resource(
        "pagamentos", Pagamento, "Pagamento", "Pagamentos recebidos",
        fields=[Field("contrato_id", "Contrato", "select", choices=opcoes_contratos),
                Field("competencia", "Mês de referência", "month"),
                Field("data_pagamento", "Data do pagamento", "date"),
                Field("valor_pago", "Valor recebido (R$)", "money"),
                Field("forma_pagamento", "Forma de pagamento", "choice",
                      choices=opcoes_formas),
                Field("recebido_por", "Recebido por", "choice", choices=opcoes_recebedores),
                Field("observacao", "Observação", required=False, wide=True)],
        columns=[("Data", lambda o: data_br(o.data_pagamento)),
                 ("Referência", lambda o: mes_br(o.competencia)),
                 ("Contrato", lambda o: str(o.contrato)),
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
