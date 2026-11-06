-- Execute no Supabase: SQL Editor > New query > Run

create table if not exists predios (
    id serial primary key,
    nome varchar(120) not null,
    endereco varchar(255)
);

create table if not exists apartamentos (
    id serial primary key,
    predio_id integer not null references predios(id),
    numero varchar(30) not null,
    descricao varchar(255),
    valor_aluguel_padrao numeric(12,2)
);

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

create table if not exists contratos (
    id serial primary key,
    inquilino_id integer not null references inquilinos(id),
    apartamento_id integer references apartamentos(id),
    vaga_id integer references vagas(id),
    data_inicio date not null,
    data_fim date not null,
    valor_mensal numeric(12,2) not null,
    dia_vencimento integer not null default 5,
    ativo boolean not null default true,
    check ((apartamento_id is not null)::int + (vaga_id is not null)::int = 1),
    check (data_fim >= data_inicio)
);

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
alter table apartamentos enable row level security;
alter table vagas enable row level security;
alter table inquilinos enable row level security;
alter table contratos enable row level security;
alter table pagamentos enable row level security;
alter table despesas enable row level security;
