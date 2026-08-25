from fastapi import FastAPI

from app.db.database import check_database_connection
from app.reconciliation.engine import reconcile_payments


app = FastAPI(
    title="LedgerLens API",
    version="0.1.0",
    description="Financial reconciliation and investigation API",
)


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
def run_reconciliation():
    results = reconcile_payments()

    return {
        "status": "ok",
        "results": results,
    }