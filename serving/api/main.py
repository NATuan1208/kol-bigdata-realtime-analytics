from fastapi import FastAPI, Depends, HTTPException
from .routers import kol, forecast, predict

app = FastAPI(
    title="KOL Platform API",
    version="0.2.0",
    description="KOL Analytics Platform - Trust Score Prediction API"
)

@app.get("/healthz")
def health():
    return {"ok": True, "version": "0.2.0"}

# Include routers
app.include_router(kol.router, prefix="/kol", tags=["kol"])
app.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
app.include_router(predict.router, prefix="/predict", tags=["predict"])
