"""Health check router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {"status": "ok"}


@router.get("/api/health/ready")
async def readiness_check():
    try:
        from src.api.dependencies import get_settings
        get_settings()
        return {"status": "ready"}
    except Exception as exc:
        return {"status": "not_ready", "error": str(exc)}
