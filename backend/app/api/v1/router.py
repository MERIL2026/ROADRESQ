from fastapi import APIRouter

from app.api.v1.admin.bookings import router as admin_bookings_router
from app.api.v1.admin.providers import router as admin_providers_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bookings import router as bookings_router
from app.api.v1.health import router as health_router
from app.api.v1.providers import router as providers_router
from app.api.v1.services import router as services_router
from app.api.v1.vehicles import router as vehicles_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount sub-routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(services_router)
api_v1_router.include_router(vehicles_router)
api_v1_router.include_router(bookings_router)
api_v1_router.include_router(providers_router)
api_v1_router.include_router(admin_providers_router)
api_v1_router.include_router(admin_bookings_router)
