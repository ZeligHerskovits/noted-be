from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db import SessionLocal, DATABASE_URL
from ..schemas import UserResponse, CompanyCreate, CompanyResponse
from ..crud import get_all_users_with_roles, create_company
from app.routes.auth import get_current_user_with_role
from ..models import Company, User, Role

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/users", response_model=list[UserResponse])
def list_users(
    current_user = Depends(get_current_user_with_role(["super_admin", "admin"])),
    db: Session = Depends(get_db)
):
    if getattr(current_user, 'role_id', None) == 3:  # super_admin
        users = get_all_users_with_roles(db)
    elif getattr(current_user, 'role_id', None) == 1:  # admin
        users = db.query(User).filter_by(company_id=current_user.company_id).all()
        companies = {c.id: c.name for c in db.query(Company).all()}
        roles = {r.id: r.name for r in db.query(Role).all()}
        enriched_users = []
        for user in users:
            user_dict = user.__dict__.copy()
            user_dict['company_name'] = companies.get(user.company_id)
            user_dict['role_name'] = roles.get(user.role_id)
            user_dict['is_active'] = user.is_active
            enriched_users.append(user_dict)
        users = enriched_users
    else:
        raise HTTPException(status_code=403, detail="Forbidden: Only super admins or admins can access this endpoint.")
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

@router.delete("/users/{user_id}", response_model=dict)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin"]))):
    user_to_delete = db.query(User).filter(User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user_to_delete)
    db.commit()
    return {"detail": "User deleted"}

@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_profile(user_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin", "admin"]))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # super_admin can view any user; admin can only view users from their own company
    if getattr(current_user, 'role_id', None) == 1 and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot view users from another company.")
    if getattr(current_user, 'role_id', None) != 3 and user.id != current_user.id and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot view this user.")
    company = db.query(Company).filter(Company.id == user.company_id).first()
    role_obj = db.query(Role).filter(Role.id == user.role_id).first()
    user_response = UserResponse.from_orm(user)
    user_dict = user_response.dict()
    user_dict['company_name'] = company.name if company else None
    user_dict['role_name'] = role_obj.name if role_obj else None
    user_dict['is_active'] = user.is_active
    user_dict['company'] = CompanyResponse.from_orm(company).dict() if company else None
    return user_dict