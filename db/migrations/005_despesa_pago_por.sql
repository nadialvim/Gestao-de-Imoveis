-- Migração 005: quem pagou cada despesa (Sergio / Fagner), para o fechamento por pessoa.
-- Execute UMA vez no Supabase (SQL Editor) em bancos já existentes.
alter table despesas add column if not exists pago_por varchar(40);
