-- Migração 004: vagas de garagem passam a ser um tipo de imóvel (tabela imoveis).
-- Execute UMA vez no Supabase (SQL Editor), DEPOIS das migrações 002 e 003.
-- RECOMENDADO: exporte/faça backup das tabelas antes (Table Editor > Export).
begin;

-- 1. imoveis aceita o tipo 'vaga' (prédio opcional)
alter table imoveis drop constraint if exists imoveis_tipo_chk;
alter table imoveis drop constraint if exists imoveis_predio_chk;
alter table imoveis add constraint imoveis_tipo_chk
    check (tipo in ('apartamento', 'casa', 'loja', 'vaga'));
alter table imoveis add constraint imoveis_predio_chk check (
    tipo = 'vaga'
    or (tipo = 'casa' and predio_id is null)
    or (tipo in ('apartamento', 'loja') and predio_id is not null));

-- 2. copia cada vaga para imoveis, guardando a origem para repontar os aluguéis
alter table imoveis add column vaga_origem_id integer;
insert into imoveis (tipo, predio_id, identificacao, valor_aluguel_padrao, vaga_origem_id)
    select 'vaga', predio_id, identificacao, valor_aluguel_padrao, id from vagas;
update contratos c set imovel_id = i.id
    from imoveis i where c.vaga_id is not null and i.vaga_origem_id = c.vaga_id;

-- 3. remove o que era específico de vagas
drop index if exists ux_contrato_ativo_vaga;
drop index if exists ux_contrato_ativo_imovel;
alter table contratos drop column vaga_id;        -- remove também o CHECK "imóvel OU vaga"
alter table contratos alter column imovel_id set not null;
create unique index ux_contrato_ativo_imovel on contratos(imovel_id) where ativo;
alter table imoveis drop column vaga_origem_id;
drop table vagas;

commit;
