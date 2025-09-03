from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Session as SessionModel
from typing import List, Optional
from app.schemas import SessionCreate, SessionUpdate, SessionResponse
import logging
from app.routes.auth import get_current_user_with_role
from datetime import datetime
from uuid import UUID
import traceback
import json
import requests
import os
from openai import OpenAI
from ..crud import create_session, get_session, get_sessions_by_user, get_all_sessions, get_sessions_by_emr_type, get_sessions_by_client, update_session, delete_session, get_all_clients
from ..debug import debug

sessions_router = APIRouter(prefix="/sessions", tags=["Sessions"])

logger = logging.getLogger("sessions")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@sessions_router.get("/{session_id}")
def get_session_by_id(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    debug("GET /api/v1/sessions/{} called", session_id)
    try:

        clients = get_all_clients(db)

        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to view this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to view this session")
        
        # Add client name to the single session
        client = next((c for c in clients if c.id == session.client_id), None)
        if client:
            session.client_id_name = f"{client.first_name} {client.last_name}"

        # Convert session object to dict to include all dynamic fields
        session_dict = {}
        for attr in dir(session):
            if not attr.startswith('_') and not callable(getattr(session, attr)):
                value = getattr(session, attr)
                # Handle UUID objects
                if hasattr(value, '__str__'):
                    session_dict[attr] = str(value)
                else:
                    session_dict[attr] = value
        
        return session_dict
    except Exception as e:
        logger.error(f"Error fetching session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch session")

@sessions_router.get("")
def list_sessions(
    emr_type_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    try:
        debug("GET /api/v1/sessions called with emr_type_id: {}, client_id: {}", emr_type_id, client_id)
        
        clients = get_all_clients(db)

        # Step 1: Get sessions based on user role
        if current_user.role_id == 3:  # super_admin
            sessions = get_all_sessions(db)
        else:  # admin or standard
            sessions = get_sessions_by_user(db, current_user.id)
        
        # Step 2: Apply filters to the sessions, as of Augest 20 we not using that Step 2 from frontend
        if emr_type_id:
            sessions = [s for s in sessions if s.emr_type_id == emr_type_id]
        elif client_id:
            sessions = [s for s in sessions if s.client_id == client_id]
        
        # Step 3: Add client name to each session while keeping original client_id
        for session in sessions:
            client = next((c for c in clients if c.id == session.client_id), None)
            if client:
                session.client_id_name = f"{client.first_name} {client.last_name}"

        # Convert session objects to dicts to include all dynamic fields
        sessions_list = []
        for session in sessions:
            session_dict = {}
            for attr in dir(session):
                if not attr.startswith('_') and not callable(getattr(session, attr)):
                    value = getattr(session, attr)
                    # Handle UUID objects
                    if hasattr(value, '__str__'):
                        session_dict[attr] = str(value)
                    else:
                        session_dict[attr] = value 

            sessions_list.append(session_dict)

        return sessions_list
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch sessions")

@sessions_router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_new_session(
    session: SessionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    debug("POST /api/v1/sessions called with: {}", session)
    try:
        # user_id will be automatically filled from current_user.id
        session_data = session.dict()
        new_session = create_session(db, user_id=current_user.id, **session_data)
        return new_session
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create session")

@sessions_router.put("/{session_id}", response_model=SessionResponse)
def update_session_by_id(
    session_id: UUID,
    session: SessionUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    debug("PUT /api/v1/sessions/{} called with: {}", session_id, session)
    try:
        # First try to find session by ID
        db_session = get_session(db, session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to update this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if db_session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to update this session")
        
        # Update the session
        session_data = session.dict(exclude_unset=True)
        updated_session = update_session(db, session_id, **session_data)
        return updated_session
    except Exception as e:
        logger.error(f"Error updating session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to update session")

@sessions_router.delete("/{session_id}", response_model=dict)
def delete_session_by_id(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    debug("DELETE /api/v1/sessions/{} called", session_id)
    try:
        # First try to find session by ID
        db_session = get_session(db, session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to delete this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if db_session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to delete this session")
        
        success = delete_session(db, session_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete session")
        
        return {"detail": "Session deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to delete session")

# Generate sessions button is calling that api endpoint
@sessions_router.post("/{session_id}/generate", response_model=dict)
def generate_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    debug("POST /api/v1/sessions/{}/generate called", session_id)
    try:
        # Get the session
        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to access this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to access this session")
        
        # Get instructions from user
        user_session_instructions = current_user.session_instructions if hasattr(current_user, 'session_instructions') and current_user.session_instructions else ""

        # Get instructions from that session
        manual_instructions = session.manual_instructions if session.manual_instructions else ""
        
        # Get emr_type to access session_instructions
        from ..models import EmrType
        emr_type = db.query(EmrType).filter(EmrType.id == session.emr_type_id).first()
        
        # Get the 3 separate instruction fields from EMR type
        methods_instructions = emr_type.methods_instructions if emr_type and emr_type.methods_instructions else ""
        progress_instructions = emr_type.progress_towards_goal_instructions if emr_type and emr_type.progress_towards_goal_instructions else ""
        recommended_changes_instructions = emr_type.recommended_changes_instructions if emr_type and emr_type.recommended_changes_instructions else ""
        
        # Build combined instructions
        combined_instructions = []
        
        # Add user instructions first (highest priority)
        if user_session_instructions:
            combined_instructions.append(f"user_session_instructions: {user_session_instructions}")
        
        # Add session instructions second
        if manual_instructions:
            combined_instructions.append(f"manual_instructions: {manual_instructions}")
        
        # Add EMR type instructions (the 3 separate fields)
        if methods_instructions:
            combined_instructions.append(f"methods_instructions: {methods_instructions}")
        if progress_instructions:
            combined_instructions.append(f"progress_towards_goal_instructions: {progress_instructions}")
        if recommended_changes_instructions:
            combined_instructions.append(f"recommended_changes_instructions: {recommended_changes_instructions}")

        # Combine all instructions
        ai_instructions = "\n\n".join(combined_instructions)
        
        # Prepare session data for OpenAI (all fields from session)
        session_data = {}
        for attr in dir(session):
           if not attr.startswith('_') and not callable(getattr(session, attr)):
               value = getattr(session, attr)
               # Skip UUID fields
               if isinstance(value, UUID):
                   continue
               # Convert dates to strings for JSON serialization
               if hasattr(value, '__str__') and not isinstance(value, (str, int, float, bool, type(None))):
                  session_data[attr] = str(value)
               else:
                  session_data[attr] = value
        
        # Prepare prompt for OpenAI
        prompt = f"""
{ai_instructions}

Session Data:
{json.dumps(session_data, indent=2)}

Please provide a comprehensive analysis based on the instructions above.
"""
        
        # Call OpenAI API using the client
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        try:
            client = OpenAI(api_key=openai_api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            ai_content = response.choices[0].message.content
            
            # Parse AI response to extract the 3 sections
            methods = ""
            progress_towards_goal = ""
            recommended_changes = ""

            # Split the response by sections
            if "Section 1:" in ai_content:
                # Extract Methods section
                methods_start = ai_content.find("Section 1:")
                methods_end = ai_content.find("Section 2:") if "Section 2:" in ai_content else len(ai_content)
                methods = ai_content[methods_start:methods_end].strip()

            if "Section 2:" in ai_content:
                # Extract Progress towards goal section
                progress_start = ai_content.find("Section 2:")
                progress_end = ai_content.find("Section 3:") if "Section 3:" in ai_content else len(ai_content)
                progress_towards_goal = ai_content[progress_start:progress_end].strip()

            if "Section 3:" in ai_content:
                # Extract Recommended changes section
                changes_start = ai_content.find("Section 3:")
                recommended_changes = ai_content[changes_start:].strip()

            # Save AI response and parsed sections to database
            # Debug: Print what we're trying to save
            debug("DEBUG: methods = '{}'", methods)
            debug("DEBUG: progress_towards_goal = '{}'", progress_towards_goal)
            debug("DEBUG: recommended_changes = '{}'", recommended_changes)
            
            update_data = {
                'methods_response': methods,
                'progress_towards_goal_response': progress_towards_goal,
                'recommended_changes_response': recommended_changes
            }
            
            debug("DEBUG: About to update session with data: {}", update_data)
            updated_session = update_session(db, session_id, **update_data)
            
            if updated_session:
                debug("DEBUG: Session updated successfully")
            else:
                debug("DEBUG: Failed to update session")

            return {
                "methods": methods,
                "progress_towards_goal": progress_towards_goal,
                "recommended_changes": recommended_changes
            }
            
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise HTTPException(status_code=500, detail="Failed to get response from OpenAI")
        
    except Exception as e:
        logger.error(f"Error generating session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to generate session") 