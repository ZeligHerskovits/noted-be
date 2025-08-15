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
from ..crud import create_session, get_session, get_sessions_by_user, get_all_sessions, get_sessions_by_emr_type, get_sessions_by_client, update_session, delete_session

sessions_router = APIRouter(prefix="/sessions", tags=["Sessions"])

logger = logging.getLogger("sessions")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@sessions_router.get("/{session_id}", response_model=SessionResponse)
def get_session_by_id(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print(f"GET /api/v1/sessions/{session_id} called")
    try:
        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to view this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to view this session")
        
        return session
    except Exception as e:
        logger.error(f"Error fetching session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch session")

@sessions_router.get("", response_model=List[SessionResponse])
def list_sessions(
    emr_type_id: Optional[UUID] = None,
    client_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    try:
        print(f"GET /api/v1/sessions called with emr_type_id: {emr_type_id}, client_id: {client_id}")
        
        # Step 1: Get sessions based on user role
        if current_user.role_id == 3:  # super_admin
            sessions = get_all_sessions(db)
        else:  # admin or standard
            sessions = get_sessions_by_user(db, current_user.id)
        
        # Step 2: Apply filters to the sessions
        if emr_type_id:
            sessions = [s for s in sessions if s.emr_type_id == emr_type_id]
        elif client_id:
            sessions = [s for s in sessions if s.client_id == client_id]
        
        return sessions
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
    print(f"POST /api/v1/sessions called with: {session}")
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
    print(f"PUT /api/v1/sessions/{session_id} called with: {session}")
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
    print(f"DELETE /api/v1/sessions/{session_id} called")
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

@sessions_router.post("/{session_id}/generate", response_model=dict)
def generate_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print(f"POST /api/v1/sessions/{session_id}/generate called")
    try:
        # Get the session
        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if user has permission to access this session
        # if current_user.role_id != 3:  # Not super_admin
        #     if session.user_id != current_user.id:
        #         raise HTTPException(status_code=403, detail="Not authorized to access this session")
        
        # Get instructions from session
        manual_instructions = session.manual_instructions if session.manual_instructions else ""
        
        # Get instructions from user
        session_instructions = current_user.session_instructions if hasattr(current_user, 'session_instructions') and current_user.session_instructions else ""
        
        # Build combined instructions
        combined_instructions = []
        
        # Add user instructions first (highest priority)
        if session_instructions:
            combined_instructions.append(f"session_instructions: {session_instructions}")
        
        # Add session instructions second
        if manual_instructions:
            combined_instructions.append(f"manual_instructions: {manual_instructions}")
        
        # Add my static instructions last
        static_instructions = """
        Analyze the provided session data and provide the following:

        1. **Session Summary**: Create a brief summary of the session including client name, date, duration, and key details
        2. **Service Analysis**: Analyze the service provided, staff involved, and program details
        3. **Location Assessment**: Review the session location and delivery method
        4. **No-Show Analysis**: If this was a no-show, provide insights and recommendations
        5. **Recommendations**: Provide 3-5 actionable recommendations based on the session data
        6. **Risk Assessment**: Identify any potential issues or concerns
        7. **Follow-up Actions**: Suggest appropriate follow-up actions

        Format your response as a structured analysis with clear sections.
        """
        combined_instructions.append(f"Analysis Instructions: {static_instructions}")
        
        # Combine all instructions
        ai_instructions = "\n\n".join(combined_instructions)
        
        # Prepare session data for OpenAI (excluding static/manual instructions)
        session_data = {
            "session_id": str(session.id),
            "client_id": str(session.client_id),
            "emr_type_id": str(session.emr_type_id),
            "emr_name": session.emr_name,
            "client": session.client,
            "appt_date": str(session.appt_date) if session.appt_date else None,
            "duration": session.duration,
            "is_no_show": session.is_no_show,
            "no_show_action": session.no_show_action,
            "staff_providing_service": session.staff_providing_service,
            "program_name": session.program_name,
            "location_where_session_took_place": session.location_where_session_took_place,
            "service_facility_address": session.service_facility_address,
            "delivered_off_site": session.delivered_off_site
        }
        
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
            
            # Save AI response to database
            session.session_response = ai_content
            db.commit()
            
            return {
                "ai_response": ai_content,
            }
            
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise HTTPException(status_code=500, detail="Failed to get response from OpenAI")
        
    except Exception as e:
        logger.error(f"Error generating session: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to generate session") 