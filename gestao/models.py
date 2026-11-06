from .extensions import db


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
    """Apartamento e loja (vinculados a um prédio) ou casa (independente)."""
    __tablename__ = "imoveis"
    __table_args__ = (
        db.CheckConstraint("tipo in ('apartamento','casa','loja')", name="imoveis_tipo_chk"),
        db.CheckConstraint(
            "(tipo = 'casa' and predio_id is null) or (tipo <> 'casa' and predio_id is not null)",
            name="imoveis_predio_chk"),
    )
    TIPOS = [("apartamento", "Apartamento"), ("casa", "Casa"), ("loja", "Loja")]
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default="apartamento")
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    identificacao = db.Column(db.String(60), nullable=False)
    descricao = db.Column(db.String(255))
    valor_aluguel_padrao = db.Column(db.Numeric(12, 2))
    predio = db.relationship("Predio", back_populates="imoveis")
    contratos = db.relationship("Contrato", viewonly=True)

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
        rotulo = "Apto" if self.tipo == "apartamento" else "Loja"
        prefixo = f"{self.predio.nome} - " if self.predio else ""
        return f"{prefixo}{rotulo} {self.identificacao}"


class Vaga(db.Model):
    __tablename__ = "vagas"
    id = db.Column(db.Integer, primary_key=True)
    predio_id = db.Column(db.Integer, db.ForeignKey("predios.id"))
    identificacao = db.Column(db.String(60), nullable=False)
    valor_aluguel_padrao = db.Column(db.Numeric(12, 2))
    predio = db.relationship("Predio")
    contratos = db.relationship("Contrato", viewonly=True)

    @property
    def contrato_ativo(self):
        return next((c for c in self.contratos if c.ativo), None)

    @property
    def disponivel(self):
        return self.contrato_ativo is None

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
    imovel_id = db.Column(db.Integer, db.ForeignKey("imoveis.id"))
    vaga_id = db.Column(db.Integer, db.ForeignKey("vagas.id"))
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    valor_mensal = db.Column(db.Numeric(12, 2), nullable=False)
    dia_vencimento = db.Column(db.Integer, nullable=False, default=5)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    encerrado_em = db.Column(db.Date)  # data da devolução (baixa); ativo=False
    inquilino = db.relationship("Inquilino")
    imovel_rel = db.relationship("Imovel", overlaps="contratos")
    vaga = db.relationship("Vaga", overlaps="contratos")

    @property
    def imovel(self):
        """Imóvel ou vaga alugado neste contrato."""
        return self.imovel_rel or self.vaga

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
