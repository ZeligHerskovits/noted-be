from fastapi import APIRouter, HTTPException, Depends, Security
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..schemas import RegisterRequest, LoginRequest, TokenResponse, OTPVerifyRequest, ResetPasswordRequest, ForgotPasswordRequest, UserResponse
from ..crud import get_user_by_email, create_user, verify_password, create_access_token, get_user_otp, mark_otp_used, reset_user_password, get_user_role, generate_and_store_otp
import datetime
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from typing import List

router = APIRouter()

security = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user_with_role(required_roles: List[str]):
    def dependency(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
        token = credentials.credentials
        try:
            payload = jwt.decode(token, "your_secret_key_here", algorithms=["HS256"])
            email = payload.get("sub")
            role = payload.get("role")
            if not email or not role:
                raise HTTPException(status_code=401, detail="Invalid token")
            if role not in required_roles:
                raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
            user = get_user_by_email(db, email)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            return user
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    return dependency

@router.post("/auth/register")
def register_user(request: RegisterRequest, db: Session = Depends(get_db)):
    if get_user_by_email(db, request.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = create_user(db, request.email, request.password, request.full_name, request.company_id)
    return {"success": True, "user_id": user.id}

@router.post("/auth/login", response_model=TokenResponse)
def login_user(request: LoginRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    role = get_user_role(db, user)
    token = create_access_token({"sub": user.email}, role=role)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/auth/verify-otp")
def verify_otp(request: OTPVerifyRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    otp = get_user_otp(db, user.id, request.otp_code)
    if not otp:
        raise HTTPException(status_code=400, detail="OTP not found or already used")
    if otp.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")
    mark_otp_used(db, otp)
    return {"success": True, "message": "OTP verified successfully"}

@router.post("/auth/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    otp = get_user_otp(db, user.id, request.otp_code)
    if not otp:
        raise HTTPException(status_code=400, detail="OTP not found or already used")
    if otp.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")
    reset_user_password(db, user, request.new_password, otp)
    return {"success": True, "message": "Password reset successful"}

@router.post("/auth/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    otp_code = generate_and_store_otp(db, user)
    print(f"[SIMULATED EMAIL] OTP for {user.email}: {otp_code}")
    return {"success": True, "message": "OTP sent (simulated)"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user = Depends(get_current_user_with_role(["admin", "super_admin", "user"]))):
    return current_user

admin_only = get_current_user_with_role(["admin"])

@router.get("/admin/dashboard")
def admin_dashboard(current_user = Depends(admin_only)):
    return {"message": "Welcome Admin"}
 