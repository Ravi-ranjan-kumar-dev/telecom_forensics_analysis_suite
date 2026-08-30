from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=6, max_length=72)

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None

# नया role update schema
class UserRoleUpdate(BaseModel):
    username: str
    role: str  # "admin", "investigator", "viewer"

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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
