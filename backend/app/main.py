import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import get_current_user
from app.auth.router import router as auth_router
from app.datasources.router import router as datasources_router
from app.db.database import check_database_connection
from app.exceptions.router import router as exceptions_router
from app.investigation.router import router as investigations_router
from app.reconciliation.engine import reconcile_payments


app = FastAPI(
    title="LedgerLens API",
    version="0.1.0",
    description="Financial reconciliation and investigation API",
)

DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(investigations_router)
app.include_router(exceptions_router)
app.include_router(datasources_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ledgerlens-api",
        "version": "0.1.0",
    }


@app.get("/health/database")
def database_health_check():
    check_database_connection()

    return {
        "status": "ok",
        "database": "connected",
    }
@app.post("/reconciliation/run")
def run_reconciliation(_user: dict = Depends(get_current_user)):
    results = reconcile_payments()

    return {
        "status": "ok",
        "results": results,
    }