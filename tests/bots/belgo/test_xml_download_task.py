from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from ergon.connector import Transaction

from src.bots.belgo.tasks.obtencao_xml.connectors import BelgoXMLSQLConnector
from src.bots.belgo.tasks.obtencao_xml.schemas import XMLDownloadInput
from src.bots.belgo.tasks.obtencao_xml.task import (
    XML_PHASE_ID,
    TaskBelgoXMLDownload,
)
from src.bots.belgo.tasks.platform_state import BelgoPlatformStateService
from src.shared.db_handler.db_handler import DB


def sql_payload(**changes):
    payload = {
        "ID": 42,
        "ID_INCIDENTE": "163697",
        "FILIAL": "FRETO LOG - MATRIZ",
        "LOTACAO_FRETOLOG": "MG - Contagem",
        "CTE_FRETOLOG_COMPLEMENTAR": "98765",
        "DATA_EMISSAO_CTE_FRETO": datetime(2026, 9, 2, 10, 30),
    }
    payload.update(changes)
    return payload


class FakeDB:
    def __init__(self, events):
        self.events = events
        self.rows = [sql_payload()]
        self.failures = []

    def claim_belgo_xml_cases(self, limit):
        self.events.append(("sql-fetch", limit))
        return self.rows

    def get_belgo_case_by_row_id(self, row_id):
        return self.rows[0] if row_id == 42 else None

    def fail_belgo_stage(self, **fields):
        self.failures.append(fields)

    def close(self):
        return None


class FakePlatformState:
    def __init__(self, events, *, attached=False):
        self.events = events
        self.attached = attached
        self.uploads = []

    def find_card_id(self, incident_id):
        self.events.append(("find-card", incident_id))
        return "card-1"

    def card_has_attachment(self, card_id, field_name):
        self.events.append(("has-xml", card_id, field_name))
        return self.attached

    def route_to(self, card_id, phase_id):
        self.events.append(("route", card_id, phase_id))

    def upload_attachment(self, card_id, field_name, file_path):
        self.events.append(("upload", card_id, field_name))
        self.uploads.append((card_id, field_name, file_path))


class FakeKMM:
    def __init__(self, events, file_path):
        self.events = events
        self.file_path = file_path
        self.profile_kwargs = None
        self.xml_args = None

    def __enter__(self):
        self.events.append(("kmm-enter",))
        return self

    def __exit__(self, *args):
        self.events.append(("kmm-exit",))

    def login(self, *, params, management):
        self.events.append(("login", management, params.username))

    def belgo_load_user_profile(self, **kwargs):
        self.profile_kwargs = kwargs

    def get_xml(self, complement_cte, emitted_at):
        self.xml_args = (complement_cte, emitted_at)
        self.file_path.write_text("<cte/>", encoding="utf-8")
        self.events.append(("download", complement_cte))
        return self.file_path


def build_task(monkeypatch, tmp_path, *, attached=False):
    for name, value in {
        "KMM_URL": "http://kmm",
        "KMM_BELGO_USERNAME": "robot",
        "KMM_BELGO_PASSWORD": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    events = []
    db = FakeDB(events)
    sql = BelgoXMLSQLConnector(db=db)
    platform = FakePlatformState(events, attached=attached)
    file_path = tmp_path / "CTE 98765.xml"
    kmm = FakeKMM(events, file_path)
    worker = TaskBelgoXMLDownload.__new__(TaskBelgoXMLDownload)
    worker.sql_connector = sql
    worker.platform_state_service = platform
    worker.kmm_factory = lambda **kwargs: kmm
    return worker, sql, platform, kmm, file_path, events


def test_sql_connector_fetches_xml_candidates():
    events = []
    connector = BelgoXMLSQLConnector(db=FakeDB(events))

    transactions = connector.fetch_transactions(4)

    assert events == [("sql-fetch", 4)]
    assert transactions[0].id == "42"
    assert transactions[0].payload["CTE_FRETOLOG_COMPLEMENTAR"] == "98765"


def test_sql_claim_filters_complement_without_incrementing_retry():
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = []
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    db = object.__new__(DB)
    db.engine = engine

    assert db.claim_belgo_xml_cases(10) == []

    statement = str(connection.execute.call_args.args[0])
    assert "CRIADO_EM >= :dt_min" in statement
    assert "RETENTATIVA < 5" in statement
    assert "STATUS_ <> 'OK'" in statement
    assert "CTE_FRETOLOG_COMPLEMENTAR IS NOT NULL" in statement
    assert "CTE_FRETOLOG_COMPLEMENTAR <> ''" in statement
    assert "RETENTATIVA = RETENTATIVA + 1" not in statement


def test_sql_adapter_maps_xml_columns():
    item = XMLDownloadInput.from_sql_payload(sql_payload())

    assert item.row_id == 42
    assert item.complement_cte == "98765"
    assert item.emitted_at == datetime(2026, 9, 2, 10, 30)


def test_downloads_routes_uploads_and_removes_temporary_file(monkeypatch, tmp_path):
    worker, _sql, platform, kmm, file_path, events = build_task(
        monkeypatch,
        tmp_path,
    )

    result = worker.process_transaction(
        Transaction(id="42", payload=sql_payload())
    )

    assert result.uploaded is True
    assert events[:3] == [
        ("find-card", "163697"),
        ("has-xml", "card-1", "XML"),
        ("route", "card-1", XML_PHASE_ID),
    ]
    assert ("download", "98765") in events
    assert ("upload", "card-1", "XML") in events
    assert kmm.profile_kwargs == {
        "user": "robot",
        "management": "freto",
        "lotation": "MG - Contagem",
    }
    assert kmm.xml_args == ("98765", datetime(2026, 9, 2, 10, 30))
    assert platform.uploads[0][2] == file_path
    assert not file_path.exists()


def test_existing_attachment_still_downloads_without_route_or_upload(monkeypatch, tmp_path):
    worker, _sql, platform, _kmm, file_path, events = build_task(
        monkeypatch,
        tmp_path,
        attached=True,
    )

    result = worker.process_transaction(
        Transaction(id="42", payload=sql_payload())
    )

    assert result.uploaded is False
    assert ("download", "98765") in events
    assert not any(event[0] == "route" for event in events)
    assert not platform.uploads
    assert not file_path.exists()


def test_failure_increments_retry_and_updates_status(monkeypatch, tmp_path):
    worker, sql, _platform, _kmm, _file_path, _events = build_task(
        monkeypatch,
        tmp_path,
    )
    transaction = Transaction(id="42", payload=sql_payload())

    worker.handle_process_exception(transaction, RuntimeError("falha"))

    assert sql.db.failures == [{
        "row_id": 42,
        "message": "Falha no KMM. RuntimeError",
    }]


def test_platform_attachment_check_and_upload(monkeypatch, tmp_path):
    workflow = MagicMock()
    workflow.fields.return_value = SimpleNamespace(
        items=[
            {"id": "field-id", "name": "ID"},
            {"id": "field-xml", "name": "XML"},
        ],
        total=2,
    )
    workflow.item_attachment_upload_url.return_value = {
        "upload_url": "https://upload.example/xml",
        "object_key": "object/xml",
    }
    client = MagicMock()
    client.workflows.workflow.return_value = workflow
    client.workflows.items.get.return_value = {
        "id": "card-1",
        "field_values": {
            "field-xml": [{"filename": "existing.xml"}],
        },
    }
    response = MagicMock()
    put = MagicMock(return_value=response)
    monkeypatch.setattr("src.bots.belgo.tasks.platform_state.httpx.put", put)
    service = BelgoPlatformStateService(client=client)

    assert service.card_has_attachment("card-1", "XML") is True

    file_path = tmp_path / "cte.xml"
    file_path.write_text("<cte/>", encoding="utf-8")
    service.upload_attachment("card-1", "XML", file_path)

    put.assert_called_once()
    response.raise_for_status.assert_called_once()
    confirmation = workflow.confirm_item_attachment.call_args.kwargs
    assert confirmation["item_id"] == "card-1"
    assert confirmation["field_id"] == "field-xml"
    assert confirmation["object_key"] == "object/xml"
    assert confirmation["filename"] == "cte.xml"
    assert confirmation["content_type"] in {"application/xml", "text/xml"}
    assert confirmation["size"] == file_path.stat().st_size
