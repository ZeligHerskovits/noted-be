from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, Any

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    mobile: Optional[str] = None
    company_name: str
    industry: str
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
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
    id: int
    email: EmailStr
    full_name: str
    role_id: int
    company_name: Optional[str] = None
    role_name: Optional[str] = None
    is_email_verified: bool
    is_active: bool
    mobile_phone: Optional[str] = None
    company: Optional[Any] = None
    class Config:
        orm_mode = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_phone: Optional[str] = None
    # Add more fields as needed

class CompanyCreate(BaseModel):
    name: str
    industry: str | None = None
    address: str | None = None

class CompanyResponse(BaseModel):
    id: int
    name: str
    industry: str | None = None
    company_address: str | None = None
    company_phone: str | None = None
    created_at: Optional[datetime] = None
    class Config:
        orm_mode = True
        from_attributes = True

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    industry: Optional[str] = None
    # Add more fields as needed

class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: str
    address: str

class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    user_id: Optional[int] = None

class PatientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    class Config:
        orm_mode = True

class EmailVerificationRequest(BaseModel):
    token: str 