from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from ..db import SessionLocal
from ..schemas import (
    CopingSkillCreate, CopingSkillUpdate, CopingSkillResponse,
    ClinicalSpecialtyCreate, ClinicalSpecialtyUpdate, ClinicalSpecialtyResponse,
    DocumentationMethodCreate, DocumentationMethodUpdate, DocumentationMethodResponse,
    ModalityCreate, ModalityUpdate, ModalityResponse,
    ModalityStepCreate, ModalityStepUpdate, ModalityStepResponse,
    ActivityCreate, ActivityUpdate, ActivityResponse,
    SubActivityCreate, SubActivityUpdate, SubActivityResponse,
    EmrTypeFieldResponseCreate, EmrTypeFieldResponseUpdate, EmrTypeFieldResponseRecord
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
    update_documentation_method, delete_documentation_method,
    # Modalities
    create_modality, get_modality, get_all_modalities,
    update_modality, delete_modality,
    # Modality Steps
    create_modality_step, get_modality_step, get_all_modality_steps,
    update_modality_step, delete_modality_step,
    # Activities
    create_activity, get_activity, get_all_activities,
    update_activity, delete_activity,
    # Sub-Activities
    create_sub_activity, get_sub_activity, get_all_sub_activities,
    update_sub_activity, delete_sub_activity,
    create_emr_type_field_response, get_emr_type_field_response,
    get_emr_type_field_responses, update_emr_type_field_response,
    delete_emr_type_field_response, get_emr_type
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

# ==================== MODALITY ROUTES ====================

@router.post("/modalities", response_model=ModalityResponse, status_code=status.HTTP_201_CREATED)
def create_modality_endpoint(
    modality: ModalityCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new modality"""
    return create_modality(db, modality.name, modality.short_term, modality.description, modality.modality_setting)

@router.get("/modalities", response_model=List[ModalityResponse])
def list_modalities(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # All roles
):
    """Get all modalities"""
    return get_all_modalities(db)

@router.get("/modalities/{modality_id}", response_model=ModalityResponse)
def get_modality_endpoint(
    modality_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific modality by ID"""
    modality = get_modality(db, modality_id)
    if not modality:
        raise HTTPException(status_code=404, detail="Modality not found")
    return modality

@router.put("/modalities/{modality_id}", response_model=ModalityResponse)
def update_modality_endpoint(
    modality_id: UUID,
    modality_update: ModalityUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a modality"""
    modality = update_modality(
        db, modality_id,
        modality_update.name,
        modality_update.short_term,
        modality_update.description,
        modality_update.modality_setting
    )
    if not modality:
        raise HTTPException(status_code=404, detail="Modality not found")
    return modality

@router.delete("/modalities/{modality_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modality_endpoint(
    modality_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a modality"""
    success = delete_modality(db, modality_id)
    if not success:
        raise HTTPException(status_code=404, detail="Modality not found")

# ==================== MODALITY STEPS ROUTES ====================

@router.post("/modality-steps", response_model=ModalityStepResponse, status_code=status.HTTP_201_CREATED)
def create_modality_step_endpoint(
    modality_step: ModalityStepCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new modality step"""
    return create_modality_step(db, modality_step.modality_id, modality_step.name)

@router.get("/modality-steps", response_model=List[ModalityStepResponse])
def list_modality_steps(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # All roles
):
    """Get all modality steps"""
    return get_all_modality_steps(db)

@router.get("/modality-steps/{modality_step_id}", response_model=ModalityStepResponse)
def get_modality_step_endpoint(
    modality_step_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific modality step by ID"""
    modality_step = get_modality_step(db, modality_step_id)
    if not modality_step:
        raise HTTPException(status_code=404, detail="Modality step not found")
    return modality_step

@router.put("/modality-steps/{modality_step_id}", response_model=ModalityStepResponse)
def update_modality_step_endpoint(
    modality_step_id: UUID,
    modality_step_update: ModalityStepUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a modality step"""
    modality_step = update_modality_step(
        db, modality_step_id,
        modality_step_update.modality_id,
        modality_step_update.name
    )
    if not modality_step:
        raise HTTPException(status_code=404, detail="Modality step not found")
    return modality_step

@router.delete("/modality-steps/{modality_step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modality_step_endpoint(
    modality_step_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a modality step"""
    success = delete_modality_step(db, modality_step_id)
    if not success:
        raise HTTPException(status_code=404, detail="Modality step not found")

# ==================== ACTIVITY ROUTES ====================

@router.post("/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity_endpoint(
    activity: ActivityCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new activity"""
    return create_activity(db, activity.name, activity.short_term, activity.description, activity.activity_setting)

@router.get("/activities", response_model=List[ActivityResponse])
def list_activities(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # All roles
):
    """Get all activities"""
    return get_all_activities(db)

@router.get("/activities/{activity_id}", response_model=ActivityResponse)
def get_activity_endpoint(
    activity_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific activity by ID"""
    activity = get_activity(db, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity

@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity_endpoint(
    activity_id: UUID,
    activity_update: ActivityUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update an activity"""
    activity = update_activity(
        db, activity_id,
        activity_update.name,
        activity_update.short_term,
        activity_update.description,
        activity_update.activity_setting
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity

@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity_endpoint(
    activity_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete an activity"""
    success = delete_activity(db, activity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Activity not found")

# ==================== SUB-ACTIVITY ROUTES ====================

@router.post("/sub-activities", response_model=SubActivityResponse, status_code=status.HTTP_201_CREATED)
def create_sub_activity_endpoint(
    sub_activity: SubActivityCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new sub-activity"""
    return create_sub_activity(db, sub_activity.activity_id, sub_activity.name)

@router.get("/sub-activities", response_model=List[SubActivityResponse])
def list_sub_activities(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # All roles
):
    """Get all sub-activities"""
    return get_all_sub_activities(db)

@router.get("/sub-activities/{sub_activity_id}", response_model=SubActivityResponse)
def get_sub_activity_endpoint(
    sub_activity_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get a specific sub-activity by ID"""
    sub_activity = get_sub_activity(db, sub_activity_id)
    if not sub_activity:
        raise HTTPException(status_code=404, detail="Sub-activity not found")
    return sub_activity

@router.put("/sub-activities/{sub_activity_id}", response_model=SubActivityResponse)
def update_sub_activity_endpoint(
    sub_activity_id: UUID,
    sub_activity_update: SubActivityUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update a sub-activity"""
    sub_activity = update_sub_activity(
        db, sub_activity_id,
        sub_activity_update.activity_id,
        sub_activity_update.name
    )
    if not sub_activity:
        raise HTTPException(status_code=404, detail="Sub-activity not found")
    return sub_activity

@router.delete("/sub-activities/{sub_activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sub_activity_endpoint(
    sub_activity_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a sub-activity"""
    success = delete_sub_activity(db, sub_activity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sub-activity not found")


def _serialize_emr_type_field_response(db: Session, record) -> EmrTypeFieldResponseRecord:
    emr_type = get_emr_type(db, record.emr_type_id)
    return EmrTypeFieldResponseRecord(
        id=record.id,
        field_name=record.field_name,
        emr_type_id=record.emr_type_id,
        emr_type_name=emr_type.name if emr_type else None,
        response_value=record.response_value,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/emr-type-field-responses", response_model=List[EmrTypeFieldResponseRecord])
def list_emr_type_field_responses(
    emr_type_id: UUID | None = None,
    field_name: str | None = None,
    response_value: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_with_role_id([1, 2, 3]))
):
    """List EMR type field response mappings with optional filters."""
    if response_value is not None and response_value not in {"response 1", "response 2", "response 3"}:
        raise HTTPException(status_code=400, detail="response_value must be one of: response 1, response 2, response 3")

    records = get_emr_type_field_responses(
        db,
        emr_type_id=emr_type_id,
        field_name=field_name,
        response_value=response_value,
    )
    return [_serialize_emr_type_field_response(db, record) for record in records]


@router.post("/emr-type-field-responses", response_model=EmrTypeFieldResponseRecord, status_code=status.HTTP_201_CREATED)
def create_emr_type_field_response_endpoint(
    payload: EmrTypeFieldResponseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_with_role_id([1, 3]))
):
    """Create a new EMR type field response mapping."""
    if not payload.field_name.strip():
        raise HTTPException(status_code=400, detail="field_name cannot be empty")

    emr_type = get_emr_type(db, payload.emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=400, detail="emr_type_id does not exist")

    try:
        record = create_emr_type_field_response(
            db,
            field_name=payload.field_name,
            emr_type_id=payload.emr_type_id,
            response_value=payload.response_value,
            created_by=current_user.id if hasattr(current_user, "id") else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _serialize_emr_type_field_response(db, record)


@router.get("/emr-type-field-responses/{mapping_id}", response_model=EmrTypeFieldResponseRecord)
def get_emr_type_field_response_endpoint(
    mapping_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_with_role_id([1, 2, 3]))
):
    """Get one EMR type field response mapping by id."""
    record = get_emr_type_field_response(db, mapping_id)
    if not record:
        raise HTTPException(status_code=404, detail="EMR type field response not found")
    return _serialize_emr_type_field_response(db, record)


@router.put("/emr-type-field-responses/{mapping_id}", response_model=EmrTypeFieldResponseRecord)
def update_emr_type_field_response_endpoint(
    mapping_id: UUID,
    payload: EmrTypeFieldResponseUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_with_role_id([1, 3]))
):
    """Update one EMR type field response mapping by id."""
    if payload.field_name is not None and not payload.field_name.strip():
        raise HTTPException(status_code=400, detail="field_name cannot be empty")

    if payload.emr_type_id is not None:
        emr_type = get_emr_type(db, payload.emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=400, detail="emr_type_id does not exist")

    try:
        updated = update_emr_type_field_response(
            db,
            mapping_id,
            field_name=payload.field_name,
            emr_type_id=payload.emr_type_id,
            response_value=payload.response_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if not updated:
        raise HTTPException(status_code=404, detail="EMR type field response not found")

    return _serialize_emr_type_field_response(db, updated)


@router.delete("/emr-type-field-responses/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_emr_type_field_response_endpoint(
    mapping_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_with_role_id([1, 3]))
):
    """Delete one EMR type field response mapping by id."""
    success = delete_emr_type_field_response(db, mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="EMR type field response not found")
