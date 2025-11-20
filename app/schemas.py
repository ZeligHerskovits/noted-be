from pydantic import BaseModel, EmailStr
from datetime import datetime, date, timezone
from typing import Optional, Any, List, Dict
from uuid import UUID

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    mobile: Optional[str] = None
    company_name: str
    industry: str
    emr: Optional[List[str]] = None  # List of EMR names
    class Config:
        from_attributes = True

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

class EMRDocumentationPairResponse(BaseModel):
    id: UUID
    emr_type_id: UUID
    emr_type_name: str
    documentation_method_id: UUID
    documentation_method_name: str
    created_at: datetime
    
    class Config:
        from_attributes = True

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
    # New fields
    emr_type_documentation_pairs: Optional[List[EMRDocumentationPairResponse]] = None
    # Keep old fields for backward compatibility during transition (return empty arrays)
    emr_types: Optional[List[UUID]] = []
    documentation_methods: Optional[List[UUID]] = []
    coping_skills: Optional[List[UUID]] = None
    clinical_specialties: Optional[List[UUID]] = None
    type_writing: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class EMRDocumentationPairUpdate(BaseModel):
    emr_type_id: UUID
    documentation_method_id: UUID

class UserUpdateResponse(BaseModel):
    user: UserResponse
    company_wide_update: Optional[bool] = False
    users_updated: Optional[int] = None
    message: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_phone: Optional[str] = None
    user_type: Optional[str] = None
    is_active: Optional[bool] = None
    session_instructions: Optional[str] = None  # FE sends 'session_instructions', we save as 'session_instructions'
    # New fields
    emr_type_documentation_pairs: Optional[List[EMRDocumentationPairUpdate]] = None
    # Keep old fields for backward compatibility during transition
    emr_types: Optional[List[UUID]] = None
    documentation_methods: Optional[List[UUID]] = None
    coping_skills: Optional[List[UUID]] = None
    clinical_specialties: Optional[List[UUID]] = None
    type_writing: Optional[List[str]] = None
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
    emr: List[str] | None = None  # List of EMR names
    address: str | None = None
    created_at: Optional[datetime] = None
    is_active: bool
    class Config:
        from_attributes = True

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    emr: Optional[List[str]] = None  # List of EMR names
    industry: Optional[str] = None
    address: Optional[str] = None
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
    history: Optional[str] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }

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
    history: Optional[str] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }

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
    history: Optional[str] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }
        

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
    documentation_method_id: Optional[UUID] = None
    files: Optional[List[EmrTypeFile]] = None
    emr_url: Optional[str] = None
    created_from_chrome: Optional[bool] = False

class EmrTypeUpdate(BaseModel):
    name: Optional[str] = None
    session_type: Optional[str] = None
    documentation_method_id: Optional[UUID] = None
    files: Optional[List[EmrTypeFile]] = None
    json_response: Optional[str] = None
    methods_instructions: Optional[str] = None
    progress_towards_goal_instructions: Optional[str] = None
    recommended_changes_instructions: Optional[str] = None
    emr_url: Optional[str] = None
    xpath_pattern: Optional[Dict[str, str]] = None  # JSON object mapping labels to XPath patterns

class EmrTypeResponse(BaseModel):
    id: UUID
    name: str
    session_type: Optional[str] = None
    documentation_method_id: Optional[UUID] = None
    files: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    json_response: Optional[str] = None
    status: Optional[str] = None
    session_instructions: Optional[str] = None
    methods_instructions: Optional[str] = None
    progress_towards_goal_instructions: Optional[str] = None
    recommended_changes_instructions: Optional[str] = None
    emr_url: Optional[str] = None
    xpath_pattern: Optional[Dict[str, str]] = None  # JSON object mapping labels to XPath patterns
    created_from_chrome: Optional[bool] = False
    user_id: Optional[UUID] = None

    
    class Config:
        from_attributes = True

# EMR Type Fields Schemas
class EMRTypeFieldCreate(BaseModel):
    name: str
    type: str
    analyzable: Optional[str] = None
    api_name: Optional[str] = None
    dropdown_values: Optional[str] = None
    instructions: Optional[str] = None

class EMRTypeFieldUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    analyzable: Optional[str] = None
    api_name: Optional[str] = None
    dropdown_values: Optional[str] = None
    instructions: Optional[str] = None

class EMRTypeFieldResponse(BaseModel):
    id: UUID
    name: str
    type: str
    analyzable: Optional[str] = None
    api_name: Optional[str] = None
    dropdown_values: Optional[str] = None
    instructions: Optional[str] = None
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
    type: Optional[str] = None
    dropdown_values: Optional[str] = None
    
    class Config:
        from_attributes = True

class EmrTypeResponseOnly(BaseModel):
    json_response: Optional[str] = None

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

class SelectedFieldData(BaseModel):
    field_name: str
    field_value: str
    chunk_index: int
    chunk_label: Optional[str] = None

class SaveSelectedChunkRequest(BaseModel):
    emr_type_id: str
    selected_chunks: List[SelectedChunkData] = []
    selected_fields: List[SelectedFieldData] = []

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
    feedback: Optional[str] = None
    
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
    methods_response: Optional[str] = None
    progress_towards_goal_response: Optional[str] = None
    recommended_changes_response: Optional[str] = None
    feedback: Optional[str] = None
    
    # Dynamic fields will be added automatically based on emr_type_fields
    
    class Config:
        from_attributes = True
        # Allow extra fields for dynamic columns
        extra = "allow"
        # Ensure proper JSON serialization for date fields
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }
    


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

# Coping Skills Schemas
class CopingSkillCreate(BaseModel):
    short_description: str
    long_description: Optional[str] = None

class CopingSkillUpdate(BaseModel):
    short_description: Optional[str] = None
    long_description: Optional[str] = None

class CopingSkillResponse(BaseModel):
    id: UUID
    short_description: str
    long_description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Clinical Specialties Schemas
class ClinicalSpecialtyCreate(BaseModel):
    short_description: str
    long_description: Optional[str] = None

class ClinicalSpecialtyUpdate(BaseModel):
    short_description: Optional[str] = None
    long_description: Optional[str] = None

class ClinicalSpecialtyResponse(BaseModel):
    id: UUID
    short_description: str
    long_description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Documentation Methods Schemas
class DocumentationMethodCreate(BaseModel):
    name: str
    session_instructions: Optional[str] = None

class DocumentationMethodUpdate(BaseModel):
    name: Optional[str] = None
    session_instructions: Optional[str] = None

class DocumentationMethodResponse(BaseModel):
    id: UUID
    name: str
    session_instructions: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Modality Schemas
class ModalityCreate(BaseModel):
    name: str
    short_term: Optional[str] = None
    description: Optional[str] = None
    modality_setting: Optional[str] = None

class ModalityUpdate(BaseModel):
    name: Optional[str] = None
    short_term: Optional[str] = None
    description: Optional[str] = None
    modality_setting: Optional[str] = None

class ModalityResponse(BaseModel):
    id: UUID
    name: str
    short_term: Optional[str] = None
    description: Optional[str] = None
    modality_setting: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Modality Step Schemas
class ModalityStepCreate(BaseModel):
    modality_id: UUID
    name: str

class ModalityStepUpdate(BaseModel):
    modality_id: Optional[UUID] = None
    name: Optional[str] = None

class ModalityStepResponse(BaseModel):
    id: UUID
    modality_id: UUID
    modality_name: Optional[str] = None  # Virtual field for frontend
    name: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Activity Schemas
class ActivityCreate(BaseModel):
    name: str
    short_term: Optional[str] = None
    description: Optional[str] = None
    activity_setting: Optional[str] = None

class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    short_term: Optional[str] = None
    description: Optional[str] = None
    activity_setting: Optional[str] = None

class ActivityResponse(BaseModel):
    id: UUID
    name: str
    short_term: Optional[str] = None
    description: Optional[str] = None
    activity_setting: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Sub-Activity Schemas
class SubActivityCreate(BaseModel):
    activity_id: UUID
    name: str

class SubActivityUpdate(BaseModel):
    activity_id: Optional[UUID] = None
    name: Optional[str] = None

class SubActivityResponse(BaseModel):
    id: UUID
    activity_id: UUID
    activity_name: Optional[str] = None  # Virtual field for frontend
    name: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
