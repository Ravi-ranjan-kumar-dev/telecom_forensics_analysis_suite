"""Validated API request and response models."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .models import UserRole
from .security import validate_password

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 72
PasswordValue = Annotated[
    str,
    Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    ),
    AfterValidator(validate_password),
]


class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
    )
    password: PasswordValue
    role: UserRole = UserRole.viewer


class FirstAdminCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
    )
    password: PasswordValue


class UserLogin(BaseModel):
    username: str
    password: str


class SetupStatus(BaseModel):
    setup_required: bool


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class UserRoleUpdate(BaseModel):
    username: str
    role: UserRole


# ----------------------------- SDR Schemas -----------------------------


class SDRProfileOut(BaseModel):
    mobile_number: str
    subscriber_name: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    operator: Optional[str] = None
    circle: Optional[str] = None
    activation_date: Optional[str] = None
    caf_number: Optional[str] = None
    source_file: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------- CGI Schemas -----------------------------


class CGIProfileOut(BaseModel):
    cgi: str
    operator: Optional[str] = None
    circle: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    police_station: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    site_name: Optional[str] = None
    town: Optional[str] = None
    landmark: Optional[str] = None
    azimuth: Optional[str] = None
    technology: Optional[str] = None
    status: Optional[str] = None
    status_change_date: Optional[str] = None
    mcc_mnc: Optional[str] = None
    lac: Optional[str] = None
    cid: Optional[str] = None
    tac_id: Optional[str] = None
    site_id: Optional[str] = None
    gnb_id: Optional[str] = None
    cell_id: Optional[str] = None
    source_file: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PasswordResetRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
    )


class PasswordResetConfirm(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
    )
    token: str = Field(min_length=20)
    new_password: PasswordValue
