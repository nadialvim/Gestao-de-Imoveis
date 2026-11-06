import re
from datetime import date
from decimal import Decimal

import pytest

from gestao import create_app, normalizar_db_url
from gestao.extensions import db
from gestao.models import Contrato, Despesa, Imovel, Inquilino, Pagamento, Predio
from gestao.services import alugueis, relatorio
from gestao.services.unidades import parse_lista


# ---------------------------------------------------------------- fixtures
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
    v = Imovel(tipo="vaga", predio=p, identificacao="G1", valor_aluguel_padrao=Decimal("250"))
    i = Inquilino(nome="Maria")
    db.session.add_all([p, a, v, i])
    db.session.commit()
    return p, a, v, i


def novo_contrato(i, a, inicio=date(2026, 1, 1), fim=date(2026, 12, 31), valor="1000"):
    c = Contrato(inquilino=i, imovel=a, data_inicio=inicio, data_fim=fim,
                 valor_mensal=Decimal(valor), dia_vencimento=5, ativo=True)
    db.session.add(c)
    db.session.commit()
    return c


def form_aluguel(imoveis, inquilino=None, nome=None, **extra):
    d = {"aluguel_imoveis": [m.id for m in imoveis], "aluguel_inicio": "2026-03-01",
         "aluguel_fim": "2027-02-28", "aluguel_dia_vencimento": "5"}
    if inquilino:
        d["inquilino_id"] = inquilino.id
    if nome:
        d["novo_inquilino_nome"] = nome
    d.update(extra)
    return d


# ---------------------------------------------------------------- infraestrutura
def test_normalizar_db_url():
    u = "postgres://u:p@h:6543/postgres?sslmode=require&supa=base-pooler.x"
    assert normalizar_db_url(u) == "postgresql://u:p@h:6543/postgres?sslmode=require"
    assert normalizar_db_url("sqlite:///local.db") == "sqlite:///local.db"


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


def test_login_obrigatorio():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    r = app.test_client().get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


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


# ---------------------------------------------------------------- imóveis e prédios
def test_parse_lista():
    assert parse_lista("101, 102\n103;102") == ["101", "102", "103"]
    assert parse_lista("101-104") == ["101", "102", "103", "104"]
    assert parse_lista("G2-05, 7") == ["G2-05", "7"]
    assert parse_lista("") == []
    with pytest.raises(ValueError):
        parse_lista("110-101")
    with pytest.raises(ValueError):
        parse_lista("1-9999")


def test_regras_dos_tipos_de_imovel(client, base):
    p, *_ = base
    # casa é independente: o prédio informado é ignorado
    r = client.post("/c/imoveis/novo", data={"tipo": "casa", "predio_id": p.id,
                                             "identificacao": "Rua Sol, 10"})
    assert r.status_code == 302
    casa = Imovel.query.filter_by(tipo="casa").one()
    assert casa.predio_id is None and str(casa) == "Casa Rua Sol, 10"
    # apartamento e loja exigem prédio
    r = client.post("/c/imoveis/novo", data={"tipo": "apartamento", "identificacao": "900"})
    assert "vinculados a um prédio".encode() in r.data
    # vaga pode ser avulsa ou de um prédio
    for pid in ("", p.id):
        assert client.post("/c/imoveis/novo", data={
            "tipo": "vaga", "predio_id": pid, "identificacao": f"V{pid or 'x'}"}).status_code == 302
    # duplicado é recusado
    client.post("/c/imoveis/novo", data={"tipo": "loja", "predio_id": p.id, "identificacao": "L1"})
    r = client.post("/c/imoveis/novo", data={"tipo": "loja", "predio_id": p.id,
                                             "identificacao": "L1"})
    assert "Já existe".encode() in r.data


def test_predio_cadastra_unidades_em_lote_com_aluguel(client):
    r = client.post("/c/predios/novo", data={
        "nome": "Ed. Lua", "apartamentos_novos": "101-103, 201", "aluguel_apartamentos": "900",
        "lojas_novas": "A, B", "aluguel_lojas": "2500", "vagas_novas": "G1", "aluguel_vagas": "200"})
    assert r.status_code == 302 and "/predios/" in r.headers["Location"]  # vai para a ficha
    predio = Predio.query.filter_by(nome="Ed. Lua").one()
    unidades = {(i.tipo, i.identificacao): i.valor_aluguel_padrao for i in predio.imoveis}
    assert unidades == {("apartamento", "101"): Decimal("900"), ("apartamento", "102"): Decimal("900"),
                        ("apartamento", "103"): Decimal("900"), ("apartamento", "201"): Decimal("900"),
                        ("loja", "A"): Decimal("2500"), ("loja", "B"): Decimal("2500"),
                        ("vaga", "G1"): Decimal("200")}
    # editar adiciona novos sem duplicar
    client.post(f"/c/predios/{predio.id}/editar", data={
        "nome": "Ed. Lua", "apartamentos_novos": "103, 202"})
    assert Imovel.query.filter_by(predio_id=predio.id, tipo="apartamento").count() == 5


def test_reajuste_do_imovel_atualiza_aluguel_ativo_e_nao_encerrados(client, base):
    p, a, _, i = base
    c = novo_contrato(i, a)
    dados = {"tipo": "apartamento", "predio_id": p.id, "identificacao": "101"}
    client.post(f"/c/imoveis/{a.id}/editar", data={**dados, "valor_aluguel_padrao": "1200"})
    db.session.refresh(c)
    assert c.valor_mensal == Decimal("1200")
    client.post(f"/alugueis/{c.id}/baixa", data={"data_devolucao": "2026-06-01"})
    client.post(f"/c/imoveis/{a.id}/editar", data={**dados, "valor_aluguel_padrao": "1500"})
    db.session.refresh(c)
    assert c.valor_mensal == Decimal("1200")  # histórico preservado


def test_filtros_da_lista_de_imoveis(client, base):
    p, a, v, i = base
    db.session.add(Imovel(tipo="casa", identificacao="Casa Azul"))
    novo_contrato(i, a)
    db.session.commit()

    def tbody(url):
        return client.get(url).get_data(as_text=True).split("<tbody>")[1]

    assert "Casa Azul" in tbody("/c/imoveis/?tipo=casa") and "Apto 101" not in tbody("/c/imoveis/?tipo=casa")
    assert "Vaga G1" in tbody("/c/imoveis/?tipo=vaga")
    assert "Apto 101" in tbody("/c/imoveis/?situacao=alugado")
    assert "Apto 101" not in tbody("/c/imoveis/?situacao=disponivel")


# ---------------------------------------------------------------- novo aluguel
def test_novo_aluguel_com_inquilino_existente_herda_valor(client, base):
    _, a, _, i = base
    r = client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i, valor_mensal="1"))
    assert r.status_code == 302 and f"/inquilinos/{i.id}" in r.headers["Location"]
    c = Contrato.query.one()
    assert c.valor_mensal == Decimal("1000") and c.ativo and c.inquilino_id == i.id
    db.session.refresh(a)
    assert not a.disponivel


def test_novo_aluguel_com_inquilino_novo_e_dois_imoveis(client, base):
    _, a, v, _ = base
    r = client.post("/c/alugueis/novo",
                    data=form_aluguel([a, v], nome="Carlos Lima", novo_inquilino_telefone="999"))
    assert r.status_code == 302
    inq = Inquilino.query.filter_by(nome="Carlos Lima").one()
    assert inq.telefone == "999"
    assert {c.imovel_id for c in Contrato.query.filter_by(inquilino_id=inq.id)} == {a.id, v.id}


def test_novo_aluguel_validacoes(client, base):
    _, a, _, i = base
    r = client.post("/c/alugueis/novo", data=form_aluguel([a]))
    assert "Escolha um inquilino".encode() in r.data
    r = client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i, aluguel_inicio=""))
    assert "Início do aluguel: campo obrigatório".encode() in r.data
    r = client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i, aluguel_fim="2026-01-01"))
    assert "anterior à inicial".encode() in r.data
    a.valor_aluguel_padrao = None
    db.session.commit()
    r = client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i))
    assert "Defina o valor".encode() in r.data
    assert Contrato.query.count() == 0 and Inquilino.query.count() == 1


def test_alugado_nao_aparece_nem_pode_ser_alugado_ate_a_baixa(client, base):
    _, a, _, i = base
    outro = Inquilino(nome="Joao")
    db.session.add(outro)
    db.session.commit()
    client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i))
    assert "Apto 101" not in client.get("/c/alugueis/novo").get_data(as_text=True)
    r = client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=outro))
    assert "Já está alugado".encode() in r.data and Contrato.query.count() == 1
    c = Contrato.query.one()
    r = client.post(f"/alugueis/{c.id}/baixa", data={"data_devolucao": "2026-05-20"})
    assert r.status_code == 302
    db.session.refresh(c)
    assert c.ativo is False and c.encerrado_em == date(2026, 5, 20)
    assert "Apto 101" in client.get("/c/alugueis/novo").get_data(as_text=True)
    assert client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=outro)).status_code == 302


def test_baixa_valida_data_e_destino(client, base):
    _, a, _, i = base
    client.post("/c/alugueis/novo", data=form_aluguel([a], inquilino=i))
    c = Contrato.query.one()
    client.post(f"/alugueis/{c.id}/baixa", data={"data_devolucao": "2025-01-01"})
    db.session.refresh(c)
    assert c.ativo is True  # devolução antes do início é recusada
    r = client.post(f"/alugueis/{c.id}/baixa",
                    data={"data_devolucao": "2026-04-01", "next": f"/imoveis/{a.id}"})
    assert r.headers["Location"].endswith(f"/imoveis/{a.id}")
    r = client.post(f"/alugueis/{c.id}/baixa",
                    data={"data_devolucao": "2026-04-02", "next": "https://evil.example"})
    assert f"/inquilinos/{i.id}" in r.headers["Location"]  # destino externo é ignorado


def test_servico_alugueis_baixa_direta(base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    assert alugueis.dar_baixa(c, None)
    assert alugueis.dar_baixa(c, date(2025, 1, 1))
    assert alugueis.dar_baixa(c, date(2026, 2, 1)) is None
    assert alugueis.dar_baixa(c, date(2026, 3, 1)) == "Este aluguel já foi encerrado."


# ---------------------------------------------------------------- inquilino com aluguel
def _inq_form(imoveis=(), **extra):
    d = {"nome": "Paulo Dias", "telefone": "1199", "aluguel_dia_vencimento": "5"}
    if imoveis:
        d.update({"aluguel_imoveis": [m.id for m in imoveis], "aluguel_inicio": "2026-03-01",
                  "aluguel_fim": "2027-02-28"})
    d.update(extra)
    return d


def test_inquilino_com_imoveis_cria_alugueis(client, base):
    _, a, v, _ = base
    r = client.post("/c/inquilinos/novo", data=_inq_form([a, v]))
    assert r.status_code == 302
    inq = Inquilino.query.filter_by(nome="Paulo Dias").one()
    assert Contrato.query.filter_by(inquilino_id=inq.id).count() == 2
    html = client.get("/c/inquilinos/").get_data(as_text=True)
    assert "Aluguéis ativos" in html and "Apto 101" in html


def test_inquilino_aluguel_invalido_nao_salva_nada(client, base):
    _, a, _, i = base
    r = client.post("/c/inquilinos/novo", data=_inq_form([a], aluguel_inicio="", aluguel_fim=""))
    assert "Informe o início e o fim".encode() in r.data
    novo_contrato(i, a)
    r = client.post("/c/inquilinos/novo", data=_inq_form([a]))
    assert "Já está alugado".encode() in r.data
    assert Inquilino.query.filter_by(nome="Paulo Dias").count() == 0 and Contrato.query.count() == 1


def test_inquilino_sem_aluguel_e_edicao_adiciona_aluguel(client, base):
    _, a, _, _ = base
    r = client.post("/c/inquilinos/novo", data=_inq_form())
    assert r.status_code == 302 and Contrato.query.count() == 0
    inq = Inquilino.query.filter_by(nome="Paulo Dias").one()
    html = client.get(f"/c/inquilinos/{inq.id}/editar").get_data(as_text=True)
    assert re.search(r'name="aluguel_dia_vencimento"\s+value="5"', html)
    assert client.post(f"/c/inquilinos/{inq.id}/editar", data=_inq_form([a])).status_code == 302
    assert Contrato.query.filter_by(inquilino_id=inq.id).count() == 1


# ---------------------------------------------------------------- fichas e navegação
def test_ficha_do_predio(client, base):
    p, a, v, i = base
    novo_contrato(i, a)
    html = client.get(f"/predios/{p.id}").get_data(as_text=True)
    assert "Ed. Sol" in html and "unit-alugada" in html and "unit-livre" in html
    assert "Apartamentos" in html and "Vagas de garagem" in html
    assert "R$ 1.000,00" in html  # receita mensal das unidades alugadas


def test_ficha_do_imovel_alugar_e_dar_baixa(client, base):
    _, a, _, i = base
    html = client.get(f"/imoveis/{a.id}").get_data(as_text=True)
    assert f"aluguel_imoveis={a.id}" in html and "Disponível" in html
    form = client.get(f"/c/alugueis/novo?aluguel_imoveis={a.id}").get_data(as_text=True)
    assert re.search(rf'<option value="{a.id}" selected>', form)
    novo_contrato(i, a)
    html = client.get(f"/imoveis/{a.id}").get_data(as_text=True)
    assert "Dar baixa" in html and "Maria" in html and "Histórico de aluguéis" in html


def test_ficha_do_inquilino_com_debito_e_acoes(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a, inicio=date(2025, 1, 1), fim=date(2025, 12, 31))
    html = client.get(f"/inquilinos/{i.id}").get_data(as_text=True)
    assert "Em débito" in html and "Novo aluguel" in html
    assert f"contrato_id={c.id}" in html and "Dar baixa" in html


def test_menu_tem_seis_itens_e_sem_contratos_nem_vagas(client):
    html = client.get("/").get_data(as_text=True)
    menu = html.split('<nav class="side-scroll')[1].split("</nav>")[0]
    assert menu.count('class="nav-link') == 6
    for removido in ("Contratos", "Vagas", "Prédios"):
        assert removido not in menu
    assert "Imóveis" in html


def test_enderecos_antigos_redirecionam(client):
    for antigo, novo in (("/c/apartamentos/", "/c/imoveis/"), ("/c/vagas/", "/c/imoveis/?tipo=vaga"),
                         ("/c/contratos/", "/c/inquilinos/")):
        r = client.get(antigo)
        assert r.status_code == 302 and r.headers["Location"].endswith(novo)
    assert client.get("/c/alugueis/").status_code == 302  # sem listagem própria


def test_dashboard_mostra_ocupacao_e_debito(client, base):
    _, a, _, i = base
    novo_contrato(i, a, inicio=date(2025, 1, 1), fim=date(2025, 12, 31))
    html = client.get("/").get_data(as_text=True)
    assert "1 de 2" in html and "Total em débito" in html and "Novo aluguel" in html
    assert "grafico-meses" in html


def test_paginas_principais_respondem(client, base):
    p, a, v, i = base
    for url in ["/", "/c/imoveis/", "/c/predios/", "/c/inquilinos/", "/c/pagamentos/",
                "/c/despesas/?mes=2026-03", "/c/alugueis/novo", "/c/pagamentos/novo",
                "/c/imoveis/novo", "/c/predios/novo", "/c/inquilinos/novo",
                "/relatorios/?mes=2026-03", "/relatorios/debitos",
                f"/predios/{p.id}", f"/imoveis/{a.id}", f"/inquilinos/{i.id}",
                f"/c/imoveis/{a.id}/editar", f"/c/predios/{p.id}/editar"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/static/app.css").status_code == 200


def test_excluir_com_vinculo(client, base):
    p, *_ = base
    r = client.post(f"/c/predios/{p.id}/excluir")
    assert r.status_code == 302 and Predio.query.count() == 1


# ---------------------------------------------------------------- pagamentos
def _pagto(contrato_id, valor, data="2026-03-05", comp="2026-03", forma="Pix", quem="Fagner"):
    return {"contrato_id": contrato_id, "competencia": comp, "data_pagamento": data,
            "valor_pago": valor, "forma_pagamento": forma, "recebido_por": quem}


def test_forma_e_recebedor_sao_combos_obrigatorios(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    html = client.get("/c/pagamentos/novo").get_data(as_text=True)
    for txt in ("Pix", "Dinheiro", "Transferência bancária (TED/DOC)", "Sergio", "Fagner",
                'id="dica-valor"', "data-sugestao"):
        assert txt in html
    r = client.post("/c/pagamentos/novo", data=_pagto(c.id, "1000", forma="Cheque"))
    assert "opção inválida" in r.get_data(as_text=True)
    r = client.post("/c/pagamentos/novo", data=_pagto(c.id, "1000", quem="Outro"))
    assert "opção inválida" in r.get_data(as_text=True)
    assert Pagamento.query.count() == 0


def test_pagamento_volta_para_a_ficha_de_origem(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    origem = f"/inquilinos/{i.id}"
    form = client.get(f"/c/pagamentos/novo?contrato_id={c.id}&next={origem}").get_data(as_text=True)
    assert f'name="next" value="{origem}"' in form
    assert re.search(rf'<option value="{c.id}" selected>', form)
    r = client.post("/c/pagamentos/novo", data={**_pagto(c.id, "1000"), "next": origem})
    assert r.headers["Location"].endswith(origem)
    r = client.post("/c/pagamentos/novo", data={**_pagto(c.id, "1", data="2026-03-06"),
                                                "next": "//evil.example"})
    assert r.headers["Location"].endswith("/c/pagamentos/")


def test_sugestao_de_valor_e_faltante_abatido(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a)
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
    assert client.get("/c/pagamentos/sugestao?contrato_id=999").status_code == 404


# ---------------------------------------------------------------- relatórios
def test_relatorio_saldo_e_pendencias(base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    db.session.add_all([
        Pagamento(contrato=c, competencia=date(2026, 3, 1), data_pagamento=date(2026, 3, 5),
                  valor_pago=Decimal("1000"), forma_pagamento="Pix", recebido_por="Sergio"),
        Pagamento(contrato=c, competencia=date(2026, 4, 1), data_pagamento=date(2026, 4, 5),
                  valor_pago=Decimal("1000")),
        Despesa(data=date(2026, 3, 10), descricao="Reparo", valor=Decimal("150.50")),
        Despesa(data=date(2026, 4, 10), descricao="Outro mês", valor=Decimal("99")),
    ])
    db.session.commit()
    d = relatorio.dados_mes(2026, 3)
    assert d["total_recebido"] == Decimal("1000") and d["total_despesas"] == Decimal("150.50")
    assert d["saldo"] == Decimal("849.50") and d["pendentes"] == []
    assert len(relatorio.dados_mes(2026, 5)["pendentes"]) == 1


def test_pendencia_considera_baixa(base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    c.ativo, c.encerrado_em = False, date(2026, 3, 10)
    db.session.commit()
    assert len(relatorio.dados_mes(2026, 3)["pendentes"]) == 1   # mês da baixa ainda cobra
    assert relatorio.dados_mes(2026, 4)["pendentes"] == []       # depois da baixa, não


def test_exportacoes_e_coluna_recebido_por(client, base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    db.session.add(Pagamento(contrato=c, competencia=date(2026, 3, 1),
                             data_pagamento=date(2026, 3, 5), valor_pago=Decimal("1000"),
                             forma_pagamento="Pix", recebido_por="Sergio"))
    db.session.commit()
    d = relatorio.dados_mes(2026, 3)
    assert relatorio.gerar_pdf(d).startswith(b"%PDF") and relatorio.gerar_xlsx(d)[:2] == b"PK"
    assert "Sergio" in client.get("/relatorios/?mes=2026-03").get_data(as_text=True)
    assert client.get("/relatorios/exportar.pdf?mes=2026-03").mimetype == "application/pdf"
    assert client.get("/relatorios/exportar.xlsx?mes=2026-03").status_code == 200


def test_serie_meses(base):
    _, a, _, i = base
    c = novo_contrato(i, a)
    db.session.add_all([
        Pagamento(contrato=c, competencia=date(2026, 1, 1), data_pagamento=date(2026, 1, 5),
                  valor_pago=Decimal("1000")),
        Despesa(data=date(2025, 12, 10), descricao="x", valor=Decimal("40")),
    ])
    db.session.commit()
    s = relatorio.serie_meses(2026, 1, n=3)
    assert [x["rotulo"] for x in s] == ["novembro/2025", "dezembro/2025", "janeiro/2026"]
    assert [x["recebido"] for x in s] == [0.0, 0.0, 1000.0]
    assert [x["despesas"] for x in s] == [0.0, 40.0, 0.0]


def test_debitos_por_inquilino(base):
    _, a, _, i = base
    c = novo_contrato(i, a, inicio=date(2026, 1, 1), fim=date(2026, 12, 31))  # R$ 1000, dia 5
    db.session.add_all([
        Pagamento(contrato=c, competencia=date(2026, 1, 1), data_pagamento=date(2026, 1, 5),
                  valor_pago=Decimal("1000")),
        Pagamento(contrato=c, competencia=date(2026, 2, 1), data_pagamento=date(2026, 2, 5),
                  valor_pago=Decimal("600"))])
    db.session.commit()
    d = relatorio.debitos(hoje=date(2026, 4, 10))
    item = d["inquilinos"][0]
    assert [m["competencia"] for m in item["meses"]] == [date(2026, 2, 1), date(2026, 3, 1),
                                                          date(2026, 4, 1)]
    assert item["total"] == Decimal("2400") and d["total"] == Decimal("2400")
    assert relatorio.debitos(hoje=date(2026, 4, 5))["total"] == Decimal("1400")
    assert alugueis.debito_do_inquilino(i.id) is not None


def test_debitos_contrato_encerrado_e_quitado(base):
    _, a, _, i = base
    c = novo_contrato(i, a, inicio=date(2026, 1, 1), fim=date(2026, 12, 31))
    for m in (1, 2):
        db.session.add(Pagamento(contrato=c, competencia=date(2026, m, 1),
                                 data_pagamento=date(2026, m, 5), valor_pago=Decimal("1000")))
    c.ativo, c.encerrado_em = False, date(2026, 2, 28)
    db.session.commit()
    assert relatorio.debitos(hoje=date(2026, 9, 1))["inquilinos"] == []


# ---------------------------------------------------------------- fechamento por pessoa
def _pag(c, valor, quem, forma="Pix", dia=5, comp=date(2026, 3, 1)):
    return Pagamento(contrato=c, competencia=comp, data_pagamento=date(2026, 3, dia),
                     valor_pago=Decimal(valor), forma_pagamento=forma, recebido_por=quem)


def _fechamento_base(base):
    _, a, v, i = base
    c1 = novo_contrato(i, a)
    c2 = novo_contrato(i, v, valor="250")
    db.session.add_all([
        _pag(c1, "600", "Sergio", "Pix"),
        _pag(c1, "400", "Fagner", "Dinheiro", dia=20),
        _pag(c2, "250", "Sergio", "Dinheiro"),
        _pag(c2, "50", None, "Cheque", dia=21, comp=date(2026, 4, 1)),          # sem recebedor, forma antiga
        Despesa(data=date(2026, 3, 8), descricao="Reparo", valor=Decimal("100"), pago_por="Sergio"),
        Despesa(data=date(2026, 3, 9), descricao="Limpeza", valor=Decimal("30"), pago_por="Fagner"),
        Despesa(data=date(2026, 3, 10), descricao="Antiga", valor=Decimal("20")),  # sem pagador
        Pagamento(contrato=c1, competencia=date(2026, 4, 1), data_pagamento=date(2026, 4, 5),
                  valor_pago=Decimal("999"), forma_pagamento="Pix", recebido_por="Sergio"),  # outro mês
    ])
    db.session.commit()


def test_fechamento_por_pessoa(base):
    _fechamento_base(base)
    f = relatorio.fechamento(2026, 3)
    por_nome = {p["nome"]: p for p in f["pessoas"]}
    assert list(por_nome) == ["Sergio", "Fagner", "Não informado"]
    s, g, n = por_nome["Sergio"], por_nome["Fagner"], por_nome["Não informado"]
    assert s["recebido"] == Decimal("850") and s["qtd"] == 2
    assert s["por_forma"]["Pix"] == Decimal("600") and s["por_forma"]["Dinheiro"] == Decimal("250")
    assert s["gasto"] == Decimal("100") and s["saldo"] == Decimal("750")
    assert g["recebido"] == Decimal("400") and g["gasto"] == Decimal("30") and g["saldo"] == Decimal("370")
    assert g["por_forma"]["Dinheiro"] == Decimal("400")
    assert n["recebido"] == Decimal("50") and n["gasto"] == Decimal("20")
    assert n["por_forma"]["Outras / não informada"] == Decimal("50")
    # a soma por pessoa bate com o relatório mensal
    mensal = relatorio.dados_mes(2026, 3)
    assert sum(p["recebido"] for p in f["pessoas"]) == mensal["total_recebido"] == f["total_recebido"]
    assert sum(p["gasto"] for p in f["pessoas"]) == mensal["total_despesas"] == f["total_despesas"]
    assert sum(p["saldo"] for p in f["pessoas"]) == mensal["saldo"] == f["saldo"]
    assert sum(f["totais_forma"].values()) == f["total_recebido"]


def test_fechamento_sem_dados_nao_mostra_nao_informado(base):
    f = relatorio.fechamento(2026, 8)
    assert [p["nome"] for p in f["pessoas"]] == ["Sergio", "Fagner"]
    assert f["total_recebido"] == 0 and all(p["saldo"] == 0 for p in f["pessoas"])


def test_tela_e_exportacoes_do_fechamento(client, base):
    _fechamento_base(base)
    html = client.get("/relatorios/fechamento?mes=2026-03").get_data(as_text=True)
    for txt in ("Fechamento de março/2026", "Sergio", "Fagner", "Não informado", "R$ 850,00",
                "R$ 750,00", "Resumo por forma de pagamento", "Fechamento por pessoa"):
        assert txt in html
    pdf = client.get("/relatorios/fechamento.pdf?mes=2026-03")
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    xlsx = client.get("/relatorios/fechamento.xlsx?mes=2026-03")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(xlsx.data))
    assert wb.sheetnames == ["Resumo", "Sergio", "Fagner", "Não informado"]
    assert client.get("/relatorios/fechamento.csv").status_code == 404


def test_despesa_exige_pago_por_e_filtros_por_pessoa(client, base):
    dados = {"data": "2026-03-08", "descricao": "Reparo", "valor": "100"}
    r = client.post("/c/despesas/novo", data=dados)
    assert "Pago por: campo obrigatório" in r.get_data(as_text=True)
    assert client.post("/c/despesas/novo", data={**dados, "pago_por": "Outro"}).status_code == 200
    assert client.post("/c/despesas/novo", data={**dados, "pago_por": "Fagner"}).status_code == 302
    client.post("/c/despesas/novo", data={**dados, "descricao": "Luz", "pago_por": "Sergio"})
    html = client.get("/c/despesas/?mes=2026-03&pago_por=Fagner").get_data(as_text=True)
    corpo = html.split("<tbody>")[1]
    assert "Reparo" in corpo and "Luz" not in corpo
    # filtro de pagamentos por quem recebeu
    _, a, _, i = base
    c = novo_contrato(i, a)
    db.session.add_all([_pag(c, "600", "Sergio"), _pag(c, "400", "Fagner", dia=20)])
    db.session.commit()
    corpo = client.get("/c/pagamentos/?mes=2026-03&recebido_por=Sergio").get_data(as_text=True).split("<tbody>")[1]
    assert "R$ 600,00" in corpo and "Sergio" in corpo and "Fagner" not in corpo


# ---------------------------------------------------------------- filtro por pessoa e PDFs
def test_dados_mes_e_serie_filtrados_por_pessoa(base):
    _fechamento_base(base)
    todos = relatorio.dados_mes(2026, 3)
    sergio = relatorio.dados_mes(2026, 3, "Sergio")
    fagner = relatorio.dados_mes(2026, 3, "Fagner")
    assert sergio["total_recebido"] == Decimal("850") and sergio["total_despesas"] == Decimal("100")
    assert fagner["total_recebido"] == Decimal("400") and fagner["total_despesas"] == Decimal("30")
    assert sergio["saldo"] == Decimal("750") and fagner["pessoa"] == "Fagner"
    assert todos["total_recebido"] == Decimal("1300") and todos["pessoa"] is None
    # nome desconhecido equivale a "todos"
    assert relatorio.dados_mes(2026, 3, "Ninguem")["total_recebido"] == todos["total_recebido"]
    s_fagner = relatorio.serie_meses(2026, 3, n=2, pessoa="Fagner")
    assert [x["recebido"] for x in s_fagner] == [0.0, 400.0] and [x["despesas"] for x in s_fagner] == [0.0, 30.0]
    s_todos = relatorio.serie_meses(2026, 3, n=2)
    assert s_todos[1]["recebido"] == 1300.0 and s_todos[0]["recebido"] == 0.0  # fev vazio; mar total
    # pendências não dependem da pessoa
    assert len(sergio["pendentes"]) == len(todos["pendentes"])


def test_dashboard_com_filtro_de_pessoa(client, base, monkeypatch):
    _fechamento_base(base)
    from datetime import date as _date

    class _Hoje(_date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 15)

    monkeypatch.setattr("gestao.services.periodo.date", _Hoje)
    html = client.get("/").get_data(as_text=True)
    assert 'id="pessoa"' in html and "Todos" in html and "R$ 1.300,00" in html
    html = client.get("/?pessoa=Fagner").get_data(as_text=True)
    assert "Mostrando só o que" in html and "Fagner" in html
    assert "R$ 400,00" in html and "R$ 1.300,00" not in html
    assert '<option value="Fagner" selected>' in html
    assert "Mostrando só o que" not in client.get("/?pessoa=Outro").get_data(as_text=True)


def test_pdfs_legiveis_com_textos_e_paginas(base):
    pymupdf = pytest.importorskip("pymupdf")
    _fechamento_base(base)
    pdf = relatorio.gerar_pdf_fechamento(relatorio.fechamento(2026, 3))
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    texto = "\n".join(p.get_text() for p in doc)
    for esperado in ("Fechamento por pessoa", "Sergio", "Fagner", "Não informado", "R$ 850,00",
                     "R$ 750,00", "Total recebido", "Saldo", f"Página 1 de {len(doc)}"):
        assert esperado in texto, esperado
    # nada fora das margens da página (tabelas dentro da área útil)
    for pagina in doc:
        for bloco in pagina.get_text("blocks"):
            assert bloco[0] >= 30 and bloco[2] <= pagina.rect.width - 30, bloco
    mensal = pymupdf.open(stream=relatorio.gerar_pdf(relatorio.dados_mes(2026, 3, "Sergio")),
                          filetype="pdf")
    texto = "\n".join(p.get_text() for p in mensal)
    assert "somente Sergio" in texto and "R$ 850,00" in texto and "Fagner" not in texto.split("Despesas")[0]
