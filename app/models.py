from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, JSON, Date, Text
from sqlalchemy.sql import func
from sqlalchemy.ext.mutable import MutableList
from .db import Base
import uuid
from sqlalchemy.dialects.postgresql import UUID, JSONB

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    trusted_devices = Column(MutableList.as_mutable(JSON), default=list)  # List of trusted device IDs
    is_email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String, nullable=True)
    mobile_phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    user_type = Column(String(100), nullable=True)

class Otp(Base):
    __tablename__ = "otps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

class Company(Base):
    __tablename__ = "companies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    emr = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    collateral_first_name = Column(String(100), nullable=True)
    collateral_last_name = Column(String(100), nullable=True)
    collateral_email = Column(String(255), nullable=True) 

class EmrType(Base):
    __tablename__ = "emr_type"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    session_type = Column(String, nullable=True)
    documentation_methods = Column(String, nullable=True)
    files = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    instructions = Column(String, nullable=True)
    response = Column(String, nullable=True)
    status = Column(String(100), nullable=True)
    total_chunks = Column(Integer, nullable=True)
    processed_chunks = Column(Integer, nullable=True)

class EMRTypeField(Base):
    __tablename__ = "emr_type_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class EMRTypeResult(Base):
    __tablename__ = "emr_type_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    emr_type_id = Column(UUID(as_uuid=True), ForeignKey("emr_type.id"), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    status = Column(String(100), nullable=True)
    label = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now()) 