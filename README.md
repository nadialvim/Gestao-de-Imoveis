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
1. **Supabase**: crie um projeto. Em *SQL Editor*, execute `db/schema.sql` (banco novo).
   - *Authentication > Providers > Email*: **desative "Allow new users to sign up"** (qualquer conta
     criada no Supabase consegue entrar no sistema). Crie os usuários em *Authentication > Users*
     (marque "Auto Confirm User").
   - Copie a *Connection string* do **Transaction pooler** (porta 6543) e, em *Settings > API*, a URL e a `anon key`.
2. **GitHub**: crie um repositório e envie o código (`git remote add origin ...; git push -u origin main`).
3. **Vercel**: *Add New > Project*, importe o repositório e configure as variáveis de ambiente:
   `DATABASE_URL` (ou `POSTGRES_URL`, da integração Supabase), `SUPABASE_URL`, `SUPABASE_ANON_KEY` (ou `SUPABASE_PUBLISHABLE_KEY`) e `SECRET_KEY` (valor aleatório longo, obrigatório). Não use a `SUPABASE_SECRET_KEY`.
4. Acesse a URL gerada e entre com um usuário do Supabase.

## Atualizar um banco que já existia
Rode, **na ordem e uma vez cada**, no SQL Editor do Supabase, apenas as migrações que ainda não rodou
(faça backup antes da 004):
`db/migrations/002_imoveis.sql` → `003_recebido_por.sql` → `004_unifica_vagas.sql`.
Bancos novos usam só `db/schema.sql`.

## Como usar
O menu tem 6 itens: **Início, Imóveis, Inquilinos, Pagamentos, Despesas, Relatórios**.

- **Imóveis** (abas *Imóveis* e *Prédios*): o **Prédio** já é cadastrado com a lista de apartamentos, lojas e vagas
  (`101, 102` ou `101-110`) e dá para adicionar mais depois. **Casa** é independente de prédio; **vaga de
  garagem** é um tipo de imóvel. O valor do aluguel fica no imóvel.
- **Fichas**: clicar no nome abre a ficha do prédio (grade de unidades verde = disponível / âmbar = alugada),
  do imóvel (histórico de aluguéis e pagamentos) ou do inquilino (aluguéis, débito e pagamentos).
- **Alugar**: botão **Alugar** do imóvel, **Novo aluguel** do inquilino ou do Início — o mesmo formulário:
  escolha (ou cadastre) o inquilino, os imóveis/vagas e o período. O valor mensal é o do imóvel. Também dá
  para vincular o imóvel direto ao cadastrar o inquilino. Imóvel alugado só volta a ficar disponível ao
  **Dar baixa** (na ficha do imóvel ou do inquilino).
- **Pagamentos**: pelo botão *Registrar pagamento* da ficha (ou menu Pagamentos), o valor vem preenchido com o
  que falta no mês (editável); informe a forma (Pix, Dinheiro, Transferência) e quem recebeu (Sergio/Fagner).
  A coluna **Faltante** mostra o que falta em pagamentos parciais (complementos do mesmo mês são abatidos).
- **Relatórios** (abas *Mensal* e *Inquilinos em débito*): o mensal lista os valores recebidos no mês (pela data
  do pagamento), as despesas e o saldo a repassar, com exportação em PDF/Excel; o de débito mostra, por
  inquilino, os meses vencidos e não pagos desde o início do aluguel.
