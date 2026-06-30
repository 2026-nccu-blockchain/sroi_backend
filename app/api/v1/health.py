"""Health-check endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
async def get_health() -> dict[str, str]:
    """Return service health status.

    Returns:
        dict[str, str]: Current service status.
    """

    return {"status": "ok"}
