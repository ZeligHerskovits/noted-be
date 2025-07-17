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
os.environ['SSL_CERT_FILE'] = certifi.where()

from ..db import get_db
from ..schemas import EmrTypeCreate, EmrTypeUpdate, EmrTypeResponse, EmrTypeFile
from ..crud import (
    create_emr_type, get_emr_type, get_all_emr_types, 
    update_emr_type, delete_emr_type
)

router = APIRouter(prefix="/emr-types", tags=["EMR Types"])

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
    verify=False
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

def upload_file_to_s3(file_content, filename, content_type=None):
    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)
    s3.put_object(Bucket=S3_BUCKET, Key=filename, Body=file_content, ContentType=content_type or 'application/octet-stream')
    region = os.getenv("AWS_REGION")
    url = f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/{filename}"
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
    signed_files = []
    for f in files:
        # Extract the S3 key from the URL stored in DB
        # Assumes URL is in the form https://{bucket}.s3.amazonaws.com/{key}
        url = f.get('url')
        if url and url.startswith(f"https://{S3_BUCKET}.s3.amazonaws.com/"):
            key = url[len(f"https://{S3_BUCKET}.s3.amazonaws.com/"):]
            signed_url = generate_presigned_url(S3_BUCKET, key)
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
    db: Session = Depends(get_db)
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
def get_all_emr_types_endpoint(db: Session = Depends(get_db)):
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

@router.get("/{emr_type_id}", response_model=EmrTypeResponse)
def get_emr_type_endpoint(emr_type_id: UUID, db: Session = Depends(get_db)):
    """Get a specific EMR type by ID"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        # Patch: update file URLs to signed URLs
        if hasattr(emr_type, 'files'):
            emr_type.files = with_signed_urls(emr_type.files)
        return emr_type
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching EMR type: {str(e)}")

@router.put("/{emr_type_id}", response_model=EmrTypeResponse)
async def update_emr_type_with_files(
    emr_type_id: UUID,
    name: Optional[str] = Form(None),
    session_type: Optional[str] = Form(None),
    documentation_methods: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    instructions: Optional[str] = Form(None),
    clear_files: Optional[bool] = Form(False),
    db: Session = Depends(get_db)
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
def delete_emr_type_endpoint(emr_type_id: UUID, db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
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
def get_emr_type_files(emr_type_id: UUID, db: Session = Depends(get_db)):
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
def remove_file_from_emr_type(emr_type_id: UUID, file_index: int, db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
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
def remove_all_files_from_emr_type(emr_type_id: UUID, db: Session = Depends(get_db)):
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