-- Migração 002: apartamentos -> imoveis (apartamento / casa / loja), baixa de contratos.
-- Execute UMA vez no Supabase (SQL Editor) em bancos criados com a versão anterior.
begin;

alter table apartamentos rename to imoveis;
alter table imoveis rename column numero to identificacao;
alter table imoveis alter column identificacao type varchar(60);
alter table imoveis alter column predio_id drop not null;
alter table imoveis add column tipo varchar(20) not null default 'apartamento';
alter table imoveis add constraint imoveis_tipo_chk
    check (tipo in ('apartamento', 'casa', 'loja'));
alter table imoveis add constraint imoveis_predio_chk check (
    (tipo = 'casa' and predio_id is null) or (tipo <> 'casa' and predio_id is not null));
create unique index if not exists ux_imoveis_unidade
    on imoveis (coalesce(predio_id, 0), tipo, identificacao);

alter table contratos rename column apartamento_id to imovel_id;
alter table contratos add column if not exists encerrado_em date;
-- contratos já inativos: assume encerramento na data final prevista
update contratos set encerrado_em = data_fim where not ativo and encerrado_em is null;

-- Se um mesmo imóvel/vaga tiver mais de um contrato ativo, mantém só o mais recente.
update contratos c set ativo = false, encerrado_em = coalesce(encerrado_em, least(data_fim, current_date))
where ativo and imovel_id is not null and exists (
    select 1 from contratos o where o.imovel_id = c.imovel_id and o.ativo and o.id <> c.id
      and (o.data_inicio > c.data_inicio or (o.data_inicio = c.data_inicio and o.id > c.id)));
update contratos c set ativo = false, encerrado_em = coalesce(encerrado_em, least(data_fim, current_date))
where ativo and vaga_id is not null and exists (
    select 1 from contratos o where o.vaga_id = c.vaga_id and o.ativo and o.id <> c.id
      and (o.data_inicio > c.data_inicio or (o.data_inicio = c.data_inicio and o.id > c.id)));

-- Um imóvel/vaga só pode ter um contrato ativo por vez.
create unique index if not exists ux_contrato_ativo_imovel on contratos(imovel_id)
    where ativo and imovel_id is not null;
create unique index if not exists ux_contrato_ativo_vaga on contratos(vaga_id)
    where ativo and vaga_id is not null;

commit;
