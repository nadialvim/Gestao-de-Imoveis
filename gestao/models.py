from .extensions import db


class Predio(db.Model):
    __tablename__ = "predios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    endereco = db.Column(db.String(255))

    def __str__(self):
        return self.nome


class Apartamento(db.Model):
    __tablename__ = "apartamentos"
    id = db.Column(db.Integer, primary_key=True)
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"), nullable=False)
    numero = db.Column(db.String(30), nullable=False)
    descricao = db.Column(db.String(255))
    valor_aluguel_padrao = db.Column(db.Numeric(12, 2))
    predio = db.relationship("Predio")

    def __str__(self):
        return f"{self.predio.nome} - Apto {self.numero}"


class Vaga(db.Model):
    __tablename__ = "vagas"
    id = db.Column(db.Integer, primary_key=True)
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    identificacao = db.Column(db.String(60), nullable=False)
    valor_aluguel_padrao = db.Column(db.Numeric(12, 2))
    predio = db.relationship("Predio")

    def __str__(self):
        base = f"Vaga {self.identificacao}"
        return f"{self.predio.nome} - {base}" if self.predio else base


class Inquilino(db.Model):
    __tablename__ = "inquilinos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(40))
    email = db.Column(db.String(150))
    documento = db.Column(db.String(40))

    def __str__(self):
        return self.nome


class Contrato(db.Model):
    __tablename__ = "contratos"
    id = db.Column(db.Integer, primary_key=True)
    inquilino_id = db.Column(db.Integer, db.ForeignKey("inquilinos.id"), nullable=False)
    apartamento_id = db.Column(db.Integer, db.ForeignKey("apartamentos.id"))
    vaga_id = db.Column(db.Integer, db.ForeignKey("vagas.id"))
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    valor_mensal = db.Column(db.Numeric(12, 2), nullable=False)
    dia_vencimento = db.Column(db.Integer, nullable=False, default=5)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    inquilino = db.relationship("Inquilino")
    apartamento = db.relationship("Apartamento")
    vaga = db.relationship("Vaga")

    @property
    def imovel(self):
        return self.apartamento or self.vaga

    def __str__(self):
        return f"{self.inquilino} — {self.imovel}"


class Pagamento(db.Model):
    __tablename__ = "pagamentos"
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    competencia = db.Column(db.Date, nullable=False)  # dia 1 do mês de referência
    data_pagamento = db.Column(db.Date, nullable=False)
    valor_pago = db.Column(db.Numeric(12, 2), nullable=False)
    forma_pagamento = db.Column(db.String(40))
    observacao = db.Column(db.String(255))
    contrato = db.relationship("Contrato")


class Despesa(db.Model):
    __tablename__ = "despesas"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(80))
    valor = db.Column(db.Numeric(12, 2), nullable=False)
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    predio = db.relationship("Predio")
