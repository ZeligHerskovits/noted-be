from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db import SessionLocal, DATABASE_URL
from ..schemas import UserResponse, CompanyCreate, CompanyResponse, UserUpdate
from ..crud import get_all_users_with_roles, create_company, update_user_with_relations
from app.routes.auth import get_current_user_with_role, get_current_user_with_role_id
from ..models import Company, User, Role
from uuid import UUID

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/users", response_model=list[UserResponse])
def list_users(
    current_user = Depends(get_current_user_with_role_id([1, 3])),  # Role 1 (admin) and Role 3 (super_admin)
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
def delete_user(user_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role_id([3]))):  # Only Role 3 (super_admin)
    user_to_delete = db.query(User).filter(User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user_to_delete)
    db.commit()
    return {"detail": "User deleted"}

@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_profile(user_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role_id([1, 3]))):  # Role 1 (admin) and Role 3 (super_admin)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # super_admin can view any user; admin can only view users from their own company
    if getattr(current_user, 'role_id', None) == 1 and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot view users from another company.")
    company = db.query(Company).filter(Company.id == user.company_id).first()
    role_obj = db.query(Role).filter(Role.id == user.role_id).first()
    user_response = UserResponse.from_orm(user)
    user_dict = user_response.dict()
    user_dict['company_name'] = company.name if company else None
    user_dict['role_name'] = role_obj.name if role_obj else None
    user_dict['is_active'] = user.is_active
    user_dict['company'] = CompanyResponse.from_orm(company).dict() if company else None
    
    # Add junction table data
    from ..models import UserEmrType, UserDocumentationMethod, UserCopingSkill, UserClinicalSpecialty
    user_dict['emr_types'] = [j.emr_type_id for j in db.query(UserEmrType).filter(UserEmrType.user_id == user_id).all()]
    user_dict['documentation_methods'] = [j.documentation_method_id for j in db.query(UserDocumentationMethod).filter(UserDocumentationMethod.user_id == user_id).all()]
    user_dict['coping_skills'] = [j.coping_skill_id for j in db.query(UserCopingSkill).filter(UserCopingSkill.user_id == user_id).all()]
    user_dict['clinical_specialties'] = [j.clinical_specialty_id for j in db.query(UserClinicalSpecialty).filter(UserClinicalSpecialty.user_id == user_id).all()]
    # Handle type_writing - SQLAlchemy already converts PostgreSQL array to Python list
    if user.type_writing:
        if isinstance(user.type_writing, list):
            user_dict['type_writing'] = user.type_writing
        else:
            # Fallback for string format
            array_str = str(user.type_writing).strip('{}')
            if array_str:
                user_dict['type_writing'] = [item.strip('"') for item in array_str.split(',')]
            else:
                user_dict['type_writing'] = []
    else:
        user_dict['type_writing'] = []
    
    return user_dict

@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    update: UserUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 3]))  # Role 1 (admin) and Role 3 (super_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Only super_admin can update any user; admin can only update users from their own company
    if getattr(current_user, 'role_id', None) == 1 and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot update users from another company.")
    # Prevent duplicate email only if changed
    if update.email and update.email != user.email:
        existing = db.query(User).filter(User.email == update.email, User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use.")
    
    # Use the new update function that handles junction tables
    updated_user = update_user_with_relations(db, user_id, **update.dict(exclude_unset=True))
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Enrich user with company_name, role_name, is_active, and company info
    company = db.query(Company).filter(Company.id == updated_user.company_id).first()
    role = db.query(Role).filter(Role.id == updated_user.role_id).first()
    
    # Get related data from junction tables
    from ..models import UserEmrType, UserDocumentationMethod, UserCopingSkill, UserClinicalSpecialty
    user_dict = updated_user.__dict__.copy()
    user_dict['company_name'] = company.name if company else None
    user_dict['role_name'] = role.name if role else None
    user_dict['is_active'] = updated_user.is_active
    user_dict['company'] = CompanyResponse.from_orm(company).dict() if company else None
    
    # Add junction table data
    user_dict['emr_types'] = [j.emr_type_id for j in db.query(UserEmrType).filter(UserEmrType.user_id == user_id).all()]
    user_dict['documentation_methods'] = [j.documentation_method_id for j in db.query(UserDocumentationMethod).filter(UserDocumentationMethod.user_id == user_id).all()]
    user_dict['coping_skills'] = [j.coping_skill_id for j in db.query(UserCopingSkill).filter(UserCopingSkill.user_id == user_id).all()]
    user_dict['clinical_specialties'] = [j.clinical_specialty_id for j in db.query(UserClinicalSpecialty).filter(UserClinicalSpecialty.user_id == user_id).all()]
    # Handle type_writing - SQLAlchemy already converts PostgreSQL array to Python list
    if updated_user.type_writing:
        if isinstance(updated_user.type_writing, list):
            user_dict['type_writing'] = updated_user.type_writing
        else:
            # Fallback for string format
            array_str = str(updated_user.type_writing).strip('{}')
            if array_str:
                user_dict['type_writing'] = [item.strip('"') for item in array_str.split(',')]
            else:
                user_dict['type_writing'] = []
    else:
        user_dict['type_writing'] = []
    
    return user_dict