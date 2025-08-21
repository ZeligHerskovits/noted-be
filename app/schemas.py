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
    session_instructions: Optional[str] = None
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_phone: Optional[str] = None
    user_type: Optional[str] = None
    is_active: Optional[bool] = None
    session_instructions: Optional[str] = None  # FE sends 'session_instructions', we save as 'session_instructions'
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

class ClientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    collateral_first_name: Optional[str] = None
    collateral_last_name: Optional[str] = None
    collateral_email: Optional[EmailStr] = None

class ClientUpdate(BaseModel):
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

class ClientResponse(BaseModel):
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
    response: Optional[str] = None

class EmrTypeResponse(BaseModel):
    id: UUID
    name: str
    session_type: Optional[str] = None
    documentation_methods: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    instructions: Optional[str] = None
    response: Optional[str] = None
    status: Optional[str] = None
    
    class Config:
        from_attributes = True

# EMR Type Fields Schemas
class EMRTypeFieldCreate(BaseModel):
    name: str
    type: str
    analyzable: Optional[str] = None
    api_name: Optional[str] = None

class EMRTypeFieldUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    analyzable: Optional[str] = None
    api_name: Optional[str] = None

class EMRTypeFieldResponse(BaseModel):
    id: UUID
    name: str
    type: str
    analyzable: Optional[str] = None
    api_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class EMRTypeResultCreate(BaseModel):
    emr_type_id: UUID
    key: str
    value: Optional[str] = None
    status: Optional[str] = None
    label: Optional[str] = None

class EMRTypeResultResponse(BaseModel):
    id: UUID
    emr_type_id: UUID
    key: str
    value: Optional[str] = None
    instructions: Optional[str] = None
    status: Optional[str] = None
    label: Optional[str] = None
    
    class Config:
        from_attributes = True

class EmrTypeResponseOnly(BaseModel):
    response: Optional[str] = None

class UpdateResultInstructionsRequest(BaseModel):
    key: str
    value: str
    instructions: str 

class EMRTypeResultInstructionsOnly(BaseModel):
    key: str
    value: str
    instructions: Optional[str] = None

class UpdateResultStatusRequest(BaseModel):
    key: str
    value: str
    status: str

class SelectedChunkData(BaseModel):
    selected_chunk_index: int
    selected_chunk_response: str
    selected_chunk_label: Optional[str] = None

class SaveSelectedChunkRequest(BaseModel):
    emr_type_id: str
    selected_chunks: List[SelectedChunkData]

# Session Schemas
class SessionCreate(BaseModel):
    # Static fields (always required)
    client_id: UUID
    emr_type_id: UUID
    manual_instructions: Optional[str] = None
    
    # Dynamic fields (based on emr_type_fields)
    # These will be handled dynamically based on the EMR type
    # Frontend can send any field names, they'll be stored as dynamic columns
    
    class Config:
        from_attributes = True
        # Allow extra fields for dynamic columns
        extra = "allow"

class SessionUpdate(BaseModel):
    # Static fields (optional for updates)
    client_id: Optional[UUID] = None
    emr_type_id: Optional[UUID] = None
    manual_instructions: Optional[str] = None
    
    # Dynamic fields (based on emr_type_fields)
    # These will be handled dynamically based on the EMR type
    
    class Config:
        from_attributes = True
        # Allow extra fields for dynamic columns
        extra = "allow"



class SessionResponse(BaseModel):
    # Static fields (always present)
    id: UUID
    client_id: UUID
    user_id: UUID
    emr_type_id: UUID
    emr_name: Optional[str] = None
    client_id_name: Optional[str] = None  # Virtual field for frontend - not in DB
    created_at: datetime
    updated_at: datetime
    manual_instructions: Optional[str] = None
    session_response: Optional[str] = None
    
    # Dynamic fields will be added automatically based on emr_type_fields
    
    class Config:
        from_attributes = True
        # Allow extra fields for dynamic columns
        extra = "allow"

# Manual Field Schemas
class ManualFieldCreate(BaseModel):
    name: str
    emr_type_id: UUID

class ManualFieldUpdate(BaseModel):
    name: Optional[str] = None

class ManualFieldResponse(BaseModel):
    id: UUID
    name: str
    emr_type_id: UUID
    created: datetime
    updated: datetime
    
    class Config:
        from_attributes = True 