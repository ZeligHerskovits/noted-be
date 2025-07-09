from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, Any, List, Dict
from uuid import UUID

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    mobile: Optional[str] = None
    company_name: str
    industry: str
    emr: Optional[str] = None
    class Config:
        orm_mode = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    deviceId: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str
    deviceId: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role_id: int
    company_name: Optional[str] = None
    role_name: Optional[str] = None
    is_email_verified: bool
    is_active: bool
    mobile_phone: Optional[str] = None
    company: Optional[Any] = None
    user_type: Optional[str] = None
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_phone: Optional[str] = None
    user_type: Optional[str] = None
    is_active: Optional[bool] = None
    # Add more fields as needed

class CompanyCreate(BaseModel):
    name: str
    industry: str | None = None
    address: str | None = None
    is_active: bool = True

class CompanyResponse(BaseModel):
    id: UUID
    name: str
    industry: str | None = None
    emr: str | None = None
    created_at: Optional[datetime] = None
    is_active: bool
    class Config:
        orm_mode = True
        from_attributes = True

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    emr: Optional[str] = None
    industry: Optional[str] = None
    is_active: Optional[bool] = None
    # Add more fields as needed

class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    collateral_first_name: Optional[str] = None
    collateral_last_name: Optional[str] = None
    collateral_email: Optional[EmailStr] = None

class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    user_id: Optional[UUID] = None
    collateral_first_name: Optional[str] = None
    collateral_last_name: Optional[str] = None
    collateral_email: Optional[str] = None

class PatientResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    collateral_first_name: Optional[str] = None
    collateral_last_name: Optional[str] = None
    collateral_email: Optional[str] = None
    class Config:
        orm_mode = True

class EmailVerificationRequest(BaseModel):
    token: str 

class EmrTypeFile(BaseModel):
    name: str
    content: str  # base64 encoded content
    type: str
    size: int
    client_name: Optional[str] = None
    date: Optional[str] = None
    version: Optional[str] = None

class EmrTypeCreate(BaseModel):
    name: str
    session_type: Optional[str] = None
    documentation_methods: Optional[str] = None
    files: Optional[List[EmrTypeFile]] = None

class EmrTypeUpdate(BaseModel):
    name: Optional[str] = None
    session_type: Optional[str] = None
    documentation_methods: Optional[str] = None
    files: Optional[List[EmrTypeFile]] = None
    instructions: Optional[str] = None

class EmrTypeResponse(BaseModel):
    id: UUID
    name: str
    session_type: Optional[str] = None
    documentation_methods: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    instructions: Optional[str] = None
    
    class Config:
        from_attributes = True 