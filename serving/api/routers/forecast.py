from fastapi import APIRouter
from ..services.model_loader import get_success_model

router = APIRouter()

@router.get("/{kol_id}")
def forecast(kol_id: str):
    # dummy values
    yhat_next_1h = 123.4
    ci = [100.0, 150.0]
    return {"kol_id": kol_id, "yhat_next_1h": yhat_next_1h, "ci": ci}
