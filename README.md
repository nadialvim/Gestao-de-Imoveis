# Gestão de Imóveis

Sistema web responsivo (Flask + Bootstrap) para gerenciar aluguéis de apartamentos e vagas de garagem,
registrar pagamentos e despesas e exportar o relatório mensal (PDF/Excel). Hospedagem: Vercel + Supabase.

## Rodar localmente
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
copy .env.example .env                              # preencha com os dados do Supabase
flask --app api.index run --debug
pytest                                              # testes (SQLite em memória)
```

## Publicar (grátis)
1. **Supabase**: crie um projeto. Em *SQL Editor*, execute `db/schema.sql`.
   - *Authentication > Providers > Email*: **desative "Allow new users to sign up"** (qualquer conta
     criada no Supabase consegue entrar no sistema). Crie os usuários em *Authentication > Users*
     (marque "Auto Confirm User").
   - Copie a *Connection string* do **Transaction pooler** (porta 6543) e, em *Settings > API*, a URL e a `anon key`.
2. **GitHub**: crie um repositório e envie o código (`git remote add origin ...; git push -u origin main`).
3. **Vercel**: *Add New > Project*, importe o repositório e configure as variáveis de ambiente:
   `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SECRET_KEY` (valor aleatório longo).
4. Acesse a URL gerada e entre com um usuário do Supabase.

## Como usar
Prédios → Apartamentos / Vagas → Inquilinos → Contratos (inquilino + imóvel + período) → Pagamentos
(mês de referência e data do recebimento) → Despesas. Em **Relatórios** escolha o mês e exporte PDF ou Excel:
o relatório lista os valores *recebidos no mês* (pela data do pagamento), as despesas do mês e o saldo a repassar.
