from fastapi import APIRouter, Depends

from aarr import __version__
from aarr.security import require_api_key

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/status", dependencies=[Depends(require_api_key)])
def system_status() -> dict[str, str]:
    return {"version": __version__}
