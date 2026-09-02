from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.sql import func
from .database import Base
from enum import Enum


# ----------------------------- SDR Subscriber Model -----------------------------

class SDRSubscriber(Base):
    __tablename__ = "sdr_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    mobile_number = Column(String, unique=True, index=True, nullable=False)
    subscriber_name = Column(String, nullable=True)
    father_name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    id_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)
    operator = Column(String, nullable=True)
    circle = Column(String, nullable=True)
    activation_date = Column(String, nullable=True)
    caf_number = Column(String, nullable=True)
    source_file = Column(String, nullable=True)


# ----------------------------- CGI Address Model -----------------------------

class CGIAddress(Base):
    __tablename__ = "cgi_addresses"

    id = Column(Integer, primary_key=True, index=True)
    cgi = Column(String, unique=True, index=True, nullable=False)
    operator = Column(String, nullable=True)
    circle = Column(String, nullable=True)
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    police_station = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    site_name = Column(String, nullable=True)
    town = Column(String, nullable=True)
    landmark = Column(String, nullable=True)
    azimuth = Column(String, nullable=True)
    technology = Column(String, nullable=True)
    status = Column(String, nullable=True)
    status_change_date = Column(String, nullable=True)
    mcc_mnc = Column(String, nullable=True)
    lac = Column(String, nullable=True)
    cid = Column(String, nullable=True)
    tac_id = Column(String, nullable=True)
    site_id = Column(String, nullable=True)
    gnb_id = Column(String, nullable=True)
    cell_id = Column(String, nullable=True)
    source_file = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserRole(str, Enum):
    admin = "admin"
    investigator = "investigator"
    viewer = "viewer"
