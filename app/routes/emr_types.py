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
import logging
from datetime import datetime
from pydantic import BaseModel

from app.routes.ai import SaveSessionInstructionsRequest
os.environ['SSL_CERT_FILE'] = certifi.where()

from ..db import get_db
from ..routes.auth import get_current_user_with_role, get_current_user_with_role_id, send_email_via_msmtp
from ..schemas import (
    EmrTypeCreate, EmrTypeUpdate, EmrTypeResponse, EmrTypeFile,
    EMRTypeFieldCreate, EMRTypeFieldUpdate, EMRTypeFieldResponse,
    EMRTypeResultCreate, EMRTypeResultResponse, EmrTypeResponseOnly,
    UpdateResultInstructionsRequest, EMRTypeResultInstructionsOnly,
    UpdateResultStatusRequest, ManualFieldCreate, ManualFieldUpdate, ManualFieldResponse
)
from ..crud import (
    create_emr_type, get_emr_type, get_all_emr_types, 
    update_emr_type, delete_emr_type,
    create_emr_type_result, get_emr_type_results_by_emr_type, get_all_emr_type_results, delete_all_emr_type_results_by_emr_type,
    create_emr_type_field, get_emr_type_field, get_all_emr_type_fields, update_emr_type_field, delete_emr_type_field,
    _create_field_mapping, _create_field_type_mapping,
    create_manual_field, get_manual_field, get_all_manual_fields, get_manual_fields_by_emr_type, update_manual_field, delete_manual_field
)
from ..models import EMRTypeField, User, Company, UserEMRDocumentationPair
from ..debug import debug

router = APIRouter(prefix="/emr-types", tags=["EMR Types"])
fields_router = APIRouter(prefix="/emr-types-fields", tags=["EMR Type Fields"])
manual_fields_router = APIRouter(prefix="/manual-fields", tags=["Manual Fields"])
results_router = APIRouter(prefix="/results", tags=["EMR Type Results"])

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

# Create a new EMR type
@router.post("/", response_model=EmrTypeResponse)
async def create_emr_type_with_files(
    name: str = Form(...),
    session_type: Optional[str] = Form(None),
    documentation_method_id: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    emr_url: Optional[str] = Form(None),
    created_from_chrome: Optional[str] = Form("false"),  # String "true"/"false" from FormData
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_role_id([1,2,3]))  
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
  
    # Convert documentation_method_id to UUID and validate it exists
    if not documentation_method_id or documentation_method_id.strip() == "":
        raise HTTPException(status_code=400, detail="Documentation method is required")
    
    try:
        doc_method_uuid = UUID(documentation_method_id)
        # Validate that the documentation method exists
        from ..crud import get_documentation_method
        if not get_documentation_method(db, doc_method_uuid):
            raise HTTPException(status_code=400, detail="Documentation method not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid documentation_method_id format")
    
    # Convert created_from_chrome string to boolean
    created_from_chrome_bool = created_from_chrome.lower() == "true"
    
    # Get user_id from current_user
    user_id = current_user.id
    
    emr_type = create_emr_type(
        db=db,
        name=name,
        session_type=session_type,
        documentation_method_id=doc_method_uuid,
        files=files_data,
        emr_url=emr_url,
        created_from_chrome=created_from_chrome_bool,
        user_id=user_id
    )
    
    # Send email notifications if created from Chrome
    if created_from_chrome_bool:
        # 1) Confirmation email to the user who created the EMR type
        subject = "EMR Request Received - Pending Review"
        body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2 style="color: #3b82f6;">Thank You for Your EMR Request</h2>
              <p>Hello {current_user.full_name or 'there'},</p>
              <p>We have successfully received your Electronic Medical Record (EMR) request. Your request is currently <strong>pending review</strong> by our team.</p>
              <p>We will carefully review your submission and notify you via email once it has been approved. You can expect to hear from us soon.</p>
              <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
              <p style="margin-top: 30px;">Best regards,<br><strong>The Noted Team</strong></p>
            </div>
          </body>
        </html>
        """
        try:
            send_email_via_msmtp(current_user.email, subject, body)
        except Exception as e:
            # Log error but don't fail the request if email fails
            import logging
            logging.error(f"Failed to send EMR request confirmation email: {e}")

        # 2) Notification email to all super admins (role_id == 3)
        try:
            super_admins = db.query(User).filter(User.role_id == 3, User.is_active == True).all()
            if super_admins:
                admin_subject = "New EMR Type Created from Chrome - Awaiting Analysis"
                emr_name = emr_type.name
                creator_name = current_user.full_name or current_user.email
                created_at_str = emr_type.created_at.strftime("%Y-%m-%d %H:%M")
                admin_body = f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                      <h2 style="color: #3b82f6;">New EMR Type Waiting for Analysis</h2>
                      <p>Hello,</p>
                      <p>A new EMR type has been created from the Chrome extension and is waiting to be analyzed.</p>
                      <ul>
                        <li><strong>EMR Name:</strong> {emr_name}</li>
                        <li><strong>Session Type:</strong> {session_type or 'N/A'}</li>
                        <li><strong>Created By:</strong> {creator_name}</li>
                        <li><strong>Created At:</strong> {created_at_str}</li>
                      </ul>
                      <p>You can review and analyze this EMR type in the Noted admin panel.</p>
                      <p style="margin-top: 30px;">Best regards,<br><strong>The Noted System</strong></p>
                    </div>
                  </body>
                </html>
                """
                for admin in super_admins:
                    if admin.email:
                        try:
                            send_email_via_msmtp(admin.email, admin_subject, admin_body)
                        except Exception as e:
                            import logging
                            logging.error(f"Failed to send EMR creation notification to admin {admin.email}: {e}")
        except Exception as e:
            import logging
            logging.error(f"Failed to prepare EMR creation notifications for super admins: {e}")

    return emr_type
import html
import re
#Saving changed session instructions is calling this endpoint
@router.put("/save-session-instructions/")
def save_session_instructions(
    req: SaveSessionInstructionsRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Save a session_instructions to the EMR type"""
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    if req.methods_instructions and req.progress_towards_goal_instructions and req.recommended_changes_instructions:
        # Use the provided individual fields and clean them
        methods_instructions = re.sub(r'\s+', ' ', html.unescape(req.methods_instructions)).strip()
        progress_towards_goal_instructions = re.sub(r'\s+', ' ', html.unescape(req.progress_towards_goal_instructions)).strip()
        recommended_changes_instructions = re.sub(r'\s+', ' ', html.unescape(req.recommended_changes_instructions)).strip()
    else:
       # Its will prob never go into this cause even one section box is empty has it a header which is get ssend to be along with that section box which means thta a section box will never be empty
       raise HTTPException(status_code=400, detail="All 3 sections must be filled out")

    # Update the EMR type with all fields
    update_emr_type(
        db, 
        emr_type_id, 
        methods_instructions=methods_instructions,
        progress_towards_goal_instructions=progress_towards_goal_instructions,
        recommended_changes_instructions=recommended_changes_instructions
    )


    return {"message": "session_instructions saved successfully", "emr_type_id": emr_type_id}

# Get all EMR types
@router.get("/", response_model=List[EmrTypeResponse])
def get_all_emr_types_endpoint(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
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

# Get a specific EMR type by ID
@router.get("/{emr_type_id}")
def get_emr_type_endpoint(
    emr_type_id: UUID, 
    response_only: bool = False, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get a specific EMR type by ID"""
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")
        
        # If response_only is requested, return only the response
        if response_only:
            return EmrTypeResponseOnly(json_response=emr_type.json_response)
        
        # Patch: update file URLs to signed URLs
        if hasattr(emr_type, 'files'):
            emr_type.files = with_signed_urls(emr_type.files)
        return EmrTypeResponse.from_orm(emr_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching EMR type: {str(e)}")

# EMR Type Results, its the data you see under Analysis Results - GET endpoint for frontend display
@router.get("/{emr_type_id}/results")
def get_emr_type_results(
    emr_type_id: UUID, 
    instructions_only: bool = False, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get all results for a specific EMR type (for frontend display)"""
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    
    if instructions_only:
        # Return only key value and instructions
        return [EMRTypeResultInstructionsOnly(key=result.key, value=result.value, instructions=result.instructions) for result in results]
    
    return [EMRTypeResultResponse.from_orm(result) for result in results]

# EMR Type Results, its the data you see under Analysis Results - Update instructions endpoint (MUST BE BEFORE GENERAL PUT)
@router.put("/{emr_type_id}/instructions")
def update_result_instructions(
    emr_type_id: UUID,
    request: UpdateResultInstructionsRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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
    debug("=== DEBUG: Updated EMR type status to 'draft' after instruction change ===")
    
    return {
        "message": "Instructions updated successfully"
    }

# EMR Type Results, its the data you see under Analysis Results - Update status endpoint
@router.put("/{emr_type_id}/status")
def update_result_status(
    emr_type_id: UUID,
    request: UpdateResultStatusRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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
    
    debug("=== DEBUG: Updated status for {} to {} ===", request.key, result.status)
    
    return {
        "message": "Status updated successfully",
        "key": request.key,
        "value": request.value,
        "status": result.status
    }

# This get called when clicking the back < in the EMR Type Details
@router.put("/{emr_type_id}/back-action")
def back_action_emr_type(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """
    Restore the previous status when going back from processing.
    If no previous status is stored, determine based on results.
    """
    # Get the EMR type
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Check if there are any results for this EMR type
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    
    # Determine new status based on previous_status or results
    if emr_type.previous_status:
        # Restore the previous status
        new_status = emr_type.previous_status
    elif results:
        # If no previous status but results exist, set to analyzed
        new_status = "analyzed"
    else:
        # If no previous status and no results, set to draft
        new_status = "draft"
    
    # Get the current total_chunks value to reset processed_chunks
    total_chunks = emr_type.total_chunks or 0
    
    # Update the EMR type status and reset processed_chunks to match total_chunks
    update_emr_type(
        db=db,
        emr_type_id=emr_type_id,
        status=new_status,
        processed_chunks=total_chunks
    )
    
    # Force refresh from database to ensure changes are committed
    db.commit()
    
    # Verify the update worked by fetching fresh data
    updated_emr = get_emr_type(db, emr_type_id)
    debug("=== DEBUG: Back action - Status: {}, Total chunks: {}, Processed chunks: {} ===", updated_emr.status, updated_emr.total_chunks, updated_emr.processed_chunks)
    
    return {
        "message": f"EMR type status restored to '{new_status}' and processed_chunks reset to {total_chunks}",
        "debug_info": {
            "status": updated_emr.status,
            "total_chunks": updated_emr.total_chunks,
            "processed_chunks": updated_emr.processed_chunks,
            "chunks_equal": updated_emr.total_chunks == updated_emr.processed_chunks
        }
    }

# Update a EMR type
@router.put("/{emr_type_id}", response_model=EmrTypeResponse)
async def update_emr_type_with_files(
    emr_type_id: UUID,
    name: Optional[str] = Form(None),
    session_type: Optional[str] = Form(None),
    documentation_method_id: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    clear_files: Optional[bool] = Form(False),
    emr_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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
    if not documentation_method_id or documentation_method_id.strip() == "":
        raise HTTPException(status_code=400, detail="Documentation method is required")
    
    try:
        doc_method_uuid = UUID(documentation_method_id)
        # Validate that the documentation method exists
        from ..crud import get_documentation_method
        if not get_documentation_method(db, doc_method_uuid):
            raise HTTPException(status_code=400, detail="Documentation method not found")
        update_data['documentation_method_id'] = doc_method_uuid
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid documentation_method_id format")
    if emr_url is not None:
        update_data['emr_url'] = emr_url

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

# Delete an EMR type
@router.delete("/{emr_type_id}")
def delete_emr_type_endpoint(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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

#------------------------------------------------------------------------------------------------------

# # This is not getting called as of Augest 20 from frontend
# @router.post("/{emr_type_id}/upload-files")
# def upload_files_to_emr_type(
#     emr_type_id: UUID,
#     files: List[UploadFile] = File(...),
#     db: Session = Depends(get_db),
#     _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
# ):
#     """Upload files to an existing EMR type"""
#     try:
#         emr_type = get_emr_type(db, emr_type_id)
#         if not emr_type:
#             raise HTTPException(status_code=404, detail="EMR type not found")
        
#         # Read existing files or initialize empty list
#         existing_files = emr_type.files or []
        
#         # Process uploaded files
#         for file in files:
#             file_content = file.file.read()
#             content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
#             file_url = upload_file_to_s3(file_content, file.filename, content_type)
#             file_data = {
#                 "name": file.filename,
#                 "url": file_url,
#                 "type": content_type,
#                 "size": len(file_content)
#             }
#             existing_files.append(file_data)
        
#         # Update the EMR type with new files
#         updated_emr_type = update_emr_type(
#             db=db,
#             emr_type_id=emr_type_id,
#             files=existing_files
#         )
        
#         return {"message": f"Successfully uploaded {len(files)} files", "emr_type": updated_emr_type}
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error uploading files: {str(e)}")

# # This is not getting called as of Augest 20 from frontend
# @router.get("/{emr_type_id}/files")
# def get_emr_type_files(
#     emr_type_id: UUID, 
#     db: Session = Depends(get_db),
#     _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
# ):
#     """Get all files for a specific EMR type"""
#     try:
#         emr_type = get_emr_type(db, emr_type_id)
#         if not emr_type:
#             raise HTTPException(status_code=404, detail="EMR type not found")
#         # Patch: update file URLs to signed URLs
#         return {"files": with_signed_urls(emr_type.files or [])}
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error fetching files: {str(e)}")

# # This is not getting called as of Augest 20 from frontend
# @router.delete("/{emr_type_id}/files/{file_index}")
# def remove_file_from_emr_type(
#     emr_type_id: UUID, 
#     file_index: int, 
#     db: Session = Depends(get_db),
#     _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
# ):
#     """Remove a specific file from an EMR type by index"""
#     try:
#         emr_type = get_emr_type(db, emr_type_id)
#         if not emr_type:
#             raise HTTPException(status_code=404, detail="EMR type not found")
        
#         existing_files = emr_type.files or []
        
#         if file_index < 0 or file_index >= len(existing_files):
#             raise HTTPException(status_code=400, detail="Invalid file index")
        
#         # Remove the file at the specified index
#         removed_file = existing_files.pop(file_index)
        
#         # Update the EMR type with the modified files list
#         updated_emr_type = update_emr_type(
#             db=db,
#             emr_type_id=emr_type_id,
#             files=existing_files
#         )
        
#         return {
#             "message": f"Successfully removed file: {removed_file['name']}",
#             "removed_file": removed_file,
#             "remaining_files_count": len(existing_files)
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error removing file: {str(e)}")

# # This is not getting called as of Augest 20 from frontend
# @router.put("/{emr_type_id}/files")
# def replace_all_files_in_emr_type(
#     emr_type_id: UUID,
#     files: List[EmrTypeFile],
#     db: Session = Depends(get_db),
#     _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
# ):
#     """Replace all files in an EMR type with new files"""
#     try:
#         emr_type = get_emr_type(db, emr_type_id)
#         if not emr_type:
#             raise HTTPException(status_code=404, detail="EMR type not found")
        
#         # Convert files to the format expected by the database
#         files_data = [file.dict() for file in files]
        
#         # Update the EMR type with new files (replaces all existing files)
#         updated_emr_type = update_emr_type(
#             db=db,
#             emr_type_id=emr_type_id,
#             files=files_data
#         )
        
#         return {
#             "message": f"Successfully replaced all files. New file count: {len(files_data)}",
#             "emr_type": updated_emr_type
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error replacing files: {str(e)}")

# # This is not getting called as of Augest 20 from frontend
# @router.delete("/{emr_type_id}/files")
# def remove_all_files_from_emr_type(
#     emr_type_id: UUID, 
#     db: Session = Depends(get_db),
#     _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
# ):
#     """Remove all files from an EMR type"""
#     try:
#         emr_type = get_emr_type(db, emr_type_id)
#         if not emr_type:
#             raise HTTPException(status_code=404, detail="EMR type not found")
        
#         # Update the EMR type with empty files list
#         updated_emr_type = update_emr_type(
#             db=db,
#             emr_type_id=emr_type_id,
#             files=[]
#         )
        
#         return {
#             "message": "Successfully removed all files from EMR type",
#             "emr_type": updated_emr_type
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error removing all files: {str(e)}")

#------------------------------------------------------------------------------------------------------

# Finalize an EMR type
@router.put("/{emr_type_id}/finalize")
def finalize_emr_type(
    emr_type_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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
    
    # If EMR was created from Chrome, create pair and update company
    if emr_type.created_from_chrome and emr_type.user_id:
        try:
            user = db.query(User).filter(User.id == emr_type.user_id).first()
            if user:
                # Create pair
                if emr_type.documentation_method_id:
                    existing = db.query(UserEMRDocumentationPair).filter(
                        UserEMRDocumentationPair.user_id == user.id,
                        UserEMRDocumentationPair.emr_type_id == emr_type_id,
                        UserEMRDocumentationPair.documentation_method_id == emr_type.documentation_method_id
                    ).first()
                    if not existing:
                        db.add(UserEMRDocumentationPair(
                            user_id=user.id,
                            emr_type_id=emr_type_id,
                            documentation_method_id=emr_type.documentation_method_id
                        ))
                        db.commit()
                from sqlalchemy.orm.attributes import flag_modified
                # Update company
                if user.company_id:
                    company = db.query(Company).filter(Company.id == user.company_id).first()
                    if company:
                        emr_arr = company.emr or []
                        if emr_type.name not in emr_arr:
                            emr_arr.append(emr_type.name)
                            company.emr = emr_arr
                            # 👇 tell SQLAlchemy that the JSONB field changed
                            flag_modified(company, "emr")

                            db.commit()
                            db.refresh(company)
                
                # Send email
                if user.email:
                    subject = "Your EMR Request Has Been Approved!"
                    body = f"""
            <html>
              <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                  <h2 style="color: #10b981;">Great News! Your EMR Has Been Approved</h2>
                  <p>Hello {user.full_name or 'there'},</p>
                  <p>We're excited to inform you that your Electronic Medical Record (EMR) request for <strong>{emr_type.name}</strong> has been <strong>approved and finalized</strong>!</p>
                  <p>Your EMR is now active and ready to use. You can start using it right away.</p>
                  <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
                  <p style="margin-top: 30px;">Best regards,<br><strong>The Noted Team</strong></p>
                </div>
              </body>
            </html>
            """
                    try:
                        send_email_via_msmtp(user.email, subject, body)
                    except Exception as e:
                        logging.error(f"Failed to send EMR approval email: {e}")
        except Exception as e:
            logging.error(f"Error in finalize: {e}")
    
    return {
        "message": "EMR type finalized successfully",
        "emr_type": updated_emr_type
    }


# EMR Type Fields API Endpoints
@fields_router.post("/", response_model=EMRTypeFieldResponse)
def create_field(
    field: EMRTypeFieldCreate, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new EMR type field"""
    try:
        db_field = create_emr_type_field(db, name=field.name, type=field.type, analyzable=field.analyzable, api_name=field.api_name, dropdown_values=field.dropdown_values, instructions=field.instructions)
        return db_field
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@fields_router.get("/", response_model=List[EMRTypeFieldResponse])
def get_fields(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all EMR type fields"""
    return get_all_emr_type_fields(db)

@fields_router.get("/{field_id}", response_model=EMRTypeFieldResponse)
def get_field(
    field_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
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
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update EMR type field"""
    try:
        db_field = update_emr_type_field(db, field_id, name=field.name, type=field.type, analyzable=field.analyzable, api_name=field.api_name, dropdown_values=field.dropdown_values, instructions=field.instructions)
        if not db_field:
            raise HTTPException(status_code=404, detail="Field not found")
        return db_field
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@fields_router.delete("/{field_id}")
def delete_field(
    field_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete EMR type field"""
    success = delete_emr_type_field(db, field_id)
    if not success:
        raise HTTPException(status_code=404, detail="Field not found")
    return {"message": "Field deleted successfully"}

# Manual Fields API Endpoints
@manual_fields_router.post("/", response_model=ManualFieldResponse)
def create_manual_field_endpoint(
    field: ManualFieldCreate, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Create a new manual field"""
    db_field = create_manual_field(db, name=field.name, emr_type_id=field.emr_type_id)
    return db_field

@manual_fields_router.get("/", response_model=List[ManualFieldResponse])
def get_all_manual_fields_endpoint(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all manual fields from all EMR types"""
    return get_all_manual_fields(db)

@manual_fields_router.get("/emr-type/{emr_type_id}", response_model=List[ManualFieldResponse])
def get_manual_fields_by_emr_type_endpoint(
    emr_type_id: UUID,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get all manual fields for a specific EMR type"""
    return get_manual_fields_by_emr_type(db, emr_type_id)

@manual_fields_router.put("/{field_id}", response_model=ManualFieldResponse)
def update_manual_field_endpoint(
    field_id: UUID, 
    field: ManualFieldUpdate, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Update manual field"""
    db_field = update_manual_field(db, field_id, name=field.name)
    if not db_field:
        raise HTTPException(status_code=404, detail="Manual field not found")
    return db_field

@manual_fields_router.delete("/{field_id}")
def delete_manual_field_endpoint(
    field_id: UUID, 
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete manual field"""
    success = delete_manual_field(db, field_id)
    if not success:
        raise HTTPException(status_code=404, detail="Manual field not found")
    return {"message": "Manual field deleted successfully"}

# EMR Type Results API Endpoints
@results_router.get("/")
def get_all_emr_type_results_endpoint(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    """Get all EMR type results with field type and name information"""
    # Get all results
    all_results = get_all_emr_type_results(db)
    
    # Get all EMR type fields for type and name info
    emr_fields = db.query(EMRTypeField).all()
    
    # Use existing field type mapping function to avoid duplication
    field_mapping = _create_field_type_mapping(emr_fields)
    
    # Transform results to include all original fields plus type
    enhanced_results = []
    for result in all_results:
        # Try to find matching field type
        field_type = field_mapping.get(result.key) or field_mapping.get(result.key.lower())
        
        # Create result object with all original fields
        result_obj = {
            "id": result.id,
            "emr_type_id": result.emr_type_id,
            "instructions": result.instructions,
            "key": result.key,
            "label": result.label,
            "status": result.status,
            "value": result.value
        }
        
        # Add type if found
        if field_type:
            result_obj["type"] = field_type
        else:
            result_obj["type"] = "text"  # Default type
        
        # If type is dropdown, also add dropdown_values
        if field_type and field_type.lower() == "dropdown":
            # Find the corresponding EMR type field to get dropdown_values
            # Try multiple matching strategies for better field identification
            emr_field = None
            
            # Strategy 1: Case-insensitive name match
            emr_field = next((field for field in emr_fields if field.name.lower() == result.key.lower()), None)
            
            # Strategy 2: Sanitized name match (remove spaces, special chars)
            if not emr_field:
                sanitized_key = result.key.lower().replace(' ', '').replace('-', '').replace('_', '')
                emr_field = next((field for field in emr_fields 
                                if field.name.lower().replace(' ', '').replace('-', '').replace('_', '') == sanitized_key), None)
            
            # Strategy 3: Partial name match
            if not emr_field:
                emr_field = next((field for field in emr_fields 
                                if result.key.lower() in field.name.lower() or field.name.lower() in result.key.lower()), None)
            
            if emr_field and emr_field.dropdown_values:
                result_obj["dropdown_values"] = emr_field.dropdown_values
        
        enhanced_results.append(result_obj)
    
    return enhanced_results 