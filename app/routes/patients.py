from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Patient
from typing import List
from app.schemas import PatientCreate, PatientUpdate, PatientResponse
import logging
from app.routes.auth import get_current_user_with_role
from datetime import date

router = APIRouter(prefix="/api/patients", tags=["patients"])

logger = logging.getLogger("patients")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=List[PatientResponse])
def list_patients(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print("GET /api/patients called")
    try:
        if current_user.role_id == 3:  # super_admin
            patients = db.query(Patient).all()
        else:  # admin or standard
            patients = db.query(Patient).filter(Patient.user_id == current_user.id).all()
        return patients
    except Exception as e:
        logger.error(f"Error fetching patients: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch patients")

@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    patient: PatientCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print(f"POST /api/patients called with: {patient}")
    try:
        patient_data = patient.dict(exclude={"user_id"})  # Remove user_id from request
        patient_data["user_id"] = current_user.id  # Assign from token/session
        # Use date_of_birth from frontend (no hardcoding)
        new_patient = Patient(**patient_data)
        db.add(new_patient)
        db.commit()
        db.refresh(new_patient)
        return new_patient
    except Exception as e:
        logger.error(f"Error creating patient: {e}")
        raise HTTPException(status_code=500, detail="Failed to create patient")

@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(patient_id: int, patient: PatientUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))):
    print(f"PUT /api/patients/{patient_id} called with: {patient}")
    try:
        db_patient = db.query(Patient).filter(Patient.id == patient_id, Patient.user_id == current_user.id).first()
        if not db_patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        for key, value in patient.dict(exclude_unset=True).items():
            setattr(db_patient, key, value)
        db.commit()
        db.refresh(db_patient)
        return db_patient
    except Exception as e:
        logger.error(f"Error updating patient: {e}")
        raise HTTPException(status_code=500, detail="Failed to update patient")

@router.delete("/{patient_id}", response_model=dict)
def delete_patient(patient_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))):
    print(f"DELETE /api/patients/{patient_id} called")
    try:
        db_patient = db.query(Patient).filter(Patient.id == patient_id, Patient.user_id == current_user.id).first()
        if not db_patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        db.delete(db_patient)
        db.commit()
        return {"detail": "Patient deleted"}
    except Exception as e:
        logger.error(f"Error deleting patient: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete patient") 