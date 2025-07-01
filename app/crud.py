from sqlalchemy.orm import Session
from .models import User, Otp, Role, Company
from passlib.context import CryptContext
import jwt
import datetime
from sqlalchemy import and_
import random
import secrets
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password: str, full_name: str, company_id: int):
    hashed_password = get_password_hash(password)
    user = User(email=email, hashed_password=hashed_password, full_name=full_name, role_id=2, company_id=company_id)
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

def get_user_otp(db: Session, user_id: int, otp_code: str):
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

def get_all_users_with_roles(db: Session):
    users = db.query(User).all()
    companies = {c.id: c.name for c in db.query(Company).all()}
    roles = {r.id: r.name for r in db.query(Role).all()}
    enriched_users = []
    for user in users:
        user_dict = user.__dict__.copy()
        user_dict['company_name'] = companies.get(user.company_id)
        user_dict['role_name'] = roles.get(user.role_id)
        enriched_users.append(user_dict)
    return enriched_users

def create_company(db: Session, name: str, industry: str = None, address: str = None):
    company = Company(name=name, industry=industry, address=address)
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