from __future__ import annotations

import os
from typing import Any

from ergon_platform import ErgonClient

from src.bots.belgo.tasks.publisher.connectors import WORKFLOW_ID


class BelgoPlatformStateService:
    def __init__(self, client: ErgonClient | None = None) -> None:
        self.client = client or ErgonClient(
            client_id=os.environ["ERGON_CLIENT_ID"],
            client_secret=os.environ["ERGON_CLIENT_SECRET"],
            base_url=os.getenv("ERGON_BASE_URL", "https://platform.ergondata.ai"),
            company_id=os.getenv("ERGON_COMPANY_ID") or None,
            timeout=float(os.getenv("ERGON_PLATFORM_TIMEOUT", "30")),
            max_retries=int(os.getenv("ERGON_PLATFORM_MAX_RETRIES", "2")),
        )
        self._field_names: dict[str, str] | None = None

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            payload = dump(mode="json")
            return payload if isinstance(payload, dict) else {}
        return {}

    @classmethod
    def _page_items(cls, page: Any) -> tuple[list[Any], int]:
        if isinstance(page, list):
            return page, len(page)
        items = getattr(page, "items", None)
        total = getattr(page, "total", None)
        if isinstance(items, list):
            return items, int(total if total is not None else len(items))
        payload = cls._as_dict(page)
        raw_items = payload.get("items")
        raw_items = raw_items if isinstance(raw_items, list) else []
        return raw_items, int(payload.get("total", len(raw_items)))

    def _workflow_field_names(self) -> dict[str, str]:
        if self._field_names is not None:
            return self._field_names
        fields = self.client.workflows.workflow(WORKFLOW_ID).fields()
        items, _ = self._page_items(fields)
        self._field_names = {
            str(payload["id"]): str(payload["name"])
            for field in items
            if (payload := self._as_dict(field)).get("id") and payload.get("name")
        }
        return self._field_names

    def _item_field_values(self, item: Any) -> dict[str, Any]:
        payload = self._as_dict(item)
        raw_values = payload.get("field_values") or {}
        names_by_id = self._workflow_field_names()
        if isinstance(raw_values, dict):
            return {
                names_by_id.get(str(identifier), str(identifier)): (
                    value.get("value")
                    if isinstance(value, dict) and "value" in value
                    else value
                )
                for identifier, value in raw_values.items()
            }

        values: dict[str, Any] = {}
        for entry in raw_values if isinstance(raw_values, list) else []:
            entry_payload = self._as_dict(entry)
            field = self._as_dict(entry_payload.get("field"))
            identifier = entry_payload.get("field_id") or field.get("id")
            name = (
                entry_payload.get("field_name")
                or entry_payload.get("name")
                or field.get("name")
                or names_by_id.get(str(identifier))
            )
            if name:
                values[str(name)] = entry_payload.get("value")
        return values

    def find_card_id(self, incident_id: str) -> str:
        workflow = self.client.workflows.workflow(WORKFLOW_ID)
        matches: list[str] = []
        offset = 0
        limit = 100
        while True:
            page = workflow.items(limit=limit, offset=offset)
            items, total = self._page_items(page)
            for item in items:
                payload = self._as_dict(item)
                if str(self._item_field_values(item).get("ID", "")).strip() == incident_id:
                    matches.append(str(payload["id"]))
            offset += len(items)
            if not items or offset >= total:
                break

        if len(matches) != 1:
            raise RuntimeError(
                f"Esperado 1 card BELGO para o incidente {incident_id}, encontrados {len(matches)}"
            )
        return matches[0]

    def route_to(self, card_id: str, phase_id: str) -> None:
        self.client.workflows.items.route(card_id, to_phase_id=phase_id)

    def validate_phase_fields(self, phase_id: str, expected: set[str] | frozenset[str]) -> None:
        workflow_fields, _ = self._page_items(
            self.client.workflows.workflow(WORKFLOW_ID).fields()
        )
        phase_fields, _ = self._page_items(
            self.client.workflows.phases.list_fields(phase_id)
        )
        available = {
            str(payload["name"])
            for field in [*workflow_fields, *phase_fields]
            if (payload := self._as_dict(field)).get("name")
        }
        missing = set(expected) - available
        if missing:
            raise RuntimeError(
                f"Campos BELGO ausentes na fase {phase_id}: {', '.join(sorted(missing))}"
            )

    def update_results(self, card_id: str, *, cte_number: str, net_value: float) -> None:
        self.client.workflows.items.update(
            card_id,
            field_values={
                "Valor Complementar Fretolog": net_value,
                "N CT-e Complementar Fretolog": cte_number,
            },
        )

    def update_cte_number(self, card_id: str, cte_number: str) -> None:
        self.client.workflows.items.update(
            card_id,
            field_values={"N CT-e Complementar Fretolog": cte_number},
        )

    def close(self) -> None:
        self.client.close()
