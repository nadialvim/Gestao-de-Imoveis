from datetime import date
from decimal import Decimal

import pytest

from gestao import create_app
from gestao.extensions import db
from gestao.models import Apartamento, Contrato, Despesa, Inquilino, Pagamento, Predio, Vaga
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
    a = Apartamento(predio=p, numero="101")
    v = Vaga(predio=p, identificacao="G1")
    i = Inquilino(nome="Maria")
    db.session.add_all([p, a, v, i])
    db.session.commit()
    return p, a, v, i


def novo_contrato(i, a=None, v=None, inicio=date(2026, 1, 1), fim=date(2026, 12, 31)):
    c = Contrato(inquilino=i, apartamento=a, vaga=v, data_inicio=inicio, data_fim=fim,
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
        "inquilino_id": i.id, "apartamento_id": a.id, "data_inicio": "2026-06-01",
        "data_fim": "2027-06-01", "valor_mensal": "900", "dia_vencimento": "5",
        "ativo": "on"})
    assert r.status_code == 200  # volta ao formulário com erro
    assert "Já existe contrato ativo".encode() in r.data
    assert Contrato.query.count() == 1


def test_contrato_exige_um_imovel(client, base):
    _, a, v, i = base
    r = client.post("/c/contratos/novo", data={
        "inquilino_id": i.id, "apartamento_id": a.id, "vaga_id": v.id,
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
        "valor_pago": "250.00"})
    assert r.status_code == 302
    assert Pagamento.query.one().competencia == date(2026, 2, 1)


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
