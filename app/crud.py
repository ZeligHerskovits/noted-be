from sqlalchemy.orm import Session
from .models import User, Otp, Role, Company, EmrType, EMRTypeField, EMRTypeResult, Client, Session as SessionModel
from passlib.context import CryptContext
import jwt
import datetime
from sqlalchemy import and_
import random
import secrets
import os
from uuid import UUID
from typing import List, Optional

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password: str, full_name: str, company_id: UUID, mobile_phone: str = None, user_type: str = None):
    hashed_password = get_password_hash(password)
    user = User(email=email, hashed_password=hashed_password, full_name=full_name, role_id=1, company_id=company_id, mobile_phone=mobile_phone, is_active=False, user_type=user_type)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: int = 60*24, role: str = None):
    to_encode = data.copy()
    if role:
        to_encode["role"] = role
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_otp(db: Session, user_id: UUID, otp_code: str):
    return db.query(Otp).filter(
        and_(
            Otp.user_id == user_id,
            Otp.otp_code == otp_code,
            Otp.used == False
        )
    ).order_by(Otp.expires_at.desc()).first()

def mark_otp_used(db: Session, otp: Otp):
    otp.used = True
    db.commit()
    db.refresh(otp)
    return otp

def reset_user_password(db: Session, user: User, new_password: str, otp: Otp):
    user.hashed_password = get_password_hash(new_password)
    otp.used = True
    db.commit()
    db.refresh(user)
    db.refresh(otp)
    return user

def get_user_role(db: Session, user: User):
    role = db.query(Role).filter(Role.id == user.role_id).first()
    return role.name if role else None

def generate_and_store_otp(db: Session, user: User, expires_minutes: int = 10):
    otp_code = ''.join(random.choices('0123456789', k=6))
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes)
    otp = Otp(user_id=user.id, otp_code=otp_code, expires_at=expires_at, used=False)
    db.add(otp)
    db.commit()
    db.refresh(otp)
    return otp_code

def get_all_clients(db: Session):
    clients = db.query(Client).all()
   
    return clients

def get_all_users_with_roles(db: Session):
    users = db.query(User).all()
    companies = {c.id: c.name for c in db.query(Company).all()}
    roles = {r.id: r.name for r in db.query(Role).all()}
    enriched_users = []
    for user in users:
        user_dict = user.__dict__.copy()
        user_dict['company_name'] = companies.get(user.company_id)
        user_dict['role_name'] = roles.get(user.role_id)
        user_dict['is_active'] = user.is_active
        enriched_users.append(user_dict)
    return enriched_users

def create_company(db: Session, name: str, industry: str, emr: str = None):
    company = Company(name=name, industry=industry, emr=emr)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company

def generate_device_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def set_email_verification_token(db: Session, user: User, token: str):
    user.email_verification_token = token
    db.commit()
    db.refresh(user)
    return user

def verify_email_token(db: Session, token: str):
    user = db.query(User).filter(User.email_verification_token == token).first()
    if user:
        user.is_email_verified = True
        user.email_verification_token = None
        db.commit()
        db.refresh(user)
    return user

# EMR Type CRUD operations
def create_emr_type(db: Session, name: str, session_type: Optional[str] = None,
                   documentation_methods: Optional[str] = None, files: Optional[List[dict]] = None,
                   instructions: Optional[str] = None, response: Optional[str] = None):
    emr_type = EmrType(
        name=name,
        session_type=session_type,
        documentation_methods=documentation_methods,
        files=files,
        instructions=instructions,
        response=response,
        status='draft'  # Set default status to draft
    )
    db.add(emr_type)
    db.commit()
    db.refresh(emr_type)
    return emr_type

def get_emr_type(db: Session, emr_type_id: UUID):
    return db.query(EmrType).filter(EmrType.id == emr_type_id).first()

def get_all_emr_types(db: Session):
    return db.query(EmrType).all()

def update_emr_type(db: Session, emr_type_id: UUID, name: Optional[str] = None,
                   session_type: Optional[str] = None, documentation_methods: Optional[str] = None,
                   files: Optional[List[dict]] = None, instructions: Optional[str] = None,
                   response: Optional[str] = None, status: Optional[str] = None,
                   total_chunks: Optional[int] = None, processed_chunks: Optional[int] = None):
    print(f"=== DEBUG: update_emr_type called with emr_type_id={emr_type_id}, processed_chunks={processed_chunks}, total_chunks={total_chunks} ===")
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        print(f"=== DEBUG: EMR type not found for id={emr_type_id} ===")
        return None

    if name is not None:
        emr_type.name = name
    if session_type is not None:
        emr_type.session_type = session_type
    if documentation_methods is not None:
        emr_type.documentation_methods = documentation_methods
    if files is not None:
        emr_type.files = files
    if instructions is not None:
        emr_type.instructions = instructions
    if response is not None:
        emr_type.response = response
    if status is not None:
        emr_type.status = status
    if total_chunks is not None:
        emr_type.total_chunks = total_chunks
        print(f"=== DEBUG: Updated total_chunks to {total_chunks} ===")
    if processed_chunks is not None:
        emr_type.processed_chunks = processed_chunks
        print(f"=== DEBUG: Updated processed_chunks to {processed_chunks} ===")

    print(f"=== DEBUG: About to commit database changes ===")
    db.commit()
    print(f"=== DEBUG: Database commit completed ===")
    db.refresh(emr_type)
    print(f"=== DEBUG: Database refresh completed, current processed_chunks={emr_type.processed_chunks} ===")
    return emr_type

def delete_emr_type(db: Session, emr_type_id: UUID):
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        return False

    db.delete(emr_type)
    db.commit()
    return True

# EMR Type Field CRUD operations
def create_emr_type_field(db: Session, name: str, type: str):
    field = EMRTypeField(name=name, type=type)
    db.add(field)
    db.commit()
    db.refresh(field)
    return field

def get_emr_type_field(db: Session, field_id: UUID):
    return db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()

def get_all_emr_type_fields(db: Session):
    return db.query(EMRTypeField).all()

def update_emr_type_field(db: Session, field_id: UUID, name: Optional[str] = None, type: Optional[str] = None):
    field = get_emr_type_field(db, field_id)
    if not field:
        return None

    if name is not None:
        field.name = name
    if type is not None:
        field.type = type

    db.commit()
    db.refresh(field)
    return field

def delete_emr_type_field(db: Session, field_id: UUID):
    field = get_emr_type_field(db, field_id)
    if not field:
        return False

    db.delete(field)
    db.commit()
    return True

# EMR Type Result CRUD operations
def create_emr_type_result(db: Session, emr_type_id: UUID, key: str, value: Optional[str] = None, status: Optional[str] = None, label: Optional[str] = None):
    result = EMRTypeResult(
        emr_type_id=emr_type_id,
        key=key,
        value=value,
        status=status,
        label=label
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result

def get_emr_type_results_by_emr_type(db: Session, emr_type_id: UUID):
    return db.query(EMRTypeResult).filter(EMRTypeResult.emr_type_id == emr_type_id).all()

def delete_all_emr_type_results_by_emr_type(db: Session, emr_type_id: UUID):
    results = db.query(EMRTypeResult).filter(EMRTypeResult.emr_type_id == emr_type_id).all()
    for result in results:
        db.delete(result)
    db.commit()
    return True

# Session CRUD operations
def create_session(db: Session, user_id: UUID, **session_data):
    """Create a new session"""
    # Get the EMR type name from emr_type_id
    emr_type_id = session_data.get('emr_type_id')
    if emr_type_id:
        emr_type = db.query(EmrType).filter(EmrType.id == emr_type_id).first()
        if emr_type:
            session_data['emr_name'] = emr_type.name
    
    session = SessionModel(user_id=user_id, **session_data)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def get_session(db: Session, session_id: UUID):
    """Get session by ID"""
    return db.query(SessionModel).filter(SessionModel.id == session_id).first()

def get_sessions_by_user(db: Session, user_id: UUID):
    """Get all sessions for a specific user"""
    return db.query(SessionModel).filter(SessionModel.user_id == user_id).all()

def get_all_sessions(db: Session):
    """Get all sessions (for super admin)"""
    return db.query(SessionModel).all()

def get_sessions_by_emr_type(db: Session, emr_type_id: UUID):
    """Get all sessions for a specific EMR type"""
    return db.query(SessionModel).filter(SessionModel.emr_type_id == emr_type_id).all()

def get_sessions_by_client(db: Session, client_id: UUID):
    """Get all sessions for a specific client"""
    return db.query(SessionModel).filter(SessionModel.client_id == client_id).all()

def update_session(db: Session, session_id: UUID, **session_data):
    """Update a session"""
    session = get_session(db, session_id)
    if not session:
        return None
    
    for key, value in session_data.items():
        if value is not None:
            setattr(session, key, value)
    
    db.commit()
    db.refresh(session)
    return session

def delete_session(db: Session, session_id: UUID):
    """Delete a session"""
    session = get_session(db, session_id)
    if not session:
        return False
    
    db.delete(session)
    db.commit()
    return True 