# Bot J Mendes

Documentação do fluxo **J Mendes**: ingestão por planilha no SharePoint, fila em SQL Server, worker e automação no **KMM (Internet Explorer)**. Detalhes do driver: [KMM e Selenium (Internet Explorer)](../kmm-selenium-internet-explorer.md).

Documentação relacionada: [Arcelor](arcelor.md), [Belgo](belgo.md), [Operação, ambiente e suporte](../operacao-ambiente-agendamento-suporte.md).

---

## Finalidade

Emitir **contrato** no KMM (fluxo **Repom Frete A**) e realizar **quitação** (`payment`) a partir de linhas importadas de planilha, com gestão (**Freto** ou **Levo**) definida por coluna.

---

## Ingestão (publisher)

Arquivo: [`src/bots/jmendes/publisher.py`](../../src/bots/jmendes/publisher.py) (`run`).

1. Envia e-mail de início para **`JMN_RECIPIENTS`**.
2. Baixa o ficheiro Excel do SharePoint com [`sharepoint.get_items`](../../src/shared/sharepoint.py) (navegador **Chrome**, pasta local `excel_files/`).
3. Lê a folha indicada por `JMN_EXCEL_SHEET_NAME`, remove a coluna `Data` se existir, renomeia colunas para o esquema da tabela e define `STATUS_ = Pendente`.
4. Remove linhas sem `TBE`; insere com `insert_ignore_df` em **`complementar_jmendes`** com chave **`TBE`**.
5. Em falha de download ou erro não tratado, envia e-mail de conclusão com mensagem de diagnóstico.

---

## Fila no banco

- **Tabela:** `Ergondata_Robo.dbo.complementar_jmendes`
- **Leitura:** `get_data` **sem** `date_range` → `CRIADO_EM >=` início do dia atual, `RETENTATIVA < 3`, `STATUS_ <> 'OK'`.

---

## Worker

Arquivo: [`src/bots/jmendes/worker.py`](../../src/bots/jmendes/worker.py).

Fluxo análogo ao Arcelor/Belgo: `Processando` → `process()` → `OK` + `FINALIZADO_EM` ou estados de erro (`Falha no KMM`, `Falha de lentidão KMM`, `Falha no KMM não mapeada`).

Pós-processamento: **`Retorno JMendes.xlsx`** em `src/bots/jmendes/output/` e e-mail para **`JMN_RECIPIENTS`**.

**Constante de fila:** `QUEUE_NAME = "jmendes"`.

---

## Processamento KMM

Arquivo: [`src/bots/jmendes/kmm_process.py`](../../src/bots/jmendes/kmm_process.py).

- **Modelo:** [`JMNItemProcess`](../../src/bots/jmendes/models.py) — placa, motorista, TBE, natureza, operação, rota, cartão, remetente, destinatário, valor contrato, `GESTAO` → `management`, contrato opcional.
- Uma instância **`KMMActions(service='JMendes')`** (sem `evidence_dir` customizado no código atual → pasta padrão `output/evidence` relativa ao `IEDriverConfig`).
- `login` com `KMM_JMN_*` e `management=queue_item.management`.
- Se não houver contrato no registo: `emitting_contract_repomfretea` com `JMN_LIBERATION_USER` e `control_number=21` fixo no código.
- Depois: `kmm.payment(...)`; falha levanta `KMMPaymentError`.

---

## Variáveis de ambiente

| Variável | Uso |
|----------|-----|
| `KMM_URL` | URL do KMM |
| `KMM_JMN_USERNAME` / `KMM_JMN_PASSWORD` | Credenciais KMM J Mendes |
| `JMN_LIBERATION_USER` | Utilizador de liberação na emissão do contrato |
| `JMN_SHAREPOINT_URL` | URL para download via Selenium Chrome |
| `JMN_EXCEL_FILE_NAME` | Nome do ficheiro esperado após download |
| `JMN_EXCEL_SHEET_NAME` | Nome da folha Excel |
| `JMN_RECIPIENTS` | E-mails (publisher + worker) |

---

## Artefatos

| Caminho / artefato | Descrição |
|--------------------|-----------|
| `excel_files/<JMN_EXCEL_FILE_NAME>` | Cópia local após SharePoint |
| `src/bots/jmendes/output/Retorno JMendes.xlsx` | Planilha de retorno do worker |
| `output/evidence/` (raiz do CWD) | Evidências IE padrão do `KMMIEDriver`, se não sobrescrito |

---

## Referência rápida de código

| Componente | Arquivo |
|------------|---------|
| Publisher | [`publisher.py`](../../src/bots/jmendes/publisher.py) |
| Worker | [`worker.py`](../../src/bots/jmendes/worker.py) |
| Processo KMM | [`kmm_process.py`](../../src/bots/jmendes/kmm_process.py) |
| Modelo | [`models.py`](../../src/bots/jmendes/models.py) |
| Download SharePoint | [`sharepoint.py`](../../src/shared/sharepoint.py) |
