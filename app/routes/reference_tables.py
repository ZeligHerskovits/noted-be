from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from ..db import SessionLocal
from ..schemas import (
    CopingSkillCreate, CopingSkillUpdate, CopingSkillResponse,
    ClinicalSpecialtyCreate, ClinicalSpecialtyUpdate, ClinicalSpecialtyResponse,
    DocumentationMethodCreate, DocumentationMethodUpdate, DocumentationMethodResponse
)
from ..crud import (
    # Coping Skills
    create_coping_skill, get_coping_skill, get_all_coping_skills, 
    update_coping_skill, delete_coping_skill,
    # Clinical Specialties
    create_clinical_specialty, get_clinical_specialty, get_all_clinical_specialties,
    update_clinical_specialty, delete_clinical_specialty,
    # Documentation Methods
    create_documentation_method, get_documentation_method, get_all_documentation_methods,
    update_documentation_method, delete_documentation_method
)
from app.routes.auth import get_current_user_with_role, get_current_user_with_role_id

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==================== COPING SKILLS ROUTES ====================

@router.post("/coping-skills", response_model=CopingSkillResponse, status_code=status.HTTP_201_CREATED)
def create_coping_skill_endpoint(
    coping_skill: CopingSkillCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new coping skill"""
    return create_coping_skill(db, coping_skill.short_description, coping_skill.long_description)

@router.get("/coping-skills", response_model=List[CopingSkillResponse])
def list_coping_skills(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all coping skills"""
    return get_all_coping_skills(db)

@router.get("/coping-skills/{coping_skill_id}", response_model=CopingSkillResponse)
def get_coping_skill_endpoint(
    coping_skill_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific coping skill by ID"""
    coping_skill = get_coping_skill(db, coping_skill_id)
    if not coping_skill:
        raise HTTPException(status_code=404, detail="Coping skill not found")
    return coping_skill

@router.put("/coping-skills/{coping_skill_id}", response_model=CopingSkillResponse)
def update_coping_skill_endpoint(
    coping_skill_id: UUID,
    coping_skill_update: CopingSkillUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a coping skill"""
    coping_skill = update_coping_skill(
        db, coping_skill_id, 
        coping_skill_update.short_description, 
        coping_skill_update.long_description
    )
    if not coping_skill:
        raise HTTPException(status_code=404, detail="Coping skill not found")
    return coping_skill

@router.delete("/coping-skills/{coping_skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coping_skill_endpoint(
    coping_skill_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a coping skill"""
    success = delete_coping_skill(db, coping_skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Coping skill not found")

# ==================== CLINICAL SPECIALTIES ROUTES ====================

@router.post("/clinical-specialties", response_model=ClinicalSpecialtyResponse, status_code=status.HTTP_201_CREATED)
def create_clinical_specialty_endpoint(
    clinical_specialty: ClinicalSpecialtyCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new clinical specialty"""
    return create_clinical_specialty(db, clinical_specialty.short_description, clinical_specialty.long_description)

@router.get("/clinical-specialties", response_model=List[ClinicalSpecialtyResponse])
def list_clinical_specialties(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all clinical specialties"""
    return get_all_clinical_specialties(db)

@router.get("/clinical-specialties/{clinical_specialty_id}", response_model=ClinicalSpecialtyResponse)
def get_clinical_specialty_endpoint(
    clinical_specialty_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific clinical specialty by ID"""
    clinical_specialty = get_clinical_specialty(db, clinical_specialty_id)
    if not clinical_specialty:
        raise HTTPException(status_code=404, detail="Clinical specialty not found")
    return clinical_specialty

@router.put("/clinical-specialties/{clinical_specialty_id}", response_model=ClinicalSpecialtyResponse)
def update_clinical_specialty_endpoint(
    clinical_specialty_id: UUID,
    clinical_specialty_update: ClinicalSpecialtyUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a clinical specialty"""
    clinical_specialty = update_clinical_specialty(
        db, clinical_specialty_id,
        clinical_specialty_update.short_description,
        clinical_specialty_update.long_description
    )
    if not clinical_specialty:
        raise HTTPException(status_code=404, detail="Clinical specialty not found")
    return clinical_specialty

@router.delete("/clinical-specialties/{clinical_specialty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clinical_specialty_endpoint(
    clinical_specialty_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a clinical specialty"""
    success = delete_clinical_specialty(db, clinical_specialty_id)
    if not success:
        raise HTTPException(status_code=404, detail="Clinical specialty not found")

# ==================== DOCUMENTATION METHODS ROUTES ====================

@router.post("/documentation-methods", response_model=DocumentationMethodResponse, status_code=status.HTTP_201_CREATED)
def create_documentation_method_endpoint(
    documentation_method: DocumentationMethodCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new documentation method"""
    return create_documentation_method(db, documentation_method.name, documentation_method.session_instructions)

@router.get("/documentation-methods", response_model=List[DocumentationMethodResponse])
def list_documentation_methods(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all documentation methods"""
    return get_all_documentation_methods(db)

@router.get("/documentation-methods/{documentation_method_id}", response_model=DocumentationMethodResponse)
def get_documentation_method_endpoint(
    documentation_method_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific documentation method by ID"""
    documentation_method = get_documentation_method(db, documentation_method_id)
    if not documentation_method:
        raise HTTPException(status_code=404, detail="Documentation method not found")
    return documentation_method

@router.put("/documentation-methods/{documentation_method_id}", response_model=DocumentationMethodResponse)
def update_documentation_method_endpoint(
    documentation_method_id: UUID,
    documentation_method_update: DocumentationMethodUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a documentation method"""
    documentation_method = update_documentation_method(
        db, documentation_method_id,
        documentation_method_update.name,
        documentation_method_update.session_instructions
    )
    if not documentation_method:
        raise HTTPException(status_code=404, detail="Documentation method not found")
    return documentation_method

@router.delete("/documentation-methods/{documentation_method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_documentation_method_endpoint(
    documentation_method_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a documentation method"""
    success = delete_documentation_method(db, documentation_method_id)
    if not success:
        raise HTTPException(status_code=404, detail="Documentation method not found")
