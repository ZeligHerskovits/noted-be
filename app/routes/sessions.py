from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Session as SessionModel
from typing import List, Optional
from app.schemas import SessionCreate, SessionUpdate, SessionResponse
import logging
from app.routes.auth import get_current_user_with_role, get_current_user_with_role_id
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
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("GET /api/v1/sessions/{} called", session_id)
    try:

        clients = get_all_clients(db)

        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
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
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    try:
        debug("GET /api/v1/sessions called with emr_type_id: {}, client_id: {}", emr_type_id, client_id)
        
        clients = get_all_clients(db)

        # Step 1: Get sessions based on user role
        if current_user.role_id == 3:  # super_admin
            sessions = get_all_sessions(db)
        elif current_user.role_id == 1:  # admin - see sessions from their company
            # Get all users from the same company
            from ..models import User
            company_users = db.query(User).filter(User.company_id == current_user.company_id).all()
            company_user_ids = [user.id for user in company_users]
            sessions = []
            for user_id in company_user_ids:
                user_sessions = get_sessions_by_user(db, user_id)
                sessions.extend(user_sessions)
        else:  # standard - only their own sessions
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
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
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
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("PUT /api/v1/sessions/{} called with: {}", session_id, session)
    try:
        # First try to find session by ID
        db_session = get_session(db, session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Update the session
        session_data = session.dict(exclude_unset=True)
        updated_session = update_session(db, session_id, **session_data)
        return updated_session
    except Exception as e:
        logger.error(f"Error updating session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to update session")

@sessions_router.put("/{session_id}/feedback")
def update_session_feedback(
    session_id: UUID,
    request: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    feedback = request.get("feedback", "")
    debug("PUT /api/v1/sessions/{}/feedback called with feedback: {}", session_id, feedback)
    try:
        # First try to find session by ID
        db_session = get_session(db, session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Update the feedback field
        updated_session = update_session(db, session_id, feedback=feedback)
        if not updated_session:
            raise HTTPException(status_code=500, detail="Failed to update feedback")
        
        return {"detail": "Feedback updated successfully", "feedback": feedback}
    except Exception as e:
        logger.error(f"Error updating session feedback: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to update feedback")

@sessions_router.delete("/{session_id}", response_model=dict)
def delete_session_by_id(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("DELETE /api/v1/sessions/{} called", session_id)
    try:
        # First try to find session by ID
        db_session = get_session(db, session_id)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
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
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("POST /api/v1/sessions/{}/generate called", session_id)
    try:
        # Get the session
        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get client history from the session's client
        from ..models import Client
        client = db.query(Client).filter(Client.id == session.client_id).first()
        client_history = client.history if client and client.history else ""

        #Get Type Writing from user
        type_writing = current_user.type_writing if hasattr(current_user, 'type_writing') and current_user.type_writing else "detailed"

        # Get instructions from user
        user_session_instructions = current_user.session_instructions if hasattr(current_user, 'session_instructions') and current_user.session_instructions else ""

        # Get instructions from that session
        manual_instructions = session.manual_instructions if session.manual_instructions else ""
        
        # Get emr_type to access session_instructions
        from ..models import EmrType, UserEMRDocumentationPair
        emr_type = db.query(EmrType).filter(EmrType.id == session.emr_type_id).first()
        default_duc_id = emr_type.documentation_method_id if emr_type else None

        # Check if user has customized documentation method for this EMR type
        user_emr_pair = db.query(UserEMRDocumentationPair).filter(
            UserEMRDocumentationPair.user_id == current_user.id,
            UserEMRDocumentationPair.emr_type_id == session.emr_type_id
        ).first()
        
        if user_emr_pair:
            # User has customized this EMR type - use their chosen documentation method
            duc_id = user_emr_pair.documentation_method_id
            # Find ANY EMR type that uses this documentation method to get the instructions
            emr_type_with_duc = db.query(EmrType).filter(EmrType.documentation_method_id == duc_id).first()
            if emr_type_with_duc:
                methods_instructions = emr_type_with_duc.methods_instructions if emr_type_with_duc.methods_instructions else ""
                progress_instructions = emr_type_with_duc.progress_towards_goal_instructions if emr_type_with_duc.progress_towards_goal_instructions else ""
                recommended_changes_instructions = emr_type_with_duc.recommended_changes_instructions if emr_type_with_duc.recommended_changes_instructions else ""
            else:
                # Fallback to original EMR type if no EMR type found with this duc
                duc_id = default_duc_id
                methods_instructions = emr_type.methods_instructions if emr_type and emr_type.methods_instructions else ""
                progress_instructions = emr_type.progress_towards_goal_instructions if emr_type and emr_type.progress_towards_goal_instructions else ""
                recommended_changes_instructions = emr_type.recommended_changes_instructions if emr_type and emr_type.recommended_changes_instructions else ""
        else:
            # User hasn't customized this EMR type - use default documentation method
            duc_id = default_duc_id
            methods_instructions = emr_type.methods_instructions if emr_type and emr_type.methods_instructions else ""
            progress_instructions = emr_type.progress_towards_goal_instructions if emr_type and emr_type.progress_towards_goal_instructions else ""
            recommended_changes_instructions = emr_type.recommended_changes_instructions if emr_type and emr_type.recommended_changes_instructions else ""
        
        # Build combined instructions
        combined_instructions = []
        
         # Add client history
        if client_history:
            combined_instructions.append(f"The Clients history is: {client_history}")

        # Add type of writing first
        if type_writing:
            combined_instructions.append(f"Type of writing: {type_writing}")

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
        if session.feedback and session.feedback.strip():
            # If feedback exists, include it in the prompt
            prompt = f"""
{ai_instructions}

Session Data:
{json.dumps(session_data, indent=2)}

This is the response you gave me based on my instructions above:
{json.dumps({
    "methods": session.methods_response or "No previous response",
    "progress_towards_goal": session.progress_towards_goal_response or "No previous response", 
    "recommended_changes": session.recommended_changes_response or "No previous response"
}, indent=2)}

This is my feedback on your response: "{session.feedback}"

Please provide a comprehensive analysis based on the instructions above, taking into account my feedback on your previous response.
"""
        else:
            # Normal prompt without feedback
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