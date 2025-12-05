from fastapi import FastAPI, Depends, HTTPException
from .routers import kol, forecast

app = FastAPI(title="KOL Platform API", version="0.1.0")

@app.get("/healthz")
def health():
    return {"ok": True}

app.include_router(kol.router, prefix="/kol", tags=["kol"])
app.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
