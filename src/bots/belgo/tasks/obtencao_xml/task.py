from __future__ import annotations

import logging
import os
from pathlib import Path

from ergon.connector import Transaction
from ergon.task.mixins.consumer import ConsumerTask

from src.bots.belgo.tasks.obtencao_xml.schemas import (
    REQUIRED_PLATFORM_FIELDS,
    XMLDownloadInput,
    XMLDownloadResult,
)
from src.kmm.services.kmm_actions import KMMActions, LoginParams

logger = logging.getLogger(__name__)

XML_PHASE_ID = "813464dd-b550-4e88-b620-856c48b27a66"
BASE_DIR = Path(__file__).resolve().parents[5]


class TaskBelgoXMLDownload(ConsumerTask):
    kmm_factory = KMMActions

    def _validate_platform_fields(self) -> None:
        if os.getenv("BELGO_VALIDATE_PLATFORM_FIELDS", "true").lower() != "true":
            return
        self.platform_state_service.validate_phase_fields(
            XML_PHASE_ID,
            REQUIRED_PLATFORM_FIELDS,
        )

    def _download(self, item: XMLDownloadInput) -> Path:
        username = os.environ["KMM_BELGO_USERNAME"]
        with self.kmm_factory(
            service="Belgo Freto",
            evidence_dir=BASE_DIR / "output" / "evidence",
        ) as freto_kmm:
            logger.info(
                "Obtendo XML do incidente %s pela filial Fretolog (%s)",
                item.incident_id,
                item.center,
            )
            freto_kmm.login(
                params=LoginParams(
                    url=os.environ["KMM_URL"],
                    username=username,
                    password=os.environ["KMM_BELGO_PASSWORD"],
                ),
                management="freto",
            )
            freto_kmm.belgo_load_user_profile(
                user=username,
                management="freto",
                lotation=item.freto_lot,
            )
            downloaded = freto_kmm.get_xml(
                item.complement_cte,
                item.emitted_at,
            )

        if not downloaded:
            raise RuntimeError(
                f"KMM não retornou XML para o incidente {item.incident_id}"
            )
        file_path = Path(downloaded)
        if not file_path.is_file() or file_path.stat().st_size == 0:
            if file_path.is_file():
                file_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Arquivo XML inválido para o incidente {item.incident_id}: {file_path}"
            )
        return file_path

    def process_transaction(self, transaction: Transaction) -> XMLDownloadResult:
        item = XMLDownloadInput.from_sql_payload(transaction.payload)
        card_id = self.platform_state_service.find_card_id(item.incident_id)
        already_attached = self.platform_state_service.card_has_attachment(
            card_id,
            "XML",
        )
        if not already_attached:
            self.platform_state_service.route_to(card_id, XML_PHASE_ID)

        file_path = self._download(item)
        try:
            if not already_attached:
                self.platform_state_service.upload_attachment(
                    card_id,
                    "XML",
                    file_path,
                )
            return XMLDownloadResult(
                filename=file_path.name,
                uploaded=not already_attached,
            )
        finally:
            file_path.unlink(missing_ok=True)

    def handle_process_success(
        self,
        transaction: Transaction,
        result: XMLDownloadResult,
    ) -> None:
        logger.info(
            "XML obtido para linha SQL %s (%s): %s",
            transaction.id,
            "anexado" if result.uploaded else "já existente no card",
            result.filename,
        )

    def handle_process_exception(self, transaction: Transaction, exc: Exception) -> None:
        logger.error(
            "Falha na obtenção do XML da linha SQL %s: %s",
            transaction.id,
            exc,
        )
        self.sql_connector.mark_failed(
            transaction,
            f"Falha no KMM. {type(exc).__name__}",
        )

    def execute(self) -> int:
        self._validate_platform_fields()
        return self.consume_transactions(self.worker_policy)
