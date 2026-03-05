from fastapi import APIRouter, Depends, File, UploadFile
from fastapi import HTTPException

from modelforge.schemas.evaluation import TrialEvaluationResponse
from modelforge.services.evaluation import trial_evaluate
from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/models", tags=["Evaluation"])


@router.post(
    "/{model_id}/versions/{version_id}/trial-evaluate",
    response_model=TrialEvaluationResponse,
)
async def trial_evaluate_endpoint(
    model_id: str,
    version_id: str,
    file: UploadFile = File(...),
    store: ModelStore = Depends(get_store),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    csv_bytes = await file.read()
    if not csv_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    result = trial_evaluate(store, model_id, version_id, csv_bytes)
    return TrialEvaluationResponse(**result)
