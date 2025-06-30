from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Company
from ..schemas import CompanyResponse
from app.routes.auth import get_current_user_with_role

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/companies", response_model=list[CompanyResponse], tags=["Companies"])
def list_companies(
    current_user = Depends(get_current_user_with_role(["admin", "super_admin"])),
    db: Session = Depends(get_db)
):
    if getattr(current_user, 'role_id', None) != 1:
        raise HTTPException(status_code=403, detail="Forbidden: Only admins can access this endpoint.")
    companies = db.query(Company).all()
    return companies 