# Bot Belgo

Documentação do fluxo **Belgo**: ingestão a partir do **portal BBA** (Chrome + Mechanize), fila em SQL Server, worker e automação **KMM em duas fases (Fretolog e Levolog)** com envio opcional de **XML** ao portal. O KMM usa **Internet Explorer**; o portal BBA usa **Chrome**. Ver [KMM e Selenium (Internet Explorer)](../kmm-selenium-internet-explorer.md).

Documentação relacionada: [Arcelor](arcelor.md), [J Mendes](jmendes.md), [Operação, ambiente e suporte](../operacao-ambiente-agendamento-suporte.md).

---

## Finalidade

Emitir **CTes de complemento** (Fretolog e, quando aplicável, Levolog), obter **XML**, emitir **contrato**, **quitar**, e anexar/atualizar informação no portal BBA (`BelgoXML.insert_xml`) conforme flags e dados do incidente.

---

## Ingestão (publisher)

Arquivo: [`src/bots/belgo/publisher.py`](../../src/bots/belgo/publisher.py).

Fluxo pretendido:

1. Instanciar `BelgoPortal` (em [`bba_portal.py`](../../src/bots/belgo/bba_portal.py)) e chamar `get_incidents_in_bba_portal()` para obter lista de incidentes.
2. Normalizar datas e colunas; `STATUS_ = Pendente`.
3. Inserir em **`complementar_belgo2`** com `insert_ignore_df` e `unique_keys=['CTE_FRETOLOG']`.

**Nota de implementação:** em `Main.__init__` o código comenta a criação de `DB()`, mas `get_incidents` usa `self.db.insert_ignore_df`. Para o publisher funcionar como `__main__`, é necessário inicializar `self.db = DB()` (ou equivalente) antes de `insert_ignore_df`. A ingestão está documentada pelo comportamento esperado; ajuste o código se o publisher for executado em produção.

---

## Fila no banco

- **Tabela:** `Ergondata_Robo.dbo.complementar_belgo2`
- **Leitura no worker:** `get_data(..., date_range=True)` → `CRIADO_EM >=` **hoje − 15 dias** (meia-noite), mais `RETENTATIVA < 3` e `STATUS_ <> 'OK'`.  
  Isto alarga a janela em relação ao Arcelor/J Mendes (apenas dia corrente).

---

## Worker

Arquivo: [`src/bots/belgo/worker.py`](../../src/bots/belgo/worker.py).

Mesmo padrão: `Processando`, `process()`, `OK` / mensagens de erro. `KMMProcess` grava `Falha no KMM. <NomeDaExcecao>`.

Excel: **`Retorno Belgo.xlsx`** em `src/bots/belgo/output/`; e-mail **`BELGO_RECIPIENTS`**.

**Constante de fila:** `QUEUE_NAME = "belgo"`.

---

## Processamento KMM e portal BBA

Arquivo: [`src/bots/belgo/kmm_process.py`](../../src/bots/belgo/kmm_process.py). Modelo: [`BelgoItemProcess`](../../src/bots/belgo/models.py).

### Fretolog

- `KMMActions(service='Belgo Freto', evidence_dir=...)` com evidências sob a raiz do projeto em `output/evidence` (via `BASE_DIR`).
- Login com `KMM_BELGO_*`; `belgo_load_user_profile` com lotação Fretolog.
- `emitting_cte` com `belgo=True`, `taxes=True`, número de incidentes.
- Atualiza `CTE_FRETOLOG_COMPLEMENTAR` e `DATA_EMISSAO_CTE_FRETO` quando emite novo complemento.
- `get_xml` para obter ficheiro XML do complemento.
- Se **não** existir `levo_cte`: contrato `emitting_contract_repomfreted` (utilizador `KMM_CONTRACT_LIBERATION_USER`, controlo `KMM_BELGO_CONTROL_NUMBER`), `payment`; se `edicao_caso` for falso/absente, `BelgoXML().insert_xml(...)` e retorno.
- **Atenção:** o ficheiro regista URL/username/password em log (linha com `log.info`); em produção convém remover ou mascarar credenciais.

### Levolog

- Segunda sessão `KMMActions(service='Belgo Levo')`; `arcelor_load_user_profile` com `center=queue_item.levo_cte` (identificador usado como centro na automação).
- Complemento Levolog com `markup=0.98`, `belgo=True`.
- Contrato com `submotive` e `KMM_BELGO_LIBERATION_USER` / `KMM_BELGO_CONTROL_NUMBER`.
- `payment` com `management='levolog'`.
- Se não for edição de caso: `BelgoXML().insert_xml`; caso contrário atualiza `EDICAO_CASO` no banco.

### Portal BBA (não IE)

[`bba_portal.py`](../../src/bots/belgo/bba_portal.py): **Chrome** (WebDriver Manager) para páginas dinâmicas; **Mechanize** para login/formulários legados. Variáveis `BBA_PORTAL_*`, URLs de incidentes/transporte, e constantes de taxa/veículo (`TAX1`–`TAX4`, `TRUCK`, etc.) para cálculos no UI.

---

## Variáveis de ambiente

### KMM / worker

| Variável | Uso |
|----------|-----|
| `KMM_URL` | URL do KMM |
| `KMM_BELGO_USERNAME` / `KMM_BELGO_PASSWORD` | Credenciais Belgo no KMM |
| `KMM_CONTRACT_LIBERATION_USER` | Liberação contrato (etapa Fretolog) |
| `KMM_BELGO_CONTROL_NUMBER` | Número de controle (inteiro) |
| `KMM_BELGO_LIBERATION_USER` | Liberação na etapa Levolog |
| `BELGO_RECIPIENTS` | E-mail do worker |

### Portal BBA (publisher / XML)

`BBA_PORTAL_LOGIN_URL`, `BBA_PORTAL_USERNAME`, `BBA_PORTAL_PASSWORD`, `BBA_PORTAL_INCIDENTS_URL`, `BBA_PORTAL_EDIT_INCIDENTS_URL`, `BBA_PORTAL_TRANSPORT_URL`, e variáveis de taxa/veículo usadas em `bba_portal.py` (`TAX1`–`TAX4`, `TRUCK`, `TRUCK_CORRIGIDO`, `CARRETA`, `CARRETA_CORRIGIDA`, etc.).

---

## Artefatos

| Caminho / artefato | Descrição |
|--------------------|-----------|
| `output/evidence` (raiz do projeto) | Evidências KMM Belgo (Freto/Levo conforme `evidence_dir`) |
| `src/bots/belgo/output/Retorno Belgo.xlsx` | Retorno do worker |
| Pastas `downloads` / evidências locais em `bba_portal.py` | Chrome e downloads Belgo portal |

---

## Referência rápida de código

| Componente | Arquivo |
|------------|---------|
| Worker | [`worker.py`](../../src/bots/belgo/worker.py) |
| Processo KMM | [`kmm_process.py`](../../src/bots/belgo/kmm_process.py) |
| Publisher | [`publisher.py`](../../src/bots/belgo/publisher.py) |
| Portal BBA | [`bba_portal.py`](../../src/bots/belgo/bba_portal.py) |
| Modelo | [`models.py`](../../src/bots/belgo/models.py) |
