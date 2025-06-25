from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db import SessionLocal, DATABASE_URL
from ..schemas import UserResponse, CompanyCreate, CompanyResponse
from ..crud import get_all_users_with_roles, create_company
from app.routes.auth import get_current_user_with_role

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/users", response_model=list[UserResponse])
def list_users(
    current_user = Depends(get_current_user_with_role(["admin", "super_admin"])),
    db: Session = Depends(get_db)
):
    users = get_all_users_with_roles(db)
    return users

# @router.post("/companies", response_model=CompanyResponse)
# def create_company_endpoint(request: CompanyCreate, db: Session = Depends(get_db)):
#     company = create_company(db, request.name, request.industry, request.address)
#     return company

@router.get("/health/db")
def db_health_check():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {
            "status": "ok",
            "connection": DATABASE_URL
        }
    except Exception as e:
        return {
            "status": "fail",
            "detail": str(e),
            "connection": DATABASE_URL
        } 