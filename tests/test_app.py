import re
from datetime import date
from decimal import Decimal

import pytest

from gestao import create_app
from gestao.extensions import db
from gestao.models import Contrato, Despesa, Imovel, Inquilino, Pagamento, Predio, Vaga
from gestao.services import relatorio


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True,
                      "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.create_all()
        db.session.execute(db.text("PRAGMA foreign_keys=ON"))  # Postgres aplica FKs
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def base(app):
    p = Predio(nome="Ed. Sol")
    a = Imovel(tipo="apartamento", predio=p, identificacao="101",
               valor_aluguel_padrao=Decimal("1000"))
    v = Vaga(predio=p, identificacao="G1", valor_aluguel_padrao=Decimal("250"))
    i = Inquilino(nome="Maria")
    db.session.add_all([p, a, v, i])
    db.session.commit()
    return p, a, v, i


def novo_contrato(i, a=None, v=None, inicio=date(2026, 1, 1), fim=date(2026, 12, 31)):
    c = Contrato(inquilino=i, imovel_rel=a, vaga=v, data_inicio=inicio, data_fim=fim,
                 valor_mensal=Decimal("1000"), dia_vencimento=5, ativo=True)
    db.session.add(c)
    db.session.commit()
    return c


def test_relatorio_saldo(base):
    _, a, _, i = base
    c = novo_contrato(i, a=a)
    db.session.add_all([
        Pagamento(contrato=c, competencia=date(2026, 3, 1),
                  data_pagamento=date(2026, 3, 5), valor_pago=Decimal("1000")),
        Pagamento(contrato=c, competencia=date(2026, 4, 1),
                  data_pagamento=date(2026, 4, 5), valor_pago=Decimal("1000")),
        Despesa(data=date(2026, 3, 10), descricao="Reparo", valor=Decimal("150.50")),
        Despesa(data=date(2026, 4, 10), descricao="Outro mês", valor=Decimal("99")),
    ])
    db.session.commit()
    d = relatorio.dados_mes(2026, 3)
    assert d["total_recebido"] == Decimal("1000")
    assert d["total_despesas"] == Decimal("150.50")
    assert d["saldo"] == Decimal("849.50")
    assert d["pendentes"] == []
    # março pago, abril em aberto para a competência de outro mês
    assert len(relatorio.dados_mes(2026, 5)["pendentes"]) == 1


def test_exportacoes(base):
    _, a, _, i = base
    novo_contrato(i, a=a)
    d = relatorio.dados_mes(2026, 3)
    assert relatorio.gerar_pdf(d).startswith(b"%PDF")
    assert relatorio.gerar_xlsx(d)[:2] == b"PK"


def test_contrato_sobreposto_rejeitado(client, base):
    _, a, _, i = base
    novo_contrato(i, a=a)
    r = client.post("/c/contratos/novo", data={
        "inquilino_id": i.id, "imovel_id": a.id, "data_inicio": "2026-06-01",
        "data_fim": "2027-06-01", "valor_mensal": "900", "dia_vencimento": "5",
        "ativo": "on"})
    assert r.status_code == 200  # volta ao formulário com erro
    assert "Já está alugado".encode() in r.data
    assert Contrato.query.count() == 1


def test_contrato_exige_um_imovel(client, base):
    _, a, v, i = base
    r = client.post("/c/contratos/novo", data={
        "inquilino_id": i.id, "imovel_id": a.id, "vaga_id": v.id,
        "data_inicio": "2026-01-01", "data_fim": "2026-12-31",
        "valor_mensal": "900", "dia_vencimento": "5"})
    assert "apenas um".encode() in r.data
    assert Contrato.query.count() == 0


def test_contrato_vaga_ok_e_pagamento(client, base):
    _, _, v, i = base
    r = client.post("/c/contratos/novo", data={
        "inquilino_id": i.id, "vaga_id": v.id, "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31", "valor_mensal": "250,00", "dia_vencimento": "10",
        "ativo": "on"})
    assert r.status_code == 302
    c = Contrato.query.one()
    r = client.post("/c/pagamentos/novo", data={
        "contrato_id": c.id, "competencia": "2026-02", "data_pagamento": "2026-02-08",
        "valor_pago": "250.00", "forma_pagamento": "Pix", "recebido_por": "Sergio"})
    assert r.status_code == 302
    pg = Pagamento.query.one()
    assert pg.competencia == date(2026, 2, 1) and pg.recebido_por == "Sergio"


def test_paginas_e_exportacao_http(client, base):
    for url in ["/", "/relatorios/?mes=2026-03", "/c/predios/", "/c/despesas/?mes=2026-03",
                "/c/contratos/novo", "/c/pagamentos/novo"]:
        assert client.get(url).status_code == 200, url
    r = client.get("/relatorios/exportar.pdf?mes=2026-03")
    assert r.mimetype == "application/pdf"
    assert client.get("/relatorios/exportar.xlsx?mes=2026-03").status_code == 200


def test_login_obrigatorio():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    r = app.test_client().get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_excluir_com_vinculo(client, base):
    p, a, _, _ = base
    r = client.post(f"/c/predios/{p.id}/excluir")
    assert r.status_code == 302
    assert Predio.query.count() == 1


def test_normalizar_db_url():
    from gestao import normalizar_db_url

    u = "postgres://u:p@h:6543/postgres?sslmode=require&supa=base-pooler.x"
    assert normalizar_db_url(u) == "postgresql://u:p@h:6543/postgres?sslmode=require"
    assert normalizar_db_url("sqlite:///local.db") == "sqlite:///local.db"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.mark.parametrize("status,body,esperado", [
    (400, {"error_code": "email_not_confirmed", "msg": "Email not confirmed"}, "não confirmado"),
    (401, {"message": "Invalid API key"}, "Chave do Supabase inválida"),
    (400, {"error_code": "invalid_credentials", "msg": "Invalid login credentials"},
     "E-mail ou senha inválidos"),
    (404, {}, "SUPABASE_URL incorreta"),
])
def test_login_mensagens(monkeypatch, status, body, esperado):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                      "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "k"})
    monkeypatch.setattr("gestao.auth.requests.post", lambda *a, **k: _Resp(status, body))
    r = app.test_client().post("/login", data={"email": "a@b.c", "senha": "x"})
    assert esperado in r.get_data(as_text=True)


def test_login_ok(monkeypatch):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                      "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "k"})
    monkeypatch.setattr("gestao.auth.requests.post",
                        lambda *a, **k: _Resp(200, {"user": {"email": "a@b.c"}}))
    r = app.test_client().post("/login", data={"email": "a@b.c", "senha": "x"})
    assert r.status_code == 302


def test_vercel_exige_database_url(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app({"SECRET_KEY": "abc"})


def test_vercel_rejeita_conexao_direta_supabase(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:x@db.abc.supabase.co:6543/postgres")
    with pytest.raises(RuntimeError, match="Transaction pooler"):
        create_app({"SECRET_KEY": "abc"})


def test_serie_meses(base):
    _, a, _, i = base
    c = novo_contrato(i, a=a)
    db.session.add_all([
        Pagamento(contrato=c, competencia=date(2026, 1, 1),
                  data_pagamento=date(2026, 1, 5), valor_pago=Decimal("1000")),
        Despesa(data=date(2025, 12, 10), descricao="x", valor=Decimal("40")),
    ])
    db.session.commit()
    s = relatorio.serie_meses(2026, 1, n=3)
    assert [x["rotulo"] for x in s] == ["novembro/2025", "dezembro/2025", "janeiro/2026"]
    assert [x["recebido"] for x in s] == [0.0, 0.0, 1000.0]
    assert [x["despesas"] for x in s] == [0.0, 40.0, 0.0]


def test_layout_menu_lateral_e_busca(client, base):
    html = client.get("/").get_data(as_text=True)
    assert 'class="sidebar"' in html and "grafico-meses" in html
    p, *_ = base
    html = client.get("/c/predios/").get_data(as_text=True)
    assert 'id="busca"' in html and "Ed. Sol" in html
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


# ---------- imóveis, disponibilidade e baixa ----------
def test_parse_lista():
    from gestao.services.unidades import parse_lista

    assert parse_lista("101, 102\n103;102") == ["101", "102", "103"]
    assert parse_lista("101-104") == ["101", "102", "103", "104"]
    assert parse_lista("G2-05, 7") == ["G2-05", "7"]
    assert parse_lista("") == []
    with pytest.raises(ValueError):
        parse_lista("110-101")
    with pytest.raises(ValueError):
        parse_lista("1-9999")


def test_casa_sem_predio_e_apto_exige_predio(client, base):
    p, *_ = base
    r = client.post("/c/imoveis/novo", data={"tipo": "casa", "predio_id": p.id,
                                             "identificacao": "Rua Sol, 10"})
    assert r.status_code == 302
    casa = Imovel.query.filter_by(tipo="casa").one()
    assert casa.predio_id is None and str(casa) == "Casa Rua Sol, 10"
    r = client.post("/c/imoveis/novo", data={"tipo": "apartamento", "identificacao": "900"})
    assert "vinculados a um prédio".encode() in r.data
    r = client.post("/c/imoveis/novo", data={"tipo": "loja", "predio_id": p.id,
                                             "identificacao": "L1"})
    assert r.status_code == 302
    r = client.post("/c/imoveis/novo", data={"tipo": "loja", "predio_id": p.id,
                                             "identificacao": "L1"})
    assert "Já existe".encode() in r.data


def test_predio_cadastra_unidades_em_lote(client):
    r = client.post("/c/predios/novo", data={
        "nome": "Ed. Lua", "apartamentos_novos": "101-103, 201", "lojas_novas": "A, B"})
    assert r.status_code == 302
    predio = Predio.query.filter_by(nome="Ed. Lua").one()
    assert sorted(i.identificacao for i in predio.imoveis if i.tipo == "apartamento") == \
        ["101", "102", "103", "201"]
    assert sorted(i.identificacao for i in predio.imoveis if i.tipo == "loja") == ["A", "B"]
    # edição adiciona novos sem duplicar
    client.post(f"/c/predios/{predio.id}/editar", data={
        "nome": "Ed. Lua", "apartamentos_novos": "103, 202", "lojas_novas": ""})
    assert Imovel.query.filter_by(predio_id=predio.id, tipo="apartamento").count() == 5
    assert "Unidades deste prédio".encode() in client.get(
        f"/c/predios/{predio.id}/editar").data


def _contrato_form(i, **extra):
    d = {"inquilino_id": i.id, "data_inicio": "2026-01-01", "data_fim": "2026-12-31",
         "valor_mensal": "1000", "dia_vencimento": "5"}
    d.update(extra)
    return d


def test_alugado_nao_pode_alugar_ate_dar_baixa(client, base):
    _, a, _, i = base
    outro = Inquilino(nome="Joao")
    db.session.add(outro)
    db.session.commit()
    assert a.disponivel
    assert client.post("/c/contratos/novo", data=_contrato_form(i, imovel_id=a.id)).status_code == 302
    db.session.refresh(a)
    assert not a.disponivel
    # alugado não aparece nas opções e é recusado se forçado
    assert "Apto 101" not in client.get("/c/contratos/novo").get_data(as_text=True)
    r = client.post("/c/contratos/novo", data=_contrato_form(outro, imovel_id=a.id))
    assert "Já está alugado".encode() in r.data
    assert Contrato.query.count() == 1
    # dar baixa libera o imóvel
    c = Contrato.query.one()
    r = client.post(f"/c/contratos/{c.id}/baixa", data={"data_devolucao": "2026-05-20"})
    assert r.status_code == 302
    db.session.refresh(c)
    assert c.ativo is False and c.encerrado_em == date(2026, 5, 20)
    db.session.refresh(a)
    assert a.disponivel
    assert "Apto 101" in client.get("/c/contratos/novo").get_data(as_text=True)
    r = client.post("/c/contratos/novo", data=_contrato_form(outro, imovel_id=a.id))
    assert r.status_code == 302
    assert Contrato.query.filter_by(ativo=True).count() == 1


def test_baixa_valida_data_e_vaga(client, base):
    _, _, v, i = base
    client.post("/c/contratos/novo", data=_contrato_form(i, vaga_id=v.id))
    c = Contrato.query.one()
    client.post(f"/c/contratos/{c.id}/baixa", data={"data_devolucao": "2025-01-01"})
    db.session.refresh(c)
    assert c.ativo is True  # data anterior ao início é recusada
    assert not db.session.get(Vaga, v.id).disponivel
    client.post(f"/c/contratos/{c.id}/baixa", data={"data_devolucao": "2026-03-01"})
    db.session.refresh(c)
    assert c.ativo is False and db.session.get(Vaga, v.id).disponivel


def test_pendencia_considera_baixa(base):
    _, a, _, i = base
    c = novo_contrato(i, a=a)
    c.ativo, c.encerrado_em = False, date(2026, 3, 10)
    db.session.commit()
    assert len(relatorio.dados_mes(2026, 3)["pendentes"]) == 1   # mês da baixa ainda cobra
    assert relatorio.dados_mes(2026, 4)["pendentes"] == []       # depois da baixa, não


def test_filtro_por_tipo_na_lista(client, base):
    p, *_ = base
    db.session.add(Imovel(tipo="casa", identificacao="Casa Azul"))
    db.session.commit()
    html = client.get("/c/imoveis/?tipo=casa").get_data(as_text=True)
    assert "Casa Azul" in html and "Apto" not in html.split("<tbody>")[1]


# ---------- fluxo simplificado de aluguel ----------
def test_contrato_herda_valor_do_imovel(client, base):
    _, a, _, i = base
    r = client.post("/c/contratos/novo", data=_contrato_form(i, imovel_id=a.id,
                                                              valor_mensal="1"))
    assert r.status_code == 302
    assert Contrato.query.one().valor_mensal == Decimal("1000")  # campo valor é ignorado


def test_imovel_sem_valor_nao_pode_ser_alugado(client, base):
    p, a, _, i = base
    a.valor_aluguel_padrao = None
    db.session.commit()
    r = client.post("/c/contratos/novo", data=_contrato_form(i, imovel_id=a.id))
    assert "Defina o valor do aluguel".encode() in r.data
    assert Contrato.query.count() == 0


def test_reajuste_do_imovel_atualiza_contrato_ativo_e_nao_encerrados(client, base):
    p, a, _, i = base
    client.post("/c/contratos/novo", data=_contrato_form(i, imovel_id=a.id))
    c = Contrato.query.one()
    client.post(f"/c/imoveis/{a.id}/editar", data={
        "tipo": "apartamento", "predio_id": p.id, "identificacao": "101",
        "valor_aluguel_padrao": "1200"})
    db.session.refresh(c)
    assert c.valor_mensal == Decimal("1200")
    client.post(f"/c/contratos/{c.id}/baixa", data={"data_devolucao": "2026-06-01"})
    client.post(f"/c/imoveis/{a.id}/editar", data={
        "tipo": "apartamento", "predio_id": p.id, "identificacao": "101",
        "valor_aluguel_padrao": "1500"})
    db.session.refresh(c)
    assert c.valor_mensal == Decimal("1200")  # histórico preservado


def test_alugar_com_inquilino_novo_na_mesma_tela(client, base):
    _, a, _, _ = base
    r = client.post("/c/contratos/novo", data={
        "novo_inquilino_nome": "Carlos Lima", "novo_inquilino_telefone": "9999",
        "imovel_id": a.id, "data_inicio": "2026-02-01", "data_fim": "2027-01-31",
        "dia_vencimento": "10"})
    assert r.status_code == 302
    c = Contrato.query.one()
    assert c.inquilino.nome == "Carlos Lima" and c.inquilino.telefone == "9999"
    r = client.post("/c/contratos/novo", data={
        "imovel_id": a.id, "data_inicio": "2026-02-01", "data_fim": "2027-01-31",
        "dia_vencimento": "10"})
    assert "Escolha um inquilino".encode() in r.data
    assert Inquilino.query.filter_by(nome="Carlos Lima").count() == 1


def test_botao_alugar_preenche_formulario_e_baixa_volta_para_imoveis(client, base):
    _, a, _, i = base
    html = client.get("/c/imoveis/").get_data(as_text=True)
    assert f"/c/contratos/novo?imovel_id={a.id}" in html
    form = client.get(f"/c/contratos/novo?imovel_id={a.id}").get_data(as_text=True)
    assert f'<option value="{a.id}" selected>' in form
    client.post("/c/contratos/novo", data=_contrato_form(i, imovel_id=a.id))
    c = Contrato.query.one()
    html = client.get("/c/imoveis/").get_data(as_text=True)
    assert "Dar baixa" in html and "Alugar" not in html.split("<tbody>")[1]
    r = client.post(f"/c/contratos/{c.id}/baixa",
                    data={"data_devolucao": "2026-04-01", "voltar": "imoveis"})
    assert r.headers["Location"].endswith("/c/imoveis/")


def test_apartamentos_antigo_redireciona(client):
    r = client.get("/c/apartamentos/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/c/imoveis/")


def test_predio_em_lote_com_aluguel(client):
    client.post("/c/predios/novo", data={
        "nome": "Ed. Mar", "apartamentos_novos": "11, 12", "aluguel_apartamentos": "900",
        "lojas_novas": "L1", "aluguel_lojas": "2500"})
    valores = {(i.tipo, i.identificacao): i.valor_aluguel_padrao for i in Imovel.query.all()
               if i.predio and i.predio.nome == "Ed. Mar"}
    assert valores == {("apartamento", "11"): Decimal("900"),
                       ("apartamento", "12"): Decimal("900"),
                       ("loja", "L1"): Decimal("2500")}


# ---------- pagamentos: sugestão, combos, faltante, débitos ----------
def _pagto(contrato_id, valor, data="2026-03-05", comp="2026-03", forma="Pix", quem="Fagner"):
    return {"contrato_id": contrato_id, "competencia": comp, "data_pagamento": data,
            "valor_pago": valor, "forma_pagamento": forma, "recebido_por": quem}


def test_forma_e_recebedor_sao_combos_obrigatorios(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a=a)
    html = client.get("/c/pagamentos/novo").get_data(as_text=True)
    for txt in ("Pix", "Dinheiro", "Transferência bancária (TED/DOC)", "Sergio", "Fagner",
                'id="dica-valor"', "data-sugestao"):
        assert txt in html
    r = client.post("/c/pagamentos/novo", data=_pagto(c.id, "1000", forma="Cheque"))
    assert "opção inválida" in r.get_data(as_text=True)
    r = client.post("/c/pagamentos/novo", data=_pagto(c.id, "1000", quem="Outro"))
    assert "opção inválida" in r.get_data(as_text=True)
    assert Pagamento.query.count() == 0


def test_sugestao_de_valor_e_faltante_abatido(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a=a)   # valor_mensal 1000
    j = client.get(f"/c/pagamentos/sugestao?contrato_id={c.id}&competencia=2026-03").get_json()
    assert j == {"valor_mensal": "1000.00", "recebido": "0.00", "falta": "1000.00"}
    client.post("/c/pagamentos/novo", data=_pagto(c.id, "600"))
    j = client.get(f"/c/pagamentos/sugestao?contrato_id={c.id}&competencia=2026-03").get_json()
    assert j["recebido"] == "600.00" and j["falta"] == "400.00"
    client.post("/c/pagamentos/novo", data=_pagto(c.id, "400", data="2026-03-20"))
    p1, p2 = Pagamento.query.order_by(Pagamento.id).all()
    assert p1.faltante == Decimal("400") and p2.faltante == Decimal("0")
    html = client.get("/c/pagamentos/?mes=2026-03").get_data(as_text=True)
    assert "Recebido por" in html and "Faltante" in html and "Quitado" in html
    assert "R$ 400,00" in html
    assert client.get("/c/pagamentos/sugestao?contrato_id=999").status_code == 404


def test_debitos_por_inquilino(base):
    _, a, v, i = base
    c = novo_contrato(i, a=a, inicio=date(2026, 1, 1), fim=date(2026, 12, 31))  # R$ 1000, venc. dia 5
    db.session.add(Pagamento(contrato=c, competencia=date(2026, 1, 1),
                             data_pagamento=date(2026, 1, 5), valor_pago=Decimal("1000")))
    db.session.add(Pagamento(contrato=c, competencia=date(2026, 2, 1),
                             data_pagamento=date(2026, 2, 5), valor_pago=Decimal("600")))
    db.session.commit()
    d = relatorio.debitos(hoje=date(2026, 4, 10))
    assert len(d["inquilinos"]) == 1
    item = d["inquilinos"][0]
    # fev: faltam 400; mar e abr (venc. dia 5 já passou): 1000 cada
    assert [m["competencia"] for m in item["meses"]] == [date(2026, 2, 1), date(2026, 3, 1),
                                                          date(2026, 4, 1)]
    assert item["total"] == Decimal("2400") and d["total"] == Decimal("2400")
    assert item["meses"][0]["dias_atraso"] == (date(2026, 4, 10) - date(2026, 2, 5)).days
    # antes do vencimento do mês corrente não conta
    assert relatorio.debitos(hoje=date(2026, 4, 5))["total"] == Decimal("1400")


def test_debitos_contrato_encerrado_e_quitado(base):
    _, a, _, i = base
    c = novo_contrato(i, a=a, inicio=date(2026, 1, 1), fim=date(2026, 12, 31))
    for m in (1, 2):
        db.session.add(Pagamento(contrato=c, competencia=date(2026, m, 1),
                                 data_pagamento=date(2026, m, 5), valor_pago=Decimal("1000")))
    c.ativo, c.encerrado_em = False, date(2026, 2, 28)
    db.session.commit()
    assert relatorio.debitos(hoje=date(2026, 9, 1))["inquilinos"] == []  # nada após a baixa


def test_pagina_debitos_e_exportacoes_com_recebido_por(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a=a, inicio=date(2025, 1, 1), fim=date(2025, 12, 31))
    db.session.add(Pagamento(contrato=c, competencia=date(2026, 3, 1),
                             data_pagamento=date(2026, 3, 5), valor_pago=Decimal("1000"),
                             forma_pagamento="Pix", recebido_por="Sergio"))
    db.session.commit()
    html = client.get("/relatorios/debitos").get_data(as_text=True)
    assert "Inquilinos em débito" in html and "Maria" in html
    assert "Sergio" in client.get("/relatorios/?mes=2026-03").get_data(as_text=True)
    d = relatorio.dados_mes(2026, 3)
    assert relatorio.gerar_pdf(d).startswith(b"%PDF") and relatorio.gerar_xlsx(d)[:2] == b"PK"


# ---------- inquilino já com o aluguel ----------
def _inq_form(imovel=None, vaga=None, **extra):
    d = {"nome": "Paulo Dias", "telefone": "1199", "aluguel_dia_vencimento": "5"}
    if imovel:
        d["aluguel_imovel_id"] = imovel.id
    if vaga:
        d["aluguel_vaga_id"] = vaga.id
    if imovel or vaga:
        d.update({"aluguel_inicio": "2026-03-01", "aluguel_fim": "2027-02-28"})
    d.update(extra)
    return d


def test_inquilino_com_imovel_cria_contrato(client, base):
    _, a, v, _ = base
    r = client.post("/c/inquilinos/novo", data=_inq_form(imovel=a))
    assert r.status_code == 302
    inq = Inquilino.query.filter_by(nome="Paulo Dias").one()
    c = Contrato.query.filter_by(inquilino_id=inq.id).one()
    assert c.imovel_id == a.id and c.valor_mensal == Decimal("1000") and c.ativo
    assert c.data_inicio == date(2026, 3, 1) and c.dia_vencimento == 5
    db.session.refresh(a)
    assert not a.disponivel
    html = client.get("/c/inquilinos/").get_data(as_text=True)
    assert "Aluguéis ativos" in html and "Apto 101" in html
    assert "Aluguéis deste inquilino" in client.get(f"/c/inquilinos/{inq.id}/editar").get_data(as_text=True)


def test_inquilino_com_imovel_e_vaga_cria_dois_contratos(client, base):
    _, a, v, _ = base
    client.post("/c/inquilinos/novo", data=_inq_form(imovel=a, vaga=v))
    assert Contrato.query.count() == 2
    assert {(c.imovel_id, c.vaga_id) for c in Contrato.query.all()} == {(a.id, None), (None, v.id)}


def test_inquilino_aluguel_invalido_nao_salva_nada(client, base):
    _, a, _, i = base
    r = client.post("/c/inquilinos/novo", data=_inq_form(imovel=a, aluguel_inicio="",
                                                         aluguel_fim=""))
    assert "Informe o início e o fim".encode() in r.data
    assert Inquilino.query.filter_by(nome="Paulo Dias").count() == 0
    novo_contrato(i, a=a)  # imóvel já alugado
    r = client.post("/c/inquilinos/novo", data=_inq_form(imovel=a))
    assert "Já está alugado".encode() in r.data
    assert Inquilino.query.filter_by(nome="Paulo Dias").count() == 0
    assert Contrato.query.count() == 1


def test_inquilino_sem_aluguel_e_edicao_adiciona_aluguel(client, base):
    _, a, _, _ = base
    assert client.post("/c/inquilinos/novo", data=_inq_form()).status_code == 302
    inq = Inquilino.query.filter_by(nome="Paulo Dias").one()
    assert Contrato.query.count() == 0
    assert client.get(f"/c/inquilinos/novo?aluguel_imovel_id={a.id}").status_code == 200
    html = client.get(f"/c/inquilinos/{inq.id}/editar").get_data(as_text=True)
    assert re.search(r'name="aluguel_dia_vencimento"\s+value="5"', html)
    r = client.post(f"/c/inquilinos/{inq.id}/editar", data=_inq_form(imovel=a))
    assert r.status_code == 302
    assert Contrato.query.filter_by(inquilino_id=inq.id).count() == 1
