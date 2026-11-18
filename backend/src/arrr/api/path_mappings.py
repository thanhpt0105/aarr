from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from arrr.api.deps import SessionDep
from arrr.models import DownloadClientConfig, RemotePathMapping
from arrr.security import require_api_key


class MappingIn(BaseModel):
    client_id: int
    remote_path: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class MappingOut(MappingIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


router = APIRouter(
    prefix="/api/v1/path-mappings",
    tags=["path-mappings"],
    dependencies=[Depends(require_api_key)],
)


@router.get("")
def list_mappings(session: SessionDep, client_id: int | None = None) -> list[MappingOut]:
    query = select(RemotePathMapping).order_by(RemotePathMapping.id)
    if client_id is not None:
        query = query.where(RemotePathMapping.client_id == client_id)
    return [MappingOut.model_validate(r) for r in session.scalars(query)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_mapping(body: MappingIn, session: SessionDep) -> MappingOut:
    if session.get(DownloadClientConfig, body.client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Download client not found")
    row = RemotePathMapping(**body.model_dump())
    session.add(row)
    session.commit()
    return MappingOut.model_validate(row)


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: int, session: SessionDep) -> None:
    row = session.get(RemotePathMapping, mapping_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Path mapping not found")
    session.delete(row)
    session.commit()
