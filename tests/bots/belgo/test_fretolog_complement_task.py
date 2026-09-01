from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ergon.connector import Transaction

from src.bots.belgo.tasks.worker.complementar_fretolog.schemas import (
    FretologComplementInput,
)
from src.bots.belgo.tasks.worker.complementar_fretolog.task import (
    FRETOLOG_COMPLEMENT_PHASE_ID,
    TaskBelgoFretologComplement,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions


def card_payload(**changes):
    fields = {
        "ID": "163697",
        "Filial": "FRETO LOG - MATRIZ",
        "Lotação Fretolog": "MATRIZ",
        "N CT-e Fretolog": "12345",
        "Série CT-e Fretolog": "1",
        "Valor CT-e": 100.0,
        "N Incidentes": 1,
    }
    fields.update(changes)
    return {"field_values": fields}


class FakeItems:
    def __init__(self, events):
        self.events = events
        self.updates = []

    def route(self, card_id, *, to_phase_id):
        self.events.append(("route", card_id, to_phase_id))

    def update(self, card_id, **fields):
        self.events.append(("platform-update", card_id))
        self.updates.append((card_id, fields))


class FakeConnector:
    def __init__(self, events):
        self.events = events
        self.items = FakeItems(events)
        self.client = SimpleNamespace(
            workflows=SimpleNamespace(items=self.items)
        )
        self.released = []

    def release_item(self, card_id):
        self.released.append(card_id)


class FakeDB:
    def __init__(self, events, existing_cte=None):
        self.events = events
        self.existing_cte = existing_cte
        self.saved = []

    def get_belgo_incident(self, incident_id):
        self.events.append(("sql-read", incident_id))
        return {
            "ID": 42,
            "ID_INCIDENTE": incident_id,
            "CTE_FRETOLOG_COMPLEMENTAR": self.existing_cte,
        }

    def save_belgo_fretolog_complement(self, **fields):
        self.events.append(("sql-save", fields["cte_number"]))
        self.saved.append(fields)


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


def build_task(monkeypatch, *, existing_cte=None):
    for name, value in {
        "KMM_URL": "http://kmm",
        "KMM_BELGO_USERNAME": "robot",
        "KMM_BELGO_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    events = []
    connector = FakeConnector(events)
    db = FakeDB(events, existing_cte=existing_cte)
    kmm = FakeKMM(events)
    worker = TaskBelgoFretologComplement.__new__(TaskBelgoFretologComplement)
    worker.platform_connector = connector
    worker.db_service = db
    worker.kmm_factory = lambda **kwargs: kmm
    return worker, connector, db, kmm, events


def test_card_adapter_accepts_platform_field_list():
    payload = {
        "field_values": [
            {"field": {"name": name}, "value": value}
            for name, value in card_payload()["field_values"].items()
        ]
    }

    item = FretologComplementInput.from_platform_payload(payload)

    assert item.incident_id == "163697"
    assert item.freto_cte == "12345"
    assert item.cte_value == 100.0


def test_routes_emits_persists_sql_then_updates_card(monkeypatch):
    worker, connector, db, kmm, events = build_task(monkeypatch)
    transaction = Transaction(id="card-1", payload=card_payload())

    result = worker.process_transaction(transaction)

    assert result.cte_number == "98765"
    assert result.net_value == 88.75
    assert events[0] == ("route", "card-1", FRETOLOG_COMPLEMENT_PHASE_ID)
    assert events.index(("sql-save", "98765")) < events.index(
        ("platform-update", "card-1")
    )
    assert kmm.emission_kwargs == {
        "cte": "12345",
        "serie": "1",
        "cte_value": 100.0,
        "management": "freto",
        "incident_number": 1,
        "taxes": True,
        "belgo": True,
        "return_details": True,
    }
    assert db.saved[0]["row_id"] == 42
    assert connector.items.updates[0][1]["field_values"] == {
        "Valor Complementar Fretolog": 88.75,
        "N CT-e Complementar Fretolog": "98765",
    }


def test_existing_sql_cte_reconciles_card_without_kmm(monkeypatch):
    worker, connector, db, _kmm, events = build_task(
        monkeypatch,
        existing_cte="77777",
    )
    worker.kmm_factory = lambda **kwargs: pytest.fail("KMM não deveria ser aberto")
    transaction = Transaction(
        id="card-2",
        payload=card_payload(**{"Valor Complementar Fretolog": 75.5}),
    )

    result = worker.process_transaction(transaction)

    assert result.resumed_from_sql is True
    assert result.cte_number == "77777"
    assert not db.saved
    assert ("emit", "freto") not in events
    assert connector.items.updates[0][1]["field_values"] == {
        "Valor Complementar Fretolog": 75.5,
        "N CT-e Complementar Fretolog": "77777",
    }


def test_existing_sql_cte_without_net_value_requires_reconciliation(monkeypatch):
    worker, _connector, db, _kmm, _events = build_task(
        monkeypatch,
        existing_cte="77777",
    )
    worker.kmm_factory = lambda **kwargs: pytest.fail("KMM não deveria ser aberto")

    with pytest.raises(RuntimeError, match="reconciliação manual"):
        worker.process_transaction(
            Transaction(id="card-3", payload=card_payload())
        )

    assert not db.saved


def test_failure_keeps_stage_and_releases_card(monkeypatch):
    worker, connector, db, _kmm, events = build_task(monkeypatch)
    db.get_belgo_incident = lambda _incident_id: None
    transaction = Transaction(id="card-4", payload=card_payload())

    with pytest.raises(RuntimeError) as raised:
        worker.process_transaction(transaction)
    worker.handle_process_exception(transaction, raised.value)

    assert events[0] == ("route", "card-4", FRETOLOG_COMPLEMENT_PHASE_ID)
    assert connector.released == ["card-4"]
    assert not db.saved


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
