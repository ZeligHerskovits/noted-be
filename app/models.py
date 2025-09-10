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
    session_instructions = Column(Text, nullable=True)
    type_writing = Column(Text, nullable=True)  # Store as PostgreSQL array string
    created_at = Column(DateTime, server_default=func.now())

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
    created_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True, nullable=False)

class Client(Base):
    __tablename__ = "clients"
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
    history = Column(Text, nullable=True) 

class EmrType(Base):
    __tablename__ = "emr_type"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    session_type = Column(String, nullable=True)
    documentation_method_id = Column(UUID(as_uuid=True), ForeignKey("documentation_methods.id"), nullable=True)
    files = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    instructions = Column(String, nullable=True)
    session_instructions = Column(String, nullable=True)
    response = Column(String, nullable=True)
    status = Column(String(100), nullable=True)
    previous_status = Column(String(100), nullable=True)  # Track previous status before processing
    total_chunks = Column(Integer, nullable=True)
    processed_chunks = Column(Integer, nullable=True)
    methods_instructions = Column(Text, nullable=True)
    progress_towards_goal_instructions = Column(Text, nullable=True)
    recommended_changes_instructions = Column(Text, nullable=True)

class EMRTypeField(Base):
    __tablename__ = "emr_type_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False)
    analyzable = Column(Text, nullable=True)
    api_name = Column(Text, nullable=True)
    dropdown_values = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
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

class Session(Base):
    __tablename__ = "sessions"
    
    # Static fields (always the same)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emr_type_id = Column(UUID(as_uuid=True), ForeignKey("emr_type.id", ondelete="CASCADE"), nullable=False)
    emr_name = Column(Text, nullable=True)
    manual_instructions = Column(Text, nullable=True)
    session_response = Column(Text, nullable=True)
    methods_response = Column(Text, nullable=True)
    progress_towards_goal_response = Column(Text, nullable=True)
    recommended_changes_response = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Dynamic fields will be added automatically based on emr_type_fields
    # These are handled by your migration system
    # SQLAlchemy will automatically read all columns from the database 

class ManualField(Base):
    __tablename__ = "manual_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(Text, nullable=False)
    emr_type_id = Column(UUID(as_uuid=True), ForeignKey("emr_type.id", ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=True)
    created = Column(DateTime, server_default=func.now())
    updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

class CopingSkill(Base):
    __tablename__ = "coping_skills"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    short_description = Column(Text, nullable=False)
    long_description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class ClinicalSpecialty(Base):
    __tablename__ = "clinical_specialties"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    short_description = Column(Text, nullable=False)
    long_description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class DocumentationMethod(Base):
    __tablename__ = "documentation_methods"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(Text, nullable=False)
    session_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# Junction Tables for User Relationships
class UserCopingSkill(Base):
    __tablename__ = "user_coping_skills"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    coping_skill_id = Column(UUID(as_uuid=True), ForeignKey("coping_skills.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class UserClinicalSpecialty(Base):
    __tablename__ = "user_clinical_specialties"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    clinical_specialty_id = Column(UUID(as_uuid=True), ForeignKey("clinical_specialties.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

# Old junction tables removed - now using UserEMRDocumentationPair

class UserEMRDocumentationPair(Base):
    __tablename__ = "user_emr_documentation_pairs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emr_type_id = Column(UUID(as_uuid=True), ForeignKey("emr_type.id", ondelete="CASCADE"), nullable=False)
    documentation_method_id = Column(UUID(as_uuid=True), ForeignKey("documentation_methods.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now()) 