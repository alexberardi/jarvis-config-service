from app.routes.services import router as services_router
from app.routes.settings_gateway import create_settings_gateway_router
from app.routes.service_registration import create_service_registration_router

__all__ = [
    "services_router",
    "create_settings_gateway_router",
    "create_service_registration_router",
]
