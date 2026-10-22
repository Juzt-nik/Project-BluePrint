from fastapi import FastAPI

from app.core.config import settings
from app.api.routes import health, institutions, deposits

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Prototype API for SIH26265. Not an official AICTE system. "
        "Authentication and initial role checks are enabled; further security review is required before public deployment."
    ),
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(institutions.router, prefix="/api/v1")
app.include_router(deposits.router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "status": "development",
        "notice": "Prototype only; no live AICTE or bank integration."
    }
