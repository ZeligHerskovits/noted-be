from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Company, User, Role
from ..schemas import CompanyResponse, CompanyCreate, CompanyUpdate
from app.routes.auth import get_current_user_with_role
from uuid import UUID

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/companies", response_model=list[CompanyResponse], tags=["Companies"])
def list_companies(
    current_user = Depends(get_current_user_with_role(["super_admin"])),
    db: Session = Depends(get_db)
):
    if getattr(current_user, 'role_id', None) != 3:
        raise HTTPException(status_code=403, detail="Forbidden: Only super admins can access this endpoint.")
    companies = db.query(Company).all()
    return companies

@router.put("/company/{company_id}", response_model=CompanyResponse)
def update_company(company_id: UUID, update: CompanyUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["admin", "super_admin", "user", "standard"]))):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    update_data = update.dict(exclude_unset=True)
    # Only superadmin (role_id == 3) can update is_active
    if 'is_active' in update_data and getattr(current_user, 'role_id', None) != 3:
        raise HTTPException(status_code=403, detail="Only superadmins can change the is_active field.")
    # If company is being deactivated, deactivate all its users
    if 'is_active' in update_data and update_data['is_active'] is False:
        db.query(User).filter(User.company_id == company_id).update({User.is_active: False})
    for key, value in update_data.items():
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return company

@router.get("/companies/{company_id}")
def get_company_with_users(company_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin"]))):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    users = db.query(User).filter(User.company_id == company_id).all()
    roles = {r.id: r.name for r in db.query(Role).all()}
    user_list = []
    for user in users:
        user_list.append({
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role_id": user.role_id,
            "role_name": roles.get(user.role_id),
            "is_active": user.is_active,
            "user_type": user.user_type
        })
    company_dict = company.__dict__.copy()
    company_dict['users'] = user_list
    return company_dict 