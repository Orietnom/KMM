from __future__ import annotations

from collections.abc import Collection

from src.bots.belgo.bba_portal import BelgoPortal
from src.bots.belgo.tasks.publisher.schemas import BelgoPortalResult


class BelgoPortalService:
    """Cria uma sessão de portal somente durante a execução da captura."""

    def capture(self, skip_incident_ids: Collection[str] = ()) -> BelgoPortalResult:
        portal = BelgoPortal(itens_in_bd={str(item).strip() for item in skip_incident_ids})
        return portal.get_capture_result()
