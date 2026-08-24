from fastapi import FastAPI

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