# Bot Arcelor

Documentação operacional do fluxo **Arcelor**: ingestão (Pipefy + portal Freto), fila em SQL Server, worker e automação no **KMM via Internet Explorer** (wrapper `KMMIEDriver`). Para detalhes do driver IE, ver [KMM e Selenium (Internet Explorer)](../kmm-selenium-internet-explorer.md).

Documentação relacionada: [J Mendes](jmendes.md), [Belgo](belgo.md), [Operação, ambiente e suporte](../operacao-ambiente-agendamento-suporte.md).

---

## Finalidade

Automatizar o ciclo de **complemento de CTe**, **emissão de contrato** e **quitação** no sistema KMM para casos Arcelor, com filas orquestradas no Pipefy (movimentação de cards entre fases) quando aplicável.

---

## Ingestão (publisher)

Entrada principal: [`src/bots/arcelor/publisher.py`](../../src/bots/arcelor/publisher.py) (`Main.run`).

1. **Pipefy** — [`src/bots/arcelor/pipefy_handler.py`](../../src/bots/arcelor/pipefy_handler.py): OAuth2 client credentials; leitura dos cards/incidentes via API GraphQL.
2. **Portal Freto** — [`src/bots/arcelor/freto_portal.py`](../../src/bots/arcelor/freto_portal.py): navegador **Chrome** para enriquecer dados (ex.: motorista, CTes) a partir do calendário/portal configurado por variáveis de ambiente.
3. Validações mínimas (ex.: presença de motorista e CTe Fretolog); cards podem ser movidos para a fase **CTe Freto** antes da gravação no banco.
4. Os registros válidos são normalizados (renomeação de colunas) e inseridos com `DB().insert_ignore_df` na tabela **`complementar_arcelor`**, chave de deduplicação **`CTE_FRETOLOG`**.

Ao final da execução, o publisher encerra processos de **Chrome**, **Edge** e **IEDriverServer** via `taskkill` (limpeza de sessões).

---

## Fila no banco

- **Tabela:** `Ergondata_Robo.dbo.complementar_arcelor`
- **Leitura pelo worker:** [`DB.get_data`](../../src/shared/db_handler/db_handler.py) **sem** `date_range` → apenas registros com `CRIADO_EM` **a partir da meia-noite do dia corrente**, além de:
  - `RETENTATIVA < 3`
  - `STATUS_ <> 'OK'`

---

## Worker

Arquivo: [`src/bots/arcelor/worker.py`](../../src/bots/arcelor/worker.py).

Para cada linha retornada:

1. Incrementa `RETENTATIVA` e define `STATUS_ = 'Processando'`.
2. Monta `ArcelorItemProcess` e chama `process()` em [`kmm_process.py`](../../src/bots/arcelor/kmm_process.py).
3. Em sucesso: `STATUS_ = 'OK'` e preenche `FINALIZADO_EM`.
4. Erros mapeados: `KMMProcess` → `Falha no KMM`; `RuntimeError` (lentidão) → `Falha de lentidão KMM`; demais → `Falha no KMM não mapeada`.

Após o lote: gera **`Retorno Arcelor.xlsx`** em `src/bots/arcelor/output/` (via `create_return_excel`) e envia e-mail para **`ARCELOR_RECIPIENTS`** (com anexo se houver planilha gerada, ou mensagem informando ausência de casos).

**Constante de fila:** `QUEUE_NAME = "arcelor"` (útil para orquestradores externos).

---

## Processamento KMM

Arquivo: [`src/bots/arcelor/kmm_process.py`](../../src/bots/arcelor/kmm_process.py).

- **Modelo:** [`ArcelorItemProcess`](../../src/bots/arcelor/models.py) (CTes Fretolog/Levolog, valores, filial, `card_id` Pipefy, complementos já existentes, contrato, etc.).
- **Sessão Fretolog (`KMMActions` com `service='Arcelor Freto'`)**  
  - Login KMM com usuário/senha Arcelor; perfil `arcelor_load_user_profile` para gestão **freto**.  
  - Evidências IE: `evidence_dir` = `src/bots/arcelor/output/evidence`.  
  - Emite complemento Fretolog se ainda não existir; atualiza `CTE_FRETOLOG_COMPLEMENTAR` no banco.  
  - Se **não** houver `CTE_LEVOLOG`: emite contrato (se necessário), move cards no Pipefy, executa **quitação** e **Liberar**; encerra com sucesso **sem** abrir sessão Levolog.
- **Sessão Levolog (`KMMActions` com `service='Arcelor Levo'`)** — quando há CTe Levolog:  
  - Login e perfil **levo**; complemento Levolog (markup 0,98); contrato na etapa Levo com `KMM_ARCELOR_LIBERATION_USER` e `KMM_ARCELOR_CONTROL_NUMBER`; movimentação Pipefy e quitação.

Integração Pipefy: classe `API()` — `move_card` em fases como Contrato, CTe Levo, Quitação de Contrato, Liberar (conforme o ramo do fluxo).

---

## Variáveis de ambiente

| Variável | Uso |
|----------|-----|
| `KMM_URL` | URL de login do KMM |
| `KMM_ARCELOR_USERNAME` / `KMM_ARCELOR_PASSWORD` | Credenciais KMM Arcelor |
| `KMM_CONTRACT_LIBERATION_USER` | Usuário de liberação (contrato Fretolog) |
| `KMM_ARCELOR_CONTROL_NUMBER` | Número de controle (inteiro) na emissão de contrato |
| `KMM_ARCELOR_LIBERATION_USER` | Liberação na etapa Levolog |
| `PIPEFY_AUTH_URL` | Token OAuth Pipefy |
| `PIPEFY_CLIENT_ID` / `PIPEFY_CLIENT_SECRET` | Client credentials |
| `FRETO_PORTAL_URL` / `FRETO_PORTAL_USERNAME` / `FRETO_PORTAL_PASSWORD` | Portal Freto (publisher) |
| `FRETO_PORTAL_CALENDAR` | Calendário/agenda no portal |
| `TAX1`–`TAX4` | Cálculos no portal Freto (quando aplicável) |
| `ARCELOR_RECIPIENTS` | Destinatários do e-mail do worker |

Credenciais e URLs devem estar no `.env` na raiz do projeto (carregado por `load_dotenv` nos módulos).

---

## Artefatos

| Caminho / artefato | Descrição |
|--------------------|-----------|
| `src/bots/arcelor/output/Retorno Arcelor.xlsx` | Export do dia após execução do worker |
| `src/bots/arcelor/output/evidence/` | Screenshots/HTML do KMM na sessão Fretolog (quando `evidence_dir` customizado) |
| E-mail | Resumo e anexo da planilha de retorno |

---

## Referência rápida de código

| Componente | Arquivo |
|------------|---------|
| Worker | [`worker.py`](../../src/bots/arcelor/worker.py) |
| Processo KMM | [`kmm_process.py`](../../src/bots/arcelor/kmm_process.py) |
| Publisher | [`publisher.py`](../../src/bots/arcelor/publisher.py) |
| Pipefy | [`pipefy_handler.py`](../../src/bots/arcelor/pipefy_handler.py) |
| Portal Freto (Chrome) | [`freto_portal.py`](../../src/bots/arcelor/freto_portal.py) |
| Modelo Pydantic | [`models.py`](../../src/bots/arcelor/models.py) |
