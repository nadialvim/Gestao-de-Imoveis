-- Execute no Supabase: SQL Editor > New query > Run
-- (banco novo). Se você já tinha as tabelas da versão anterior, execute
-- db/migrations/002_imoveis.sql em vez deste arquivo.

create table if not exists predios (
    id serial primary key,
    nome varchar(120) not null,
    endereco varchar(255)
);

-- Apartamento e loja (sempre com prédio) ou casa (independente, sem prédio)
create table if not exists imoveis (
    id serial primary key,
    tipo varchar(20) not null default 'apartamento'
        check (tipo in ('apartamento', 'casa', 'loja')),
    predio_id integer references predios(id),
    identificacao varchar(60) not null,
    descricao varchar(255),
    valor_aluguel_padrao numeric(12,2),
    constraint imoveis_predio_chk check (
        (tipo = 'casa' and predio_id is null) or (tipo <> 'casa' and predio_id is not null))
);
create unique index if not exists ux_imoveis_unidade
    on imoveis (coalesce(predio_id, 0), tipo, identificacao);

create table if not exists vagas (
    id serial primary key,
    predio_id integer references predios(id),
    identificacao varchar(60) not null,
    valor_aluguel_padrao numeric(12,2)
);

create table if not exists inquilinos (
    id serial primary key,
    nome varchar(150) not null,
    telefone varchar(40),
    email varchar(150),
    documento varchar(40)
);

-- ativo = true: aluguel em vigor (imóvel/vaga indisponível).
-- Dar baixa => ativo = false e encerrado_em = data da devolução (imóvel disponível).
create table if not exists contratos (
    id serial primary key,
    inquilino_id integer not null references inquilinos(id),
    imovel_id integer references imoveis(id),
    vaga_id integer references vagas(id),
    data_inicio date not null,
    data_fim date not null,
    valor_mensal numeric(12,2) not null,
    dia_vencimento integer not null default 5,
    ativo boolean not null default true,
    encerrado_em date,
    check ((imovel_id is not null)::int + (vaga_id is not null)::int = 1),
    check (data_fim >= data_inicio)
);
-- Um imóvel/vaga só pode ter um contrato ativo por vez.
create unique index if not exists ux_contrato_ativo_imovel on contratos(imovel_id)
    where ativo and imovel_id is not null;
create unique index if not exists ux_contrato_ativo_vaga on contratos(vaga_id)
    where ativo and vaga_id is not null;

create table if not exists pagamentos (
    id serial primary key,
    contrato_id integer not null references contratos(id),
    competencia date not null,          -- sempre dia 1 do mês de referência
    data_pagamento date not null,
    valor_pago numeric(12,2) not null,
    forma_pagamento varchar(40),
    observacao varchar(255)
);

create table if not exists despesas (
    id serial primary key,
    data date not null,
    descricao varchar(255) not null,
    categoria varchar(80),
    valor numeric(12,2) not null,
    predio_id integer references predios(id)
);

create index if not exists ix_pagamentos_data on pagamentos(data_pagamento);
create index if not exists ix_pagamentos_contrato_comp on pagamentos(contrato_id, competencia);
create index if not exists ix_despesas_data on despesas(data);

-- Segurança: bloqueia o acesso direto via API pública do Supabase (anon key).
-- O app usa a conexão Postgres direta (role postgres), que ignora o RLS.
alter table predios enable row level security;
alter table imoveis enable row level security;
alter table vagas enable row level security;
alter table inquilinos enable row level security;
alter table contratos enable row level security;
alter table pagamentos enable row level security;
alter table despesas enable row level security;
