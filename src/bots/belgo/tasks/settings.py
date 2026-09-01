from dotenv import load_dotenv
from ergon.service import ServiceConfig

from src.bots.belgo.tasks.publisher.services import BelgoPortalService
from src.shared.db_handler.db_handler import DB

load_dotenv()

BELGO_DB_SERVICE = ServiceConfig(service=DB, kwargs={})
BELGO_PORTAL_SERVICE = ServiceConfig(service=BelgoPortalService, kwargs={})

# O projeto continua usando o logger legado; a task pode receber configuração
# OTEL posteriormente sem alterar seu contrato.
LOGGING = None
TRACING = None
