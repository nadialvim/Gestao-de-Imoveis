from decimal import Decimal

from sqlalchemy import and_, func, or_

from .extensions import db

FORMAS_PAGAMENTO = ["Pix", "Dinheiro", "Transferência bancária (TED/DOC)"]
RECEBEDORES = ["Sergio", "Fagner"]
NAO_INFORMADO = "Não informado"


class Predio(db.Model):
    __tablename__ = "predios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    endereco = db.Column(db.String(255))
    imoveis = db.relationship("Imovel", back_populates="predio",
                              order_by="Imovel.tipo, Imovel.identificacao")

    def __str__(self):
        return self.nome


class Imovel(db.Model):
    """Unidade alugável: apartamento e loja (de um prédio), casa (independente)
    ou vaga de garagem (prédio opcional)."""
    __tablename__ = "imoveis"
    __table_args__ = (
        db.CheckConstraint("tipo in ('apartamento','casa','loja','vaga')", name="imoveis_tipo_chk"),
        db.CheckConstraint(
            "tipo = 'vaga' or (tipo = 'casa' and predio_id is null) "
            "or (tipo in ('apartamento','loja') and predio_id is not null)",
            name="imoveis_predio_chk"),
    )
    TIPOS = [("apartamento", "Apartamento"), ("casa", "Casa"), ("loja", "Loja"),
             ("vaga", "Vaga de garagem")]
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default="apartamento")
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    identificacao = db.Column(db.String(60), nullable=False)
    descricao = db.Column(db.String(255))
    valor_aluguel_padrao = db.Column(db.Numeric(12, 2))
    predio = db.relationship("Predio", back_populates="imoveis")
    contratos = db.relationship("Contrato", viewonly=True,
                                order_by="Contrato.data_inicio.desc()")

    @property
    def tipo_nome(self):
        return dict(self.TIPOS).get(self.tipo, self.tipo)

    @property
    def contrato_ativo(self):
        return next((c for c in self.contratos if c.ativo), None)

    @property
    def disponivel(self):
        return self.contrato_ativo is None

    def __str__(self):
        if self.tipo == "casa":
            return f"Casa {self.identificacao}"
        rotulo = {"apartamento": "Apto", "loja": "Loja", "vaga": "Vaga"}.get(self.tipo, "")
        prefixo = f"{self.predio.nome} - " if self.predio else ""
        return f"{prefixo}{rotulo} {self.identificacao}"


class Inquilino(db.Model):
    __tablename__ = "inquilinos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(40))
    email = db.Column(db.String(150))
    documento = db.Column(db.String(40))
    contratos = db.relationship("Contrato", viewonly=True, order_by="Contrato.data_inicio.desc()")

    @property
    def alugueis_ativos(self):
        return [c for c in self.contratos if c.ativo]

    def __str__(self):
        return self.nome


class Contrato(db.Model):
    """Aluguel de um imóvel/vaga por um inquilino (na interface: "Aluguel")."""
    __tablename__ = "contratos"
    id = db.Column(db.Integer, primary_key=True)
    inquilino_id = db.Column(db.Integer, db.ForeignKey("inquilinos.id"), nullable=False)
    imovel_id = db.Column(db.Integer, db.ForeignKey("imoveis.id"), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    valor_mensal = db.Column(db.Numeric(12, 2), nullable=False)
    dia_vencimento = db.Column(db.Integer, nullable=False, default=5)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    encerrado_em = db.Column(db.Date)  # data da devolução (baixa); ativo=False
    inquilino = db.relationship("Inquilino")
    imovel = db.relationship("Imovel", overlaps="contratos")

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
    recebido_por = db.Column(db.String(40))
    observacao = db.Column(db.String(255))
    contrato = db.relationship("Contrato")

    @property
    def faltante(self):
        """Quanto ainda faltava do mês de referência logo após este pagamento
        (abate os pagamentos anteriores do mesmo contrato e competência)."""
        total = db.session.query(func.coalesce(func.sum(Pagamento.valor_pago), 0)).filter(
            Pagamento.contrato_id == self.contrato_id,
            Pagamento.competencia == self.competencia,
            or_(Pagamento.data_pagamento < self.data_pagamento,
                and_(Pagamento.data_pagamento == self.data_pagamento,
                     Pagamento.id <= self.id))).scalar()
        return max(Decimal("0"), Decimal(str(self.contrato.valor_mensal)) - Decimal(str(total)))


class Despesa(db.Model):
    __tablename__ = "despesas"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(80))
    valor = db.Column(db.Numeric(12, 2), nullable=False)
    pago_por = db.Column(db.String(40))  # quem pagou (Sergio/Fagner) — fechamento por pessoa
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    predio = db.relationship("Predio")
