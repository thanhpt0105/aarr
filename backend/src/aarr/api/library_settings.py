import os
import shutil
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aarr.api.deps import SessionDep
from aarr.models import QualityProfile, RootFolder
from aarr.models.library import RESOLUTIONS
from aarr.security import require_api_key

profiles_router = APIRouter(
    prefix="/api/v1/quality-profiles",
    tags=["quality-profiles"],
    dependencies=[Depends(require_api_key)],
)
folders_router = APIRouter(
    prefix="/api/v1/root-folders", tags=["root-folders"], dependencies=[Depends(require_api_key)]
)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    allowed_resolutions: list[int] = Field(min_length=1)
    cutoff_resolution: int | None = None
    upgrades_allowed: bool = True

    @field_validator("allowed_resolutions")
    @classmethod
    def _valid_resolutions(cls, value: list[int]) -> list[int]:
        unknown = set(value) - set(RESOLUTIONS)
        if unknown:
            raise ValueError(f"unsupported resolutions {sorted(unknown)}; use {list(RESOLUTIONS)}")
        return sorted(set(value))

    @model_validator(mode="after")
    def _cutoff_is_allowed(self) -> "ProfileIn":
        if (
            self.cutoff_resolution is not None
            and self.cutoff_resolution not in self.allowed_resolutions
        ):
            raise ValueError("cutoff_resolution must be one of allowed_resolutions")
        return self


class ProfileOut(ProfileIn):
    id: int


class FolderIn(BaseModel):
    path: str = Field(min_length=1)
    media_type: Literal["movie", "tv"]


class FolderOut(BaseModel):
    id: int
    path: str
    media_type: str
    accessible: bool
    free_space_bytes: int | None


def _profile_out(row: QualityProfile) -> ProfileOut:
    return ProfileOut(
        id=row.id,
        name=row.name,
        allowed_resolutions=row.allowed_resolutions,
        cutoff_resolution=row.cutoff_resolution,
        upgrades_allowed=row.upgrades_allowed,
    )


def _folder_out(row: RootFolder) -> FolderOut:
    accessible = os.path.isdir(row.path) and os.access(row.path, os.W_OK)
    free = shutil.disk_usage(row.path).free if accessible else None
    return FolderOut(
        id=row.id,
        path=row.path,
        media_type=row.media_type,
        accessible=accessible,
        free_space_bytes=free,
    )


@profiles_router.get("")
def list_profiles(session: SessionDep) -> list[ProfileOut]:
    return [
        _profile_out(r) for r in session.scalars(select(QualityProfile).order_by(QualityProfile.id))
    ]


@profiles_router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileIn, session: SessionDep) -> ProfileOut:
    row = QualityProfile(**body.model_dump())
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A profile named '{body.name}' exists"
        ) from None
    return _profile_out(row)


@profiles_router.get("/{profile_id}")
def get_profile(profile_id: int, session: SessionDep) -> ProfileOut:
    row = session.get(QualityProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quality profile not found")
    return _profile_out(row)


@profiles_router.put("/{profile_id}")
def update_profile(profile_id: int, body: ProfileIn, session: SessionDep) -> ProfileOut:
    row = session.get(QualityProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quality profile not found")
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A profile named '{body.name}' exists"
        ) from None
    return _profile_out(row)


@profiles_router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, session: SessionDep) -> None:
    row = session.get(QualityProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quality profile not found")
    session.delete(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Profile is in use") from None


@folders_router.get("")
def list_folders(session: SessionDep) -> list[FolderOut]:
    return [_folder_out(r) for r in session.scalars(select(RootFolder).order_by(RootFolder.id))]


@folders_router.post("", status_code=status.HTTP_201_CREATED)
def create_folder(body: FolderIn, session: SessionDep) -> FolderOut:
    if not os.path.isabs(body.path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path must be absolute")
    path = os.path.normpath(body.path)
    if not os.path.isdir(path) or not os.access(path, os.W_OK):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Path must be an existing, writable directory"
        )
    row = RootFolder(path=path, media_type=body.media_type)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Root folder already exists") from None
    return _folder_out(row)


@folders_router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, session: SessionDep) -> None:
    row = session.get(RootFolder, folder_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Root folder not found")
    session.delete(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Root folder is in use") from None
