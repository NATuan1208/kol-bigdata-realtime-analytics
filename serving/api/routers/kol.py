from fastapi import APIRouter
from ..services.model_loader import get_trust_model
from ..services.cassandra_client import read_latest_trust

router = APIRouter()

@router.get("/{kol_id}/trust")
def trust(kol_id: str):
    score = read_latest_trust(kol_id) or 72.5
    return {"kol_id": kol_id, "trust_score": score}
