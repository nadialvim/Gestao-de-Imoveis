# Gestão de Imóveis

Sistema web responsivo (Flask + Bootstrap) para gerenciar aluguéis de apartamentos, casas, lojas e vagas de garagem,
registrar pagamentos e despesas e exportar o relatório mensal (PDF/Excel). Hospedagem: Vercel + Supabase.

## Rodar localmente
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
copy .env.example .env                              # preencha com os dados do Supabase
flask --app app run --debug
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
   `DATABASE_URL` (ou `POSTGRES_URL`, da integração Supabase), `SUPABASE_URL`, `SUPABASE_ANON_KEY` (ou `SUPABASE_PUBLISHABLE_KEY`) e `SECRET_KEY` (valor aleatório longo, obrigatório). Não use a `SUPABASE_SECRET_KEY`.
4. Acesse a URL gerada e entre com um usuário do Supabase.

## Como usar
Prédios (já com a lista de apartamentos e lojas; dá para adicionar mais depois) → Imóveis (apartamento/loja num prédio, ou casa independente) / Vagas → Inquilinos → alugar pelo botão **Alugar** do imóvel/vaga disponível (escolha ou cadastre o inquilino e informe o período; o valor é o do imóvel). O imóvel alugado só volta a ficar disponível ao **Dar baixa** → Pagamentos
(mês de referência e data do recebimento) → Despesas. Em **Relatórios** escolha o mês e exporte PDF ou Excel:
o relatório lista os valores *recebidos no mês* (pela data do pagamento), as despesas do mês e o saldo a repassar.

## Atualizar o banco (versão com imóveis/baixa)
Se o banco foi criado com a versão anterior (tabela `apartamentos`), rode **uma vez** o conteúdo de
`db/migrations/002_imoveis.sql` no SQL Editor do Supabase, antes de usar o site atualizado. Bancos novos usam
apenas `db/schema.sql`.

Pagamentos: ao escolher o contrato e o mês, o valor recebido vem preenchido com o que falta (editável); informe a
forma (Pix, Dinheiro, Transferência) e quem recebeu (Sergio/Fagner). A lista mostra a coluna **Faltante** em
pagamentos parciais (complementos do mesmo mês de referência são abatidos). O menu **Em débito** lista os
inquilinos com meses vencidos e não pagos desde o início do contrato.

Se o banco já existia antes desta versão, rode também `db/migrations/003_recebido_por.sql` (uma vez).
