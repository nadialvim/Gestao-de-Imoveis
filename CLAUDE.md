# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sistema web (pt-BR) de gestão de aluguéis de apartamentos e vagas de garagem: Flask + Jinja + Bootstrap 5, Postgres no Supabase, deploy serverless na Vercel. Interface, mensagens e nomes de domínio são em português.

## Commands
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
flask --app app run --debug            # dev server (precisa de .env; sem DATABASE_URL usa SQLite local.db)
pytest                                       # todos os testes (SQLite em memória, login desativado)
pytest tests/test_app.py::test_relatorio_saldo   # um teste
```
Schema do banco: `db/schema.sql` (aplicado manualmente no SQL Editor do Supabase; não há migrações). Alterou `gestao/models.py` → atualize o `schema.sql` à mão.

## Architecture
- `app.py` (raiz) é o entrypoint da Vercel (`app = create_app()`, detectado automaticamente; sem `vercel.json`/rewrites; o rewrite anterior para `/api/index` provavelmente causava 404 na raiz). O pacote da aplicação é `gestao/` (factory em `gestao/__init__.py`).
- **CRUD genérico**: prédios, apartamentos, vagas, inquilinos, contratos, pagamentos e despesas não têm rota/template próprios. Cada um é um `Resource` declarativo em `gestao/resources.py` (campos, colunas, validação, filtro por mês), servido por `gestao/crud.py` em `/c/<slug>/` com `list.html`/`form.html`. Para novo cadastro, adicione um `Resource` (e o link no `base.html`). `gestao/fields.py` define `Field`/`Resource` e o parsing de formulário.
- Regras de negócio ficam nas funções `validate` dos recursos (ex.: `validar_contrato`: contrato é de apartamento **ou** vaga, e não pode sobrepor contrato ativo do mesmo imóvel).
- **Relatórios**: `gestao/services/relatorio.py` — `dados_mes()` consolida o mês (recebido por `data_pagamento`, despesas por `data`, pendências por `competencia` do contrato) e alimenta dashboard, tela de relatório, `gerar_pdf` (reportlab) e `gerar_xlsx` (openpyxl).
- **Auth**: login valida e-mail/senha direto na API REST do Supabase Auth (`gestao/auth.py`) e guarda só o e-mail na sessão Flask. Um `before_app_request` exige login em todas as rotas (seguro por padrão); `LOGIN_DISABLED` é usado só nos testes. CSRF próprio em `create_app` (token em `session`, campo `_csrf` em todo form POST; desligado com `TESTING`).
- **Banco**: Flask-SQLAlchemy; com Postgres usa `NullPool` (serverless + pooler do Supabase, porta 6543). Tabelas têm RLS ligado sem policies, pois o app conecta como `postgres` direto.
- `Pagamento.competencia` é sempre o dia 1 do mês de referência (campo `month`), distinto de `data_pagamento`.
- Variáveis de ambiente: `DATABASE_URL` (fallback `POSTGRES_URL`; `normalizar_db_url` remove o parâmetro `supa`), `SUPABASE_URL`, `SUPABASE_ANON_KEY` (fallback `SUPABASE_PUBLISHABLE_KEY`), `SECRET_KEY` (obrigatória na Vercel). Ver `.env.example` e `README.md` (passo a passo de deploy).
