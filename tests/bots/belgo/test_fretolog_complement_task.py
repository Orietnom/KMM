from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ergon.connector import Transaction

from src.bots.belgo.tasks.complementar_fretolog.connectors import (
    BelgoFretologSQLConnector,
)
from src.bots.belgo.tasks.complementar_fretolog.schemas import (
    FretologComplementInput,
)
from src.bots.belgo.tasks.complementar_fretolog.services import (
    BelgoPlatformStateService,
)
from src.bots.belgo.tasks.complementar_fretolog.task import (
    FRETOLOG_COMPLEMENT_PHASE_ID,
    TaskBelgoFretologComplement,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions
from src.shared.db_handler.db_handler import DB


def sql_payload(**changes):
    payload = {
        "ID": 42,
        "ID_INCIDENTE": "163697",
        "FILIAL": "FRETO LOG - MATRIZ",
        "LOTACAO_FRETOLOG": "MATRIZ",
        "CTE_FRETOLOG": "12345",
        "SERIE_FRETOLOG": "1",
        "VALOR_CTE": "100.00",
        "N_INCIDENTES": 1,
        "CTE_FRETOLOG_COMPLEMENTAR": None,
    }
    payload.update(changes)
    return payload


class FakeDB:
    def __init__(self, events):
        self.events = events
        self.rows = [sql_payload()]
        self.saved = []
        self.updates = []

    def claim_belgo_fretolog_cases(self, limit):
        self.events.append(("sql-fetch", limit))
        return self.rows

    def get_belgo_case_by_row_id(self, row_id):
        return self.rows[0] if row_id == 42 else None

    def save_belgo_fretolog_complement(self, **fields):
        self.events.append(("sql-save", fields["cte_number"]))
        self.saved.append(fields)

    def update(self, **fields):
        self.updates.append(fields)

    def close(self):
        return None


class FakePlatformState:
    def __init__(self, events):
        self.events = events
        self.results = []
        self.numbers = []

    def find_card_id(self, incident_id):
        self.events.append(("find-card", incident_id))
        return "card-1"

    def route_to(self, card_id, phase_id):
        self.events.append(("route", card_id, phase_id))

    def update_results(self, card_id, **fields):
        self.events.append(("platform-update", card_id))
        self.results.append((card_id, fields))

    def update_cte_number(self, card_id, cte_number):
        self.numbers.append((card_id, cte_number))


class FakeKMM:
    def __init__(self, events):
        self.events = events
        self.emission_kwargs = None

    def __enter__(self):
        self.events.append(("kmm-enter",))
        return self

    def __exit__(self, *args):
        self.events.append(("kmm-exit",))

    def login(self, *, params, management):
        self.events.append(("login", management, params.username))

    def belgo_load_user_profile(self, *, user, management, lotation):
        self.events.append(("profile", management, lotation))

    def emitting_cte(self, **kwargs):
        self.emission_kwargs = kwargs
        self.events.append(("emit", kwargs["management"]))
        return CTeEmissionResult(number="98765", net_value=88.75)


def build_task(monkeypatch):
    for name, value in {
        "KMM_URL": "http://kmm",
        "KMM_BELGO_USERNAME": "robot",
        "KMM_BELGO_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    events = []
    db = FakeDB(events)
    sql = BelgoFretologSQLConnector(db=db)
    platform = FakePlatformState(events)
    kmm = FakeKMM(events)
    worker = TaskBelgoFretologComplement.__new__(TaskBelgoFretologComplement)
    worker.sql_connector = sql
    worker.platform_state_service = platform
    worker.kmm_factory = lambda **kwargs: kmm
    return worker, sql, platform, kmm, events


def test_sql_connector_fetches_claimed_database_rows():
    events = []
    connector = BelgoFretologSQLConnector(db=FakeDB(events))

    transactions = connector.fetch_transactions(7)

    assert events == [("sql-fetch", 7)]
    assert transactions[0].id == "42"
    assert transactions[0].payload["ID_INCIDENTE"] == "163697"


def test_sql_claim_uses_worker_filters():
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = []
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    db = object.__new__(DB)
    db.engine = engine

    assert db.claim_belgo_fretolog_cases(10) == []

    statement = str(connection.execute.call_args.args[0])
    assert "CRIADO_EM >= :dt_min" in statement
    assert "RETENTATIVA < 5" in statement
    assert "STATUS_ <> 'OK'" in statement
    assert "CTE_FRETOLOG_COMPLEMENTAR IS NULL" in statement
    assert "CTE_FRETOLOG_COMPLEMENTAR = ''" in statement
    assert "RETENTATIVA = RETENTATIVA + 1" in statement


def test_sql_adapter_maps_database_columns():
    item = FretologComplementInput.from_sql_payload(sql_payload())

    assert item.row_id == 42
    assert item.incident_id == "163697"
    assert item.freto_cte == "12345"
    assert item.cte_value == 100.0


def test_routes_card_emits_persists_sql_then_updates_platform(monkeypatch):
    worker, sql, platform, kmm, events = build_task(monkeypatch)
    transaction = Transaction(id="42", payload=sql_payload())

    result = worker.process_transaction(transaction)

    assert result.cte_number == "98765"
    assert events[:2] == [
        ("find-card", "163697"),
        ("route", "card-1", FRETOLOG_COMPLEMENT_PHASE_ID),
    ]
    assert events.index(("sql-save", "98765")) < events.index(
        ("platform-update", "card-1")
    )
    assert kmm.emission_kwargs["management"] == "freto"
    assert kmm.emission_kwargs["taxes"] is True
    assert kmm.emission_kwargs["belgo"] is True
    assert kmm.emission_kwargs["return_details"] is True
    assert sql.db.saved[0]["row_id"] == 42
    assert platform.results == [(
        "card-1",
        {"cte_number": "98765", "net_value": 88.75},
    )]


def test_existing_sql_cte_reconciles_platform_without_kmm(monkeypatch):
    worker, _sql, platform, _kmm, _events = build_task(monkeypatch)
    worker.kmm_factory = lambda **kwargs: pytest.fail("KMM não deveria ser aberto")

    result = worker.process_transaction(
        Transaction(
            id="42",
            payload=sql_payload(CTE_FRETOLOG_COMPLEMENTAR="77777"),
        )
    )

    assert result.resumed_from_sql is True
    assert platform.numbers == [("card-1", "77777")]


def test_failure_marks_sql_status(monkeypatch):
    worker, sql, _platform, _kmm, _events = build_task(monkeypatch)
    transaction = Transaction(id="42", payload=sql_payload())
    error = RuntimeError("falha")

    worker.handle_process_exception(transaction, error)

    assert sql.db.updates == [{
        "table": "complementar_belgo2",
        "column": "STATUS_",
        "value": "Falha no KMM. RuntimeError",
        "id": 42,
    }]


def test_platform_state_requires_exactly_one_card():
    item = {
        "id": "card-1",
        "field_values": [{"field_id": "field-id", "value": "163697"}],
    }
    workflow = MagicMock()
    workflow.fields.return_value = SimpleNamespace(
        items=[{"id": "field-id", "name": "ID"}],
        total=1,
    )
    workflow.items.return_value = SimpleNamespace(items=[item], total=1)
    client = MagicMock()
    client.workflows.workflow.return_value = workflow
    service = BelgoPlatformStateService(client=client)

    assert service.find_card_id("163697") == "card-1"

    workflow.items.return_value = SimpleNamespace(items=[], total=0)
    with pytest.raises(RuntimeError, match="encontrados 0"):
        service.find_card_id("999")

    workflow.items.return_value = SimpleNamespace(items=[item, item], total=2)
    with pytest.raises(RuntimeError, match="encontrados 2"):
        service.find_card_id("163697")


def test_emitting_cte_can_return_number_and_net_value(monkeypatch):
    driver = MagicMock()
    driver.safe_get_attribute.return_value = "90.00"
    driver.wait_alert.return_value = SimpleNamespace(
        text="CT-e emitido",
        accept=lambda: None,
    )
    driver.switch_to_window.return_value = True
    driver.safe_get_text.return_value = "98765"
    actions = KMMActions(service="test", driver=driver)
    monkeypatch.setattr(actions, "quick_access", lambda *_args: None)
    monkeypatch.setattr(actions, "_status_cte", lambda *_args: True)
    monkeypatch.setattr(actions, "_get_taxes", lambda: 10.0)
    monkeypatch.setattr(actions, "_click_on_negotiation_menu", lambda: None)
    monkeypatch.setattr(
        "src.kmm.services.kmm_actions.time.sleep",
        lambda *_args: None,
    )

    result = actions.emitting_cte(
        cte="12345",
        serie="1",
        cte_value=100.0,
        management="freto",
        taxes=True,
        return_details=True,
    )

    assert result == CTeEmissionResult(number="98765", net_value=90.0)
