from fastapi import APIRouter, HTTPException, Depends, Security, Response, Cookie, Request, Body
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..schemas import RegisterRequest, LoginRequest, TokenResponse, OTPVerifyRequest, ResetPasswordRequest, ForgotPasswordRequest, UserResponse
from ..crud import get_user_by_email, create_user, verify_password, create_access_token, get_user_otp, mark_otp_used, reset_user_password, get_user_role, generate_and_store_otp, create_company, generate_device_token, get_password_hash
import datetime
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from typing import List
import secrets
from ..models import TrustedDevice
import smtplib
from email.mime.text import MIMEText
import os
import subprocess
import sys

router = APIRouter()

security = HTTPBearer()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 2525))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL")
SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
FRONTEND_RESET_URL = os.getenv("FRONTEND_RESET_URL", "https://noteddevapi.objectif.solutions/reset-password")

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
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
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
    # Create company
    company = create_company(db, request.company_name, request.industry, request.address)
    # Create user with new company_id
    user = create_user(db, request.email, request.password, request.full_name, company.id)
    return {"success": True, "user_id": user.id, "company_id": company.id}

def send_email_via_msmtp(to_email, subject, body):
    if sys.platform.startswith("linux"):
        msmtp_path = "/usr/bin/msmtp"
        message = f"Subject: {subject}\nTo: {to_email}\nContent-Type: text/html; charset=utf-8\n\n{body}"
        try:
            process = subprocess.Popen(
                [msmtp_path, '-t', to_email],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate(message.encode())
            print("msmtp stdout:", stdout.decode())
            print("msmtp stderr:", stderr.decode())
            if process.returncode != 0:
                raise Exception(f"msmtp failed: {stderr.decode()}")
        except Exception as e:
            print(f"msmtp error: {e}")
            raise
    else:
        # Use smtplib for local development (Windows, Mac, etc.)
        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(FROM_EMAIL, to_email, msg.as_string())
            print("Email sent via smtplib (local)")
        except Exception as e:
            print(f"smtplib error: {e}")
            raise

def send_otp_email(to_email, otp_code):
    subject = "Noted: Your One-Time Password (OTP)"
    unsubscribe_url = "http://tracking.objectif.solutions/tracking/unsubscribe?d=B0yk-4Chqqgb0sZf1VnZ4u_RYT2O8lK8V933mXwu3lIqtOmDXaT3R1TLDms8Q3sj5u3oWCs26xm6Xgalni2FadXpH1j8givO2mgtis0kqn7a0"
    body = f"""
    <html>
      <body>
        <p>Hello,</p>
        <p>You are attempting to log in to your Noted account. Please use the following One-Time Password (OTP) to complete your login:</p>
        <pre style='font-size: 1.5em; text-align: center; background: #f4f4f4; padding: 10px; border-radius: 5px;'>{otp_code}</pre>
        <p>This code will expire in 10 minutes. If you did not request this, please ignore this email.</p>
        <hr>
        <p style='font-size:12px;text-align:center;'>
          <a href=\"{unsubscribe_url}\">Unsubscribe</a>
        </p>
        <p>Thank you,<br>The Noted Team</p>
      </body>
    </html>
    """
    send_email_via_msmtp(to_email, subject, body)

def send_reset_link(to_email, token):
    subject = "Noted: Password Reset Request"
    reset_url = f"https://noteddev.objectif.solutions/reset-password?email={to_email}&token={token}"
    unsubscribe_url = "http://tracking.objectif.solutions/tracking/unsubscribe?d=u2VKjc2xLLiY-svH9kVVC_wRXAgzpNBv5TIQltowX5aWunCMyu6IPTJpkOOPW9SP3zWvuyn0oO4UJbL4Iwqo42RVWLBciy6OT9ehUkA5UwmV0"
    body = f"""
<html>
  <body>
    <p>Hello,</p>
    <p>We received a request to reset your Noted account password. To reset your password, please click the button below:</p>
    <p style='text-align:center;'>
      <a href='{reset_url}' style='display:inline-block;padding:10px 20px;background-color:#3b82f6;color:#fff;text-decoration:none;border-radius:5px;font-size:16px;'>Reset Password</a>
    </p>
    <p>If you did not request a password reset, you can safely ignore this email.</p>
    <hr>
    <p style='font-size:12px;text-align:center;'>
      <a href='{unsubscribe_url}'>Unsubscribe</a>
    </p>
    <p>Thank you,<br>The Noted Team</p>
  </body>
</html>
"""
    send_email_via_msmtp(to_email, subject, body)

@router.post("/auth/login")
def login_user(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    device_id = request.deviceId
    if user.trusted_devices and device_id in user.trusted_devices:
        # Device is trusted, skip OTP
        role = get_user_role(db, user)
        token = create_access_token({"sub": user.email}, role=role)
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=False  # Set to True in production with HTTPS
        )
        return {"access_token": token, "token_type": "bearer", "otpRequired": False}
    else:
        otp_code = generate_and_store_otp(db, user)
        send_otp_email(user.email, otp_code)
        return {"otpRequired": True, "message": "OTP sent to email", "email": user.email}

@router.post("/auth/verify-otp")
def verify_otp(request: OTPVerifyRequest, response: Response, db: Session = Depends(get_db)):
    user = get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    otp = get_user_otp(db, user.id, request.otp_code)
    if not otp:
        raise HTTPException(status_code=400, detail="OTP not found or already used")
    if otp.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")
    mark_otp_used(db, otp)
    device_id = request.deviceId
    if not user.trusted_devices:
        user.trusted_devices = []
    if device_id not in user.trusted_devices:
        user.trusted_devices.append(device_id)
        db.commit()
        db.refresh(user)
    # Issue JWT as cookie
    role = get_user_role(db, user)
    token = create_access_token({"sub": user.email}, role=role)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )
    return {"success": True, "access_token": token, "token_type": "bearer"}

@router.post("/auth/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    print("SECRET_KEY in reset-password:", SECRET_KEY)
    print("Received token:", request.token)
    # Decode and verify the token to get the user's email or id
    try:
        payload = jwt.decode(request.token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token: no user info")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    # Set the new password
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    db.refresh(user)
    return {"success": True, "message": "Password reset successful"}

@router.post("/auth/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    print("SECRET_KEY in forgot-password:", SECRET_KEY)
    user = get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    # Generate a JWT reset token
    import datetime
    reset_token = jwt.encode(
        {
            "sub": user.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        },
        SECRET_KEY,
        algorithm="HS256"
    )
    send_reset_link(user.email, reset_token)
    return {"success": True, "message": "Password reset link sent (simulated)"}

@router.get("/me", response_model=UserResponse)
def get_me(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["admin", "super_admin", "user", "standard"]))):
    # Try to get token from cookie if not in header
    token = request.cookies.get("access_token")
    if not token:
        # Fallback to dependency (which checks header)
        return current_user
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = get_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

admin_only = get_current_user_with_role(["admin"])

@router.get("/admin/dashboard")
def admin_dashboard(current_user = Depends(admin_only)):
    return {"message": "Welcome Admin"}

@router.post("/auth/resend-otp")
def resend_otp(request: dict = Body(...), db: Session = Depends(get_db)):
    email = request.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    otp_code = generate_and_store_otp(db, user)
    send_otp_email(user.email, otp_code)
    return {"detail": "OTP sent"}
 