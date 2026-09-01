from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from ergon.connector import Transaction
from ergon.connector.ergon_platform import ErgonPlatformProducerConfig

from src.bots.belgo.tasks.publisher.connectors import DryRunErgonPlatformConnector
from src.bots.belgo.tasks.publisher.idempotency import (
    BelgoIdempotencyLedger,
    ClaimState,
)
from src.bots.belgo.tasks.publisher.schemas import (
    DEFAULT_PLATFORM_FIELD_MAP,
    WORKFLOW_TO_SOURCE_FIELD,
    BelgoIncident,
    BelgoPortalResult,
    CaptureRoute,
)
from src.bots.belgo.tasks.publisher.task import TaskBelgoPublisher


def complete_incident(**changes) -> BelgoIncident:
    payload = {
        "id": "123",
        "center": "FRETO LOG - MATRIZ",
        "transport": "TR-1",
        "subreason": "DESCARGA",
        "cte_value": "100.00",
        "contract_value": "80.00",
        "driver_value": 90.00,
        "nf": "456",
        "cte_fretolog_code": "789",
        "serie_fretolog": "1",
        "date": "01/09/2026",
        "freto_lot": "MATRIZ",
        "number_of_incidents": 1,
    }
    payload.update(changes)
    return BelgoIncident.model_validate(payload)


class FakeDB:
    def __init__(self, existing_ids=(), events=None) -> None:
        self.records = []
        self.existing_ids = set(existing_ids)
        self.events = events
        self.fail_insert = False

    def get_existing_belgo_incident_ids(self):
        return self.existing_ids

    def insert_ignore_df(self, *, table, df, unique_keys):
        if self.events is not None:
            self.events.append("sql")
        if self.fail_insert:
            raise RuntimeError("SQL indisponível")
        self.records.extend(df.to_dict(orient="records"))
        return 1


class FakeItems:
    def __init__(self) -> None:
        self.items = {}
        self.updates = []
        self.routes = []
        self.operations = []
        self.route_error_after_success = False

    def get(self, item_id):
        return self.items[item_id]

    def update(self, item_id, **fields):
        self.updates.append((item_id, fields))
        self.operations.append(("update", set(fields.get("field_values", {}))))
        self.items[item_id].update(fields)

    def route(self, item_id, *, to_phase_id):
        self.routes.append((item_id, to_phase_id))
        self.operations.append(("route", to_phase_id))
        self.items[item_id]["phase_id"] = to_phase_id
        if self.route_error_after_success:
            raise TimeoutError("resposta da rota perdida")


class FakeConnector:
    def __init__(self, created_id="card-1", error: Exception | None = None, events=None) -> None:
        self.created_id = created_id
        self.error = error
        self.events = events
        self.transactions = []
        self.items_api = FakeItems()
        self.client = SimpleNamespace(
            workflows=SimpleNamespace(items=self.items_api)
        )

    def dispatch_transactions(self, transactions):
        if self.events is not None:
            self.events.append("dispatch")
        self.transactions.extend(transactions)
        if self.error:
            raise self.error
        self.items_api.items[self.created_id] = {
            "id": self.created_id,
            "phase_id": transactions[0].metadata["phase_id"],
        }
        return [self.created_id]


class FakePortal:
    def __init__(self) -> None:
        self.skip_ids = None

    def capture(self, skip_ids):
        self.skip_ids = skip_ids
        return BelgoPortalResult()


def build_task(tmp_path: Path, connector: FakeConnector):
    publisher = TaskBelgoPublisher.__new__(TaskBelgoPublisher)
    publisher.processable_connector = connector
    publisher.pending_connector = connector
    publisher.db_service = FakeDB()
    publisher._ledger = BelgoIdempotencyLedger(tmp_path / "ledger.sqlite3")
    publisher._failures = []
    return publisher


def test_processable_contract_maps_sql_and_card_fields():
    incident = complete_incident(
        cte_levolog_code="987",
        serie_levolog="2",
        levo_lot="FILIAL SP",
    )

    assert incident.route is CaptureRoute.PROCESSABLE
    assert incident.to_sql_record()["ID_INCIDENTE"] == "123"
    assert incident.to_sql_record()["STATUS_"] == "Pendente"
    assert incident.to_card_fields()["ID"] == "123"
    assert incident.to_card_fields()["Transporte"] == "TR-1"
    assert set(incident.to_card_fields()) == set(DEFAULT_PLATFORM_FIELD_MAP.values())


def test_pending_contract_sends_only_global_workflow_fields():
    incident = BelgoIncident(
        id="124",
        transport="TR-2",
        subreason="DESCARGA",
        cte_value="100.00",
        driver_value=90.00,
        error_reasons=["NF ausente"],
    )

    assert incident.to_card_fields() == {
        "ID": "124",
        "Transporte": "TR-2",
        "Submotivo": "DESCARGA",
    }


def test_real_portal_payload_accepts_numeric_driver_value():
    incident = complete_incident(
        id="162490",
        cte_value="1024.82",
        contract_value="1024.82",
        driver_value=1053.31,
        nf="000058399",
    )

    assert incident.driver_value == 1053.31
    assert incident.to_sql_record()["VALOR_MOTORISTA"] == 1053.31
    assert incident.to_card_fields()["Valor Motorista"] == 1053.31


def test_pending_contract_keeps_available_data_out_of_sql():
    incident = BelgoIncident(
        id="124",
        transport="TR-2",
        subreason="DESCARGA",
        error_reasons=["Documento Viagem ausente"],
    )

    assert incident.route is CaptureRoute.PENDING
    assert "Documento Viagem ausente" in incident.error_reasons
    with pytest.raises(ValueError):
        incident.to_sql_record()


def test_workflow_relation_registers_fields_without_producer_source():
    assert WORKFLOW_TO_SOURCE_FIELD["ID"] == "ID_INCIDENTE"
    assert WORKFLOW_TO_SOURCE_FIELD["N CT-e Complementar Fretolog"] is None
    assert WORKFLOW_TO_SOURCE_FIELD["Valor Complementar Levolog"] is None
    assert WORKFLOW_TO_SOURCE_FIELD["N Contrato"] is None
    assert WORKFLOW_TO_SOURCE_FIELD["XML"] is None


def test_ledger_allows_only_one_claim_per_incident(tmp_path):
    ledger = BelgoIdempotencyLedger(tmp_path / "ledger.sqlite3")

    first = ledger.claim("123", "processable")
    second = ledger.claim("123", "processable")
    created = ledger.mark_created("123", "card-1")

    assert first.state is ClaimState.CLAIMED
    assert second.state is ClaimState.PENDING
    assert created.state is ClaimState.CREATED
    assert ledger.created_incident_ids() == {"123"}


def test_processable_creates_card_before_writing_sql(tmp_path):
    events = []
    connector = FakeConnector(events=events)
    publisher = build_task(tmp_path, connector)
    publisher.db_service = FakeDB(events=events)
    incident = complete_incident()
    transaction = Transaction(
        id=incident.id,
        payload=incident,
        metadata={"phase_id": "processable"},
    )

    result = publisher.handle_prepare_success(
        transaction,
        publisher.prepare_transaction(transaction),
    )

    assert publisher.db_service.records[0]["ID_INCIDENTE"] == "123"
    assert connector.transactions[0].id == "123"
    assert result.state is ClaimState.CREATED
    assert events == ["dispatch", "sql"]


def test_pending_creates_card_without_sql(tmp_path):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    incident = BelgoIncident(id="124", error_reasons=["NF ausente"])
    transaction = Transaction(
        id=incident.id,
        payload=incident,
        metadata={"phase_id": "pending"},
    )

    publisher.handle_prepare_success(
        transaction,
        publisher.prepare_transaction(transaction),
    )

    assert publisher.db_service.records == []
    assert connector.transactions[0].payload.extra_fields["description"] == "Motivo da pendência:\n- NF ausente"


def test_repeated_pending_updates_same_card_without_duplicate(tmp_path):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    first = BelgoIncident(id="124", error_reasons=["NF ausente"])
    updated = BelgoIncident(
        id="124",
        transport="TR-2",
        error_reasons=["Documento Viagem ausente"],
    )

    for incident in (first, updated):
        transaction = Transaction(
            id=incident.id,
            payload=incident,
            metadata={"phase_id": "pending"},
        )
        publisher.handle_prepare_success(
            transaction,
            publisher.prepare_transaction(transaction),
        )

    assert len(connector.transactions) == 1
    assert connector.items_api.updates[0][0] == "card-1"
    assert connector.items_api.updates[0][1]["field_values"]["Transporte"] == "TR-2"
    assert publisher.db_service.records == []


def test_completed_pending_updates_routes_same_card_and_writes_sql(tmp_path):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    pending = BelgoIncident(id="123", error_reasons=["NF ausente"])
    complete = complete_incident()

    for incident, phase_id in ((pending, "pending"), (complete, "processable")):
        transaction = Transaction(
            id=incident.id,
            payload=incident,
            metadata={"phase_id": phase_id},
        )
        publisher.handle_prepare_success(
            transaction,
            publisher.prepare_transaction(transaction),
        )

    claim = publisher._ledger.inspect("123")
    assert len(connector.transactions) == 1
    assert connector.items_api.routes == [
        ("card-1", "fa0472b7-80c4-47cc-81b0-bd5da388acf1")
    ]
    assert connector.items_api.operations[0] == (
        "update",
        {"ID", "Transporte", "Submotivo"},
    )
    assert connector.items_api.operations[1][0] == "route"
    assert connector.items_api.operations[2][0] == "update"
    assert "Valor CT-e" in connector.items_api.operations[2][1]
    assert connector.items_api.updates[-1][1]["description"] == ""
    assert claim.route == CaptureRoute.PROCESSABLE.value
    assert claim.platform_item_id == "card-1"
    assert publisher.db_service.records[0]["ID_INCIDENTE"] == "123"


def test_sql_retry_reuses_card_already_created(tmp_path):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    publisher.db_service.fail_insert = True
    incident = complete_incident()
    transaction = Transaction(
        id=incident.id,
        payload=incident,
        metadata={"phase_id": "processable"},
    )
    payload = publisher.prepare_transaction(transaction)

    with pytest.raises(RuntimeError, match="SQL indisponível"):
        publisher.handle_prepare_success(transaction, payload)

    publisher.db_service.fail_insert = False
    publisher.handle_prepare_success(transaction, payload)

    assert len(connector.transactions) == 1
    assert publisher.db_service.records[0]["ID_INCIDENTE"] == "123"


def test_route_retry_detects_card_already_in_target_phase(tmp_path):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    pending = BelgoIncident(id="123", error_reasons=["NF ausente"])
    pending_tx = Transaction(id="123", payload=pending, metadata={"phase_id": "pending"})
    publisher.handle_prepare_success(
        pending_tx,
        publisher.prepare_transaction(pending_tx),
    )

    complete = complete_incident()
    complete_tx = Transaction(id="123", payload=complete, metadata={"phase_id": "processable"})
    connector.items_api.route_error_after_success = True
    with pytest.raises(TimeoutError, match="resposta da rota perdida"):
        publisher.handle_prepare_success(
            complete_tx,
            publisher.prepare_transaction(complete_tx),
        )

    connector.items_api.route_error_after_success = False
    publisher.handle_prepare_success(
        complete_tx,
        publisher.prepare_transaction(complete_tx),
    )

    assert len(connector.items_api.routes) == 1
    assert publisher._ledger.inspect("123").route == CaptureRoute.PROCESSABLE.value
    assert publisher.db_service.records[0]["ID_INCIDENTE"] == "123"


def test_definitive_platform_failure_releases_claim_for_retry(tmp_path):
    error = RuntimeError("payload inválido")
    error.status_code = 422
    connector = FakeConnector(error=error)
    publisher = build_task(tmp_path, connector)
    incident = BelgoIncident(id="125", error_reasons=["NF ausente"])
    transaction = Transaction(
        id=incident.id,
        payload=incident,
        metadata={"phase_id": "pending"},
    )

    with pytest.raises(RuntimeError, match="payload inválido"):
        publisher.handle_prepare_success(
            transaction,
            publisher.prepare_transaction(transaction),
        )

    assert publisher._ledger.inspect("125") is None


def test_dry_run_never_writes_processable_incident_to_sql():
    connector = DryRunErgonPlatformConnector(
        ErgonPlatformProducerConfig(workflow_id="workflow", phase_id="phase")
    )
    publisher = TaskBelgoPublisher.__new__(TaskBelgoPublisher)
    publisher.processable_connector = connector
    publisher.pending_connector = connector
    publisher.db_service = FakeDB()
    publisher._ledger = None
    incident = complete_incident()
    transaction = Transaction(
        id=incident.id,
        payload=incident,
        metadata={"phase_id": "processable"},
    )

    publisher.handle_prepare_success(
        transaction,
        publisher.prepare_transaction(transaction),
    )

    assert publisher.db_service.records == []
    assert connector.created_cards[0]["field_values"]["ID"] == "123"


def test_execute_uses_only_sql_ids_to_skip_portal_enrichment(tmp_path, monkeypatch):
    connector = FakeConnector()
    publisher = build_task(tmp_path, connector)
    publisher.db_service = FakeDB(existing_ids={"10", "20", "30"})
    publisher.portal_service = FakePortal()
    publisher._validate_platform_fields = lambda: None
    monkeypatch.setenv("BELGO_IDEMPOTENCY_DB", str(tmp_path / "execute-ledger.sqlite3"))

    assert publisher.execute() == 0
    assert publisher.portal_service.skip_ids == {"10", "20", "30"}


def test_platform_validation_respects_fields_available_in_each_phase(tmp_path):
    processable = FakeConnector()
    pending = FakeConnector()
    processable.list_phase_fields = lambda *args, **kwargs: [
        {"id": f"field-{index}", "name": name}
        for index, name in enumerate(DEFAULT_PLATFORM_FIELD_MAP.values())
    ]
    pending.list_phase_fields = lambda *args, **kwargs: [
        {"id": "field-id", "name": "ID"},
        {"id": "field-transport", "name": "Transporte"},
        {"id": "field-subreason", "name": "Submotivo"},
    ]
    publisher = build_task(tmp_path, processable)
    publisher.pending_connector = pending

    publisher._validate_platform_fields()
