# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sistema web (pt-BR) de gestão de aluguéis de apartamentos, casas, lojas e vagas de garagem: Flask + Jinja + Bootstrap 5, Postgres no Supabase, deploy serverless na Vercel. Interface, mensagens e nomes de domínio são em português ("aluguel" na interface = tabela/modelo `contratos`/`Contrato`).

## Commands
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
flask --app app run --debug                  # dev server (precisa de .env; sem DATABASE_URL usa SQLite local.db)
pytest                                       # todos os testes (SQLite em memória, login desativado)
pytest tests/test_app.py::test_relatorio_saldo_e_pendencias   # um teste
```
Schema: `db/schema.sql` (banco novo, aplicado manualmente no SQL Editor do Supabase). Não há ferramenta de migração: alterou `gestao/models.py` → atualize `schema.sql` **e** crie `db/migrations/00N_*.sql` (002 imóveis, 003 recebido_por, 004 unifica vagas, 005 despesa pago_por).

## Architecture
- `app.py` (raiz) é o entrypoint da Vercel (`app = create_app()`, detectado automaticamente; sem `vercel.json`/rewrites). O pacote é `gestao/` (factory em `gestao/__init__.py`).
- **Modelo**: `Predio`; `Imovel` (tabela `imoveis`) cobre apartamento/loja (com `predio_id`), casa (sem prédio) e **vaga** (prédio opcional) — CHECKs no modelo e no SQL; `Inquilino`; `Contrato` (= aluguel: `imovel_id`, período, `valor_mensal`, `ativo`, `encerrado_em`); `Pagamento`; `Despesa`. Disponível/Alugado **não é coluna**: deriva de existir `Contrato.ativo` (`Imovel.contrato_ativo`/`disponivel`); índice único parcial garante 1 aluguel ativo por imóvel.
- **Navegação**: 6 itens (Início, Imóveis, Inquilinos, Pagamentos, Despesas, Relatórios). `base.html` desenha a sidebar, a barra inferior mobile e as **abas** (Imóveis|Prédios e Mensal|Em débito). Contratos e Vagas não têm menu.
- **Fichas** (`gestao/routes/fichas.py`, `ficha_*.html`): `/predios/<id>`, `/imoveis/<id>`, `/inquilinos/<id>` ligam as entidades (grade de unidades, histórico, débito, ações). `POST /alugueis/<id>/baixa` dá a baixa (`next` seguro via `crud.destino_seguro`).
- **CRUD genérico**: `gestao/resources.py` declara cada `Resource` (campos, colunas, validação, hooks); `gestao/crud.py` serve `/c/<slug>/` (lista/novo/editar/excluir) com `list.html`/`form.html`. `gestao/fields.py` define `Field`/`Resource`: tipos `text, money, int, date, month, bool, select, multi, choice, lista`; `Field(extra=True)` = campo que não é coluna (alimenta `validate`/`before_save`); `Field.section`; `Resource.before_save/after_save/destino/ficha/sem_modelo/lista/filters/extra_fields/titulo_novo`. Funções de opções (`Field.choices`) podem receber `obj`. Query string pré-preenche o formulário (`?aluguel_imoveis=3`, `?contrato_id=7`) e `?next=` define para onde voltar.
- **Aluguel num só lugar**: `gestao/services/alugueis.py` (`validar_alugueis`, `criar_alugueis`, `dar_baixa`, `debito_do_inquilino`) é usado pelo formulário "Novo aluguel" (`Resource` `alugueis`, `sem_modelo`) e pelo cadastro de inquilino (campos `aluguel_*`). O valor vem **só** de `Imovel.valor_aluguel_padrao` (copiado para `Contrato.valor_mensal`); `resources.propagar_valor` reajusta o aluguel ativo quando o valor do imóvel muda.
- **Prédio com unidades**: campos extras `apartamentos_novos`/`lojas_novas`/`vagas_novas` (tipo `lista`, `services/unidades.parse_lista`: `101, 102`, `101-110`) + `aluguel_*` criam unidades em `criar_unidades`.
- **Pagamentos**: `forma_pagamento`/`recebido_por` são `choice` com listas fixas em `models.FORMAS_PAGAMENTO`/`RECEBEDORES`. `Pagamento.faltante` abate pagamentos anteriores do mesmo contrato+competência. `crud.sugestao_pagamento` alimenta o pré-preenchimento do valor em `static/app.js`. `Pagamento.competencia` é sempre dia 1.
- **Relatórios**: `gestao/services/relatorio.py` — `dados_mes` (recebido por `data_pagamento`, despesas, pendências do mês, considerando baixa), `serie_meses` (gráfico), `debitos(hoje)` (meses vencidos não quitados desde o início; usa o `valor_mensal` atual; ignora mês cujo vencimento é anterior ao início do aluguel), `gerar_pdf` (reportlab) e `gerar_xlsx` (openpyxl).
- **Fechamento por pessoa**: `Pagamento.recebido_por` e `Despesa.pago_por` (listas fixas em `models.RECEBEDORES`; valores fora da lista/nulos caem em `NAO_INFORMADO`). `relatorio.fechamento(ano, mes)` agrega por pessoa (por forma de pagamento, despesas, saldo = recebido − despesas) e alimenta `/relatorios/fechamento` (+ `.pdf`/`.xlsx`: `gerar_pdf_fechamento`, `gerar_xlsx_fechamento`); a soma das pessoas bate com `dados_mes`.
- **PDFs**: `gestao/services/pdf.py` concentra o layout (A4, faixa no topo, rodapé "Página X de Y", `tabela()` com células `Paragraph` que quebram linha e larguras proporcionais que somam `LARGURA`, linhas de total em destaque com `NOSPLIT`, `cartoes()`, `secao()` com `CondPageBreak`). `relatorio.gerar_pdf`/`gerar_pdf_fechamento` só montam os dados. Para inspecionar visualmente: `pymupdf` (dev) renderiza as páginas em PNG.
- **Filtro por pessoa no Início**: `relatorio.dados_mes(ano, mes, pessoa)` e `serie_meses(..., pessoa=)` filtram pagamentos por `recebido_por` e despesas por `pago_por` (`pessoa_valida` descarta nomes fora de `RECEBEDORES`); pendências/ocupação não mudam. Rota `/?pessoa=Fagner`.
- **Auth**: login valida direto na API REST do Supabase Auth (`gestao/auth.py`) e guarda só o e-mail na sessão. `before_app_request` exige login em tudo; `LOGIN_DISABLED` só nos testes. CSRF próprio (`_csrf`; desligado com `TESTING`).
- **Banco**: Flask-SQLAlchemy; com Postgres usa `NullPool` (pooler do Supabase, porta 6543). Na Vercel o app **recusa** iniciar sem `SECRET_KEY`, sem `DATABASE_URL`/`POSTGRES_URL` Postgres ou com host de conexão direta (`db.*.supabase.co`, IPv6). `normalizar_db_url` remove o parâmetro `supa`. Variáveis: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` (fallback `SUPABASE_PUBLISHABLE_KEY`), `SECRET_KEY`. RLS ligado sem policies (app conecta como `postgres`).
- **Layout**: `static/app.css` (variáveis em `:root`), `static/app.js` (menu mobile, modal de baixa, busca, gráfico Chart.js, sugestão de valor). `Badge(texto, cor)` em coluna vira etiqueta. Endereços antigos (`/c/apartamentos|vagas|contratos/`) redirecionam.
