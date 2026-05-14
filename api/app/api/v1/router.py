from fastapi import APIRouter

from app.api.v1.admin.controller import router as admin_router
from app.api.v1.chat.controller import router as chat_router
from app.api.v1.manager.controller import router as manager_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(chat_router)
v1_router.include_router(admin_router)
v1_router.include_router(manager_router)
