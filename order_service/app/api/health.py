from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.broker import broker

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str | dict[str, str]]:
    health = {"status": "healthy", "checks": {}}

    try:
        await db.execute(text("SELECT 1"))
        health["checks"]["database"] = "healthy"
    except Exception as e:
        health["checks"]["database"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"

    try:
        if broker.connection and not broker.connection.is_closed:
            health["checks"]["rabbitmq"] = "healthy"
        else:
            health["checks"]["rabbitmq"] = "unhealthy: not connected"
            health["status"] = "unhealthy"
    except Exception as e:
        health["checks"]["rabbitmq"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"

    return health
