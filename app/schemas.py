from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    industry: str
    address: str
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
    class Config:
        orm_mode = True

class CompanyCreate(BaseModel):
    name: str
    industry: str | None = None
    address: str | None = None

class CompanyResponse(BaseModel):
    id: int
    name: str
    industry: str | None = None
    address: str | None = None
    created_at: Optional[datetime] = None
    class Config:
        orm_mode = True

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