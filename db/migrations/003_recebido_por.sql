-- Migração 003: quem recebeu o pagamento (Sergio / Fagner).
-- Execute UMA vez no Supabase (SQL Editor) em bancos já existentes.
alter table pagamentos add column if not exists recebido_por varchar(40);
