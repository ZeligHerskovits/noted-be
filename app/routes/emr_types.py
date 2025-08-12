from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import base64
import json
import boto3
import os
import certifi
import mimetypes
from datetime import datetime
from pydantic import BaseModel
os.environ['SSL_CERT_FILE'] = certifi.where()

from ..db import get_db
from ..routes.auth import get_current_user_with_role
from ..schemas import (
    EmrTypeCreate, EmrTypeUpdate, EmrTypeResponse, EmrTypeFile,
    EMRTypeFieldCreate, EMRTypeFieldUpdate, EMRTypeFieldResponse,
    EMRTypeResultCreate, EMRTypeResultResponse, EmrTypeResponseOnly,
    UpdateResultInstructionsRequest, EMRTypeResultInstructionsOnly,
    UpdateResultStatusRequest
)
from ..crud import (
    create_emr_type, get_emr_type, get_all_emr_types, 
    update_emr_type, delete_emr_type,
    create_emr_type_result, get_emr_type_results_by_emr_type, delete_all_emr_type_results_by_emr_type
)

router = APIRouter(prefix="/emr-types", tags=["EMR Types"])
fields_router = APIRouter(prefix="/emr-types-fields", tags=["EMR Type Fields"])

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
    verify=False
)
def upload_file_to_s3(file_content, filename, content_type=None):
    s3_bucket = os.getenv("S3_BUCKET_NAME")
    if not s3_bucket:
        raise ValueError("S3_BUCKET_NAME environment variable is not set")
    
    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)
    s3.put_object(Bucket=s3_bucket, Key=filename, Body=file_content, ContentType=content_type or 'application/octet-stream')
    region = os.getenv("AWS_REGION")
    url = f"https://{s3_bucket}.s3.{region}.amazonaws.com/{filename}"
    return url

def generate_presigned_url(bucket, key, expiration=300):
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )

# Helper to update file URLs to signed URLs for a list of file dicts
def with_signed_urls(files):
    if not files:
        return []
    
    s3_bucket = os.getenv("S3_BUCKET_NAME")
    if not s3_bucket:
        return files  # Return original files if S3_BUCKET_NAME is not set
    
    signed_files = []
    for f in files:
        # Extract the S3 key from the URL stored in DB
        # Assumes URL is in the form https://{bucket}.s3.amazonaws.com/{key}
        url = f.get('url')
        if url and url.startswith(f"https://{s3_bucket}.s3.amazonaws.com/"):
            key = url[len(f"https://{s3_bucket}.s3.amazonaws.com/"):]
            signed_url = generate_presigned_url(s3_bucket, key)
            f = dict(f)
            f['url'] = signed_url
        signed_files.append(f)
    return signed_files

@router.post("/", response_model=EmrTypeResponse)
async def create_emr_type_with_files(
    name: str = Form(...),
    session_type: Optional[str] = Form(None),
    documentation_methods: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    files_data = []
    if files:
        for file in files:
            file_content = await file.read()
            content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
            file_url = upload_file_to_s3(file_content, file.filename, content_type)
            files_data.append({
                "name": file.filename,
                "url": file_url,
                "type": content_type,
                "size": len(file_content)
            })
    emr_type = create_emr_type(
        db=db,
        name=name,
        session_type=session_type,
        documentation_methods=documentation_methods,
        files=files_data
    )
    return emr_type

@router.get("/", response_model=List[EmrTypeResponse])
def get_all_emr_types_endpoint(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get all EMR types"""
    try:
        emr_types = get_all_emr_types(db)
        # Patch: update file URLs to signed URLs
        for emr in emr_types:
            if hasattr(emr, 'files'):
                emr.files = with_signed_urls(emr.files)
        return emr_types
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching EMR types: {str(e)}")

@router.get("/{emr_type_id}")
def get_emr_type_endpoint(
    emr_type_id: UUID, 
    response_only: bool = False, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get a specific EMR type by ID"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        # If response_only is requested, return only the response
        if response_only:
            return EmrTypeResponseOnly(response=emr_type.response)
        
        # Patch: update file URLs to signed URLs
        if hasattr(emr_type, 'files'):
            emr_type.files = with_signed_urls(emr_type.files)
        return EmrTypeResponse.from_orm(emr_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching EMR type: {str(e)}")

# EMR Type Results - GET endpoint for frontend display
@router.get("/{emr_type_id}/results")
def get_emr_type_results(
    emr_type_id: UUID, 
    instructions_only: bool = False, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get all results for a specific EMR type (for frontend display)"""
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    
    if instructions_only:
        # Return only key value and instructions
        return [EMRTypeResultInstructionsOnly(key=result.key, value=result.value, instructions=result.instructions) for result in results]
    
    return [EMRTypeResultResponse.from_orm(result) for result in results]

# EMR Type Results - Update instructions endpoint (MUST BE BEFORE GENERAL PUT)
@router.put("/{emr_type_id}/instructions")
def update_result_instructions(
    emr_type_id: UUID,
    request: UpdateResultInstructionsRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Update instructions for a specific EMR type result by key"""
    from ..models import EMRTypeResult
    
    # Get the result by emr_type_id and key and value
    result = db.query(EMRTypeResult).filter(
        EMRTypeResult.emr_type_id == emr_type_id,
        EMRTypeResult.key == request.key,
        EMRTypeResult.value == request.value
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # Update the instructions
    result.instructions = request.instructions
    db.commit()
    db.refresh(result)
    
    # Update EMR type status to 'draft' since instructions were changed
    update_emr_type(db, emr_type_id, status='draft')
    print(f"=== DEBUG: Updated EMR type status to 'draft' after instruction change ===")
    
    return {
        "message": "Instructions updated successfully"
    }

# EMR Type Results - Update status endpoint
@router.put("/{emr_type_id}/status")
def update_result_status(
    emr_type_id: UUID,
    request: UpdateResultStatusRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Update status for a specific EMR type result by key and value"""
    from ..models import EMRTypeResult
    
    # Get the result by emr_type_id and key and value
    result = db.query(EMRTypeResult).filter(
        EMRTypeResult.emr_type_id == emr_type_id,
        EMRTypeResult.key == request.key,
        EMRTypeResult.value == request.value
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # Validate status value
    valid_statuses = ['found', 'not found', 'ignore', 'confirmed']
    if request.status.lower() not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Update the status (store in lowercase)
    result.status = request.status.lower()
    db.commit()
    db.refresh(result)
    
    print(f"=== DEBUG: Updated status for {request.key} to {result.status} ===")
    
    return {
        "message": "Status updated successfully",
        "key": request.key,
        "value": request.value,
        "status": result.status
    }

@router.put("/{emr_type_id}/back-action")
def back_action_emr_type(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """
    Check if there are any key-value results for this EMR type and update status accordingly.
    If there are results, set status to 'analyzed', otherwise set to 'draft'.
    """
    # Get the EMR type
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Check if there are any results for this EMR type
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    
    # Determine new status based on whether results exist
    if results:
        new_status = "analyzed"
    else:
        new_status = "draft"
    
    # Update the EMR type status
    updated_emr_type = update_emr_type(
        db=db,
        emr_type_id=emr_type_id,
        status=new_status
    )
    
    return {
        "message": f"EMR type status updated to '{new_status}'"
    }

@router.put("/{emr_type_id}", response_model=EmrTypeResponse)
async def update_emr_type_with_files(
    emr_type_id: UUID,
    name: Optional[str] = Form(None),
    session_type: Optional[str] = Form(None),
    documentation_methods: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    instructions: Optional[str] = Form(None),
    clear_files: Optional[bool] = Form(False),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    # Get existing EMR type to preserve files if not updating them
    existing_emr_type = get_emr_type(db, emr_type_id)
    if not existing_emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    update_data = {}
    if name is not None:
        update_data['name'] = name
    if session_type is not None:
        update_data['session_type'] = session_type
    if documentation_methods is not None:
        update_data['documentation_methods'] = documentation_methods
    if instructions is not None:
        update_data['instructions'] = instructions

    # Handle files: clear existing files if requested, then upload new files if provided
    if clear_files:
        # Clear existing files first
        update_data['files'] = []
    
    # If new files are provided, upload them (this will replace any existing files)
    if files is not None:
        files_data = []
        for file in files:
            file_content = await file.read()
            content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
            file_url = upload_file_to_s3(file_content, file.filename, content_type)
            files_data.append({
                "name": file.filename,
                "url": file_url,
                "type": content_type,
                "size": len(file_content)
            })
        update_data['files'] = files_data
    # If files is None and clear_files is False, don't update the files field - keep existing files

    updated_emr_type = update_emr_type(
        db=db,
        emr_type_id=emr_type_id,
        **update_data
    )
    if not updated_emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    if hasattr(updated_emr_type, 'files'):
        updated_emr_type.files = with_signed_urls(updated_emr_type.files)
    return updated_emr_type

@router.delete("/{emr_type_id}")
def delete_emr_type_endpoint(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Delete an EMR type"""
    try:
        success = delete_emr_type(db, emr_type_id)
        if not success:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        return {"message": "EMR type deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting EMR type: {str(e)}")

@router.post("/{emr_type_id}/upload-files")
def upload_files_to_emr_type(
    emr_type_id: UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Upload files to an existing EMR type"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        # Read existing files or initialize empty list
        existing_files = emr_type.files or []
        
        # Process uploaded files
        for file in files:
            file_content = file.file.read()
            content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
            file_url = upload_file_to_s3(file_content, file.filename, content_type)
            file_data = {
                "name": file.filename,
                "url": file_url,
                "type": content_type,
                "size": len(file_content)
            }
            existing_files.append(file_data)
        
        # Update the EMR type with new files
        updated_emr_type = update_emr_type(
            db=db,
            emr_type_id=emr_type_id,
            files=existing_files
        )
        
        return {"message": f"Successfully uploaded {len(files)} files", "emr_type": updated_emr_type}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error uploading files: {str(e)}")

@router.get("/{emr_type_id}/files")
def get_emr_type_files(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get all files for a specific EMR type"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        # Patch: update file URLs to signed URLs
        return {"files": with_signed_urls(emr_type.files or [])}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching files: {str(e)}")

@router.delete("/{emr_type_id}/files/{file_index}")
def remove_file_from_emr_type(
    emr_type_id: UUID, 
    file_index: int, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Remove a specific file from an EMR type by index"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        existing_files = emr_type.files or []
        
        if file_index < 0 or file_index >= len(existing_files):
            raise HTTPException(status_code=400, detail="Invalid file index")
        
        # Remove the file at the specified index
        removed_file = existing_files.pop(file_index)
        
        # Update the EMR type with the modified files list
        updated_emr_type = update_emr_type(
            db=db,
            emr_type_id=emr_type_id,
            files=existing_files
        )
        
        return {
            "message": f"Successfully removed file: {removed_file['name']}",
            "removed_file": removed_file,
            "remaining_files_count": len(existing_files)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error removing file: {str(e)}")

@router.put("/{emr_type_id}/files")
def replace_all_files_in_emr_type(
    emr_type_id: UUID,
    files: List[EmrTypeFile],
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Replace all files in an EMR type with new files"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        # Convert files to the format expected by the database
        files_data = [file.dict() for file in files]
        
        # Update the EMR type with new files (replaces all existing files)
        updated_emr_type = update_emr_type(
            db=db,
            emr_type_id=emr_type_id,
            files=files_data
        )
        
        return {
            "message": f"Successfully replaced all files. New file count: {len(files_data)}",
            "emr_type": updated_emr_type
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error replacing files: {str(e)}")

@router.delete("/{emr_type_id}/files")
def remove_all_files_from_emr_type(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Remove all files from an EMR type"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        # Update the EMR type with empty files list
        updated_emr_type = update_emr_type(
            db=db,
            emr_type_id=emr_type_id,
            files=[]
        )
        
        return {
            "message": "Successfully removed all files from EMR type",
            "emr_type": updated_emr_type
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error removing all files: {str(e)}")

@router.put("/{emr_type_id}/finalize")
def finalize_emr_type(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """
    Finalize an EMR type by changing its status to 'active'.
    Only works if current status is 'Generated'.
    """
    # Get the EMR type
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Check if current status is 'draft' or 'analyzed'
    if emr_type.status in ["draft", "analyzed", "processing"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot finalize EMR type. Current status is '{emr_type.status}', but only 'generated' status can be finalized."
        )
    
    # Update status to 'active'
    updated_emr_type = update_emr_type(
        db=db,
        emr_type_id=emr_type_id,
        status="active"
    )
    
    return {
        "message": "EMR type finalized successfully",
        "emr_type": updated_emr_type
    }

# EMR Type Fields CRUD operations
def create_emr_type_field(db: Session, name: str, type: str):
    """Create a new EMR type field"""
    from ..models import EMRTypeField
    db_field = EMRTypeField(name=name, type=type)
    db.add(db_field)
    db.commit()
    db.refresh(db_field)
    return db_field

def get_emr_type_field(db: Session, field_id: UUID):
    """Get EMR type field by ID"""
    from ..models import EMRTypeField
    return db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()

def get_all_emr_type_fields(db: Session):
    """Get all EMR type fields"""
    from ..models import EMRTypeField
    return db.query(EMRTypeField).all()

def update_emr_type_field(db: Session, field_id: UUID, name: Optional[str] = None, type: Optional[str] = None):
    """Update EMR type field"""
    from ..models import EMRTypeField
    db_field = db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()
    if not db_field:
        return None
    
    if name is not None:
        db_field.name = name
    if type is not None:
        db_field.type = type
    
    db.commit()
    db.refresh(db_field)
    return db_field

def delete_emr_type_field(db: Session, field_id: UUID):
    """Delete EMR type field"""
    from ..models import EMRTypeField
    db_field = db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()
    if not db_field:
        return False
    
    db.delete(db_field)
    db.commit()
    return True

# EMR Type Fields API Endpoints
@fields_router.post("/", response_model=EMRTypeFieldResponse)
def create_field(
    field: EMRTypeFieldCreate, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Create a new EMR type field"""
    db_field = create_emr_type_field(db, name=field.name, type=field.type)
    return db_field

@fields_router.get("/", response_model=List[EMRTypeFieldResponse])
def get_fields(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get all EMR type fields"""
    return get_all_emr_type_fields(db)

@fields_router.get("/{field_id}", response_model=EMRTypeFieldResponse)
def get_field(
    field_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Get EMR type field by ID"""
    db_field = get_emr_type_field(db, field_id)
    if not db_field:
        raise HTTPException(status_code=404, detail="Field not found")
    return db_field

@fields_router.put("/{field_id}", response_model=EMRTypeFieldResponse)
def update_field(
    field_id: UUID, 
    field: EMRTypeFieldUpdate, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Update EMR type field"""
    db_field = update_emr_type_field(db, field_id, name=field.name, type=field.type)
    if not db_field:
        raise HTTPException(status_code=404, detail="Field not found")
    return db_field

@fields_router.delete("/{field_id}")
def delete_field(
    field_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Delete EMR type field"""
    success = delete_emr_type_field(db, field_id)
    if not success:
        raise HTTPException(status_code=404, detail="Field not found")
    return {"message": "Field deleted successfully"} 