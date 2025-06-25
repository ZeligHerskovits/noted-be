from pydantic import BaseModel, EmailStr
import datetime

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

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str
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
    created_at: datetime.datetime | None = None
    class Config:
        orm_mode = True 