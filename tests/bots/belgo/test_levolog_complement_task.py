from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ergon.connector import Transaction

from src.bots.belgo.tasks.complementar_levolog.connectors import (
    BelgoLevologSQLConnector,
)
from src.bots.belgo.tasks.complementar_levolog.schemas import (
    LevologComplementInput,
)
from src.bots.belgo.tasks.complementar_levolog.task import (
    LEVOLOG_COMPLEMENT_PHASE_ID,
    TaskBelgoLevologComplement,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions
from src.shared.db_handler.db_handler import DB


def sql_payload(**changes):
    payload = {
        "ID": 42,
        "ID_INCIDENTE": "163697",
        "FILIAL": "FRETO LOG - MATRIZ",
        "LOTACAO_LEVOLOG": "FILIAL MG",
        "CTE_LEVOLOG": "57732",
        "SERIE_LEVOLOG": "1",
        "VALOR_CTE": "100.00",
        "N_INCIDENTES": 1,
        "CTE_LEVOLOG_COMPLEMENTAR": None,
    }
    payload.update(changes)
    return payload


class FakeDB:
    def __init__(self, events):
        self.events = events
        self.rows = [sql_payload()]
        self.saved = []
        self.failures = []

    def claim_belgo_levolog_cases(self, limit):
        self.events.append(("sql-fetch", limit))
        return self.rows

    def get_belgo_case_by_row_id(self, row_id):
        return self.rows[0] if row_id == 42 else None

    def save_belgo_levolog_complement(self, **fields):
        self.events.append(("sql-save", fields["cte_number"]))
        self.saved.append(fields)

    def fail_belgo_stage(self, **fields):
        self.failures.append(fields)

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

    def update_levolog_results(self, card_id, **fields):
        self.events.append(("platform-update", card_id))
        self.results.append((card_id, fields))

    def update_levolog_cte_number(self, card_id, cte_number):
        self.numbers.append((card_id, cte_number))


class FakeKMM:
    def __init__(self, events):
        self.events = events
        self.emission_kwargs = None
        self.profile_kwargs = None

    def __enter__(self):
        self.events.append(("kmm-enter",))
        return self

    def __exit__(self, *args):
        self.events.append(("kmm-exit",))

    def login(self, *, params, management):
        self.events.append(("login", management, params.username))

    def arcelor_load_user_profile(self, **kwargs):
        self.profile_kwargs = kwargs
        self.events.append(("profile", kwargs["management"], kwargs["center"]))

    def emitting_cte(self, **kwargs):
        self.emission_kwargs = kwargs
        self.events.append(("emit", kwargs["management"]))
        return CTeEmissionResult(number="88888", net_value=98.0)


def build_task(monkeypatch):
    for name, value in {
        "KMM_URL": "http://kmm",
        "KMM_BELGO_USERNAME": "robot",
        "KMM_BELGO_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    events = []
    db = FakeDB(events)
    sql = BelgoLevologSQLConnector(db=db)
    platform = FakePlatformState(events)
    kmm = FakeKMM(events)
    worker = TaskBelgoLevologComplement.__new__(TaskBelgoLevologComplement)
    worker.sql_connector = sql
    worker.platform_state_service = platform
    worker.kmm_factory = lambda **kwargs: kmm
    return worker, sql, platform, kmm, events


def test_sql_connector_fetches_levolog_rows():
    events = []
    connector = BelgoLevologSQLConnector(db=FakeDB(events))

    transactions = connector.fetch_transactions(6)

    assert events == [("sql-fetch", 6)]
    assert transactions[0].id == "42"
    assert transactions[0].payload["CTE_LEVOLOG"] == "57732"


def test_sql_claim_filters_levolog_without_incrementing_retry():
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = []
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    db = object.__new__(DB)
    db.engine = engine

    assert db.claim_belgo_levolog_cases(10) == []

    statement = str(connection.execute.call_args.args[0])
    assert "CRIADO_EM >= :dt_min" in statement
    assert "RETENTATIVA < 5" in statement
    assert "STATUS_ <> 'OK'" in statement
    assert "CTE_LEVOLOG IS NOT NULL" in statement
    assert "CTE_LEVOLOG <> ''" in statement
    assert "CTE_LEVOLOG_COMPLEMENTAR IS NULL" in statement
    assert "CTE_LEVOLOG_COMPLEMENTAR = ''" in statement
    assert "RETENTATIVA = RETENTATIVA + 1" not in statement
    assert "CTE_FRETOLOG_COMPLEMENTAR" not in statement


def test_sql_adapter_maps_levolog_columns():
    item = LevologComplementInput.from_sql_payload(sql_payload())

    assert item.row_id == 42
    assert item.levo_lot == "FILIAL MG"
    assert item.levo_cte == "57732"
    assert item.cte_value == 100.0


def test_routes_emits_saves_sql_then_updates_platform(monkeypatch):
    worker, sql, platform, kmm, events = build_task(monkeypatch)

    result = worker.process_transaction(
        Transaction(id="42", payload=sql_payload())
    )

    assert result.cte_number == "88888"
    assert events[:2] == [
        ("find-card", "163697"),
        ("route", "card-1", LEVOLOG_COMPLEMENT_PHASE_ID),
    ]
    assert events.index(("sql-save", "88888")) < events.index(
        ("platform-update", "card-1")
    )
    assert kmm.profile_kwargs == {
        "user": "robot",
        "management": "levo",
        "center": "FILIAL MG",
    }
    assert kmm.emission_kwargs["cte"] == "57732"
    assert kmm.emission_kwargs["management"] == "levo"
    assert kmm.emission_kwargs["markup"] == 0.98
    assert kmm.emission_kwargs["belgo"] is True
    assert kmm.emission_kwargs["return_details"] is True
    assert sql.db.saved == [{"row_id": 42, "cte_number": "88888"}]
    assert platform.results == [(
        "card-1",
        {"cte_number": "88888", "net_value": 98.0},
    )]


def test_existing_sql_cte_reconciles_platform_without_kmm(monkeypatch):
    worker, _sql, platform, _kmm, _events = build_task(monkeypatch)
    worker.kmm_factory = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("KMM não deveria ser aberto")
    )

    result = worker.process_transaction(
        Transaction(
            id="42",
            payload=sql_payload(CTE_LEVOLOG_COMPLEMENTAR="77777"),
        )
    )

    assert result.resumed_from_sql is True
    assert platform.numbers == [("card-1", "77777")]


def test_failure_increments_retry_and_updates_status(monkeypatch):
    worker, sql, _platform, _kmm, _events = build_task(monkeypatch)
    transaction = Transaction(id="42", payload=sql_payload())

    worker.handle_process_exception(transaction, RuntimeError("falha"))

    assert sql.db.failures == [{
        "row_id": 42,
        "message": "Falha no KMM. RuntimeError",
    }]


def test_emitting_cte_returns_levolog_value_after_markup(monkeypatch):
    driver = MagicMock()
    driver.safe_get_attribute.return_value = "98.00"
    driver.wait_alert.return_value = SimpleNamespace(
        text="CT-e emitido",
        accept=lambda: None,
    )
    driver.switch_to_window.return_value = True
    driver.safe_get_text.return_value = "88888"
    actions = KMMActions(service="test", driver=driver)
    monkeypatch.setattr(actions, "quick_access", lambda *_args: None)
    monkeypatch.setattr(actions, "_status_cte", lambda *_args: True)
    monkeypatch.setattr(actions, "_click_on_negotiation_menu", lambda: None)
    monkeypatch.setattr(
        "src.kmm.services.kmm_actions.time.sleep",
        lambda *_args: None,
    )

    result = actions.emitting_cte(
        cte="57732",
        serie="1",
        cte_value=100.0,
        management="levo",
        markup=0.98,
        return_details=True,
    )

    assert result == CTeEmissionResult(number="88888", net_value=98.0)
