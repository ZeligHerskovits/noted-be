from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import SessionLocal, get_db
from app.models import Client
from typing import List
from app.schemas import ClientCreate, ClientUpdate, ClientResponse
import logging
from app.routes.auth import get_current_user_with_role, get_current_user_with_role_id
from datetime import date
from uuid import UUID
import traceback
from ..debug import debug

router = APIRouter(prefix="/api/Clients", tags=["Clients"])

# Debug endpoint to test date serialization
@router.get("/debug-date")
def debug_date():
    """Debug endpoint to test date serialization"""
    test_date = date(2000, 1, 1)
    return {
        "original_date": test_date,
        "iso_format": test_date.isoformat(),
        "type": str(type(test_date))
    }

# Debug endpoint to check actual client data from database
@router.get("/debug-client/{client_id}")
def debug_client_data(client_id: UUID, db: Session = Depends(get_db)):
    """Debug endpoint to check actual client data from database"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "Client not found"}
    
    return {
        "client_id": str(client.id),
        "date_of_birth_raw": client.date_of_birth,
        "date_of_birth_type": str(type(client.date_of_birth)),
        "date_of_birth_iso": client.date_of_birth.isoformat() if client.date_of_birth else None,
        "created_at": client.created_at,
        "created_at_type": str(type(client.created_at))
    }

logger = logging.getLogger("Clients")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{Client_id}", response_model=ClientResponse)
def get_Client(
    Client_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("GET /api/Clients/{} called", Client_id)
    try:
        # First try to find Client by ID only
        db_Client = db.query(Client).filter(Client.id == Client_id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Check if user has permission to view this Client
        if current_user.role_id == 3:  # super_admin - can view any client
            pass  # No restrictions
        elif current_user.role_id == 1:  # admin - can view clients from their company
            # Check if the client belongs to a user from the same company
            from ..models import User
            client_user = db.query(User).filter(User.id == db_Client.user_id).first()
            if not client_user or client_user.company_id != current_user.company_id:
                raise HTTPException(status_code=403, detail="Not authorized to view this Client")
        else:  # standard - only their own clients
            if db_Client.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to view this Client")
        
        debug("Returning client with date_of_birth: {} (type: {})", db_Client.date_of_birth, type(db_Client.date_of_birth))
        return db_Client
    except Exception as e:
        logger.error(f"Error fetching Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch Client")

@router.get("", response_model=List[ClientResponse])
def list_Clients(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("GET /api/Clients called")
    try:
        if current_user.role_id == 3:  # super_admin
            Clients = db.query(Client).all()
        elif current_user.role_id == 1:  # admin - see clients from their company
            # Get all users from the same company
            from ..models import User
            company_users = db.query(User).filter(User.company_id == current_user.company_id).all()
            company_user_ids = [user.id for user in company_users]
            Clients = db.query(Client).filter(Client.user_id.in_(company_user_ids)).all()
        else:  # standard - only their own clients
            Clients = db.query(Client).filter(Client.user_id == current_user.id).all()
        return Clients
    except Exception as e:
        logger.error(f"Error fetching Clients: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch Clients")

@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_Client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role_id([1, 2, 3]))  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
):
    debug("POST /api/Clients called with: {}", client_data)
    debug("Date of birth from request: {} (type: {})", client_data.date_of_birth, type(client_data.date_of_birth))
    try:
        client_dict = client_data.dict(exclude={"user_id"})  # Remove user_id from request
        client_dict["user_id"] = current_user.id  # Assign from token/session
        debug("Client dict before creation: {}", client_dict)
        # Use date_of_birth from frontend (no hardcoding)
        new_client = Client(**client_dict)
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        debug("Client created with date_of_birth: {} (type: {})", new_client.date_of_birth, type(new_client.date_of_birth))
        return new_client
    except Exception as e:
        logger.error(f"Error creating Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create Client")

@router.put("/{Client_id}", response_model=ClientResponse)
def update_Client(Client_id: UUID, client_update: ClientUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role_id([1, 2, 3]))):  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
    debug("PUT /api/Clients/{} called with: {}", Client_id, client_update)
    try:
        # First try to find Client by ID only
        db_Client = db.query(Client).filter(Client.id == Client_id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Check if user has permission to update this Client
        if current_user.role_id == 3:  # super_admin - can update any client
            pass  # No restrictions
        elif current_user.role_id == 1:  # admin - can update clients from their company
            # Check if the client belongs to a user from the same company
            from ..models import User
            client_user = db.query(User).filter(User.id == db_Client.user_id).first()
            if not client_user or client_user.company_id != current_user.company_id:
                raise HTTPException(status_code=403, detail="Not authorized to update this Client")
        else:  # standard - only their own clients
            if db_Client.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to update this Client")
        
        # Update the Client
        for key, value in client_update.dict(exclude_unset=True).items():
            setattr(db_Client, key, value)
        db.commit()
        db.refresh(db_Client)
        return db_Client
    except Exception as e:
        logger.error(f"Error updating Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to update Client")

@router.delete("/{Client_id}", response_model=dict)
def delete_Client(Client_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role_id([1, 2, 3]))):  # Role 1 (admin), Role 2 (standard), and Role 3 (super_admin)
    debug("DELETE /api/Clients/{} called", Client_id)
    try:
        # First find the client
        db_Client = db.query(Client).filter(Client.id == Client_id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Check permissions
        if current_user.role_id == 3:  # super_admin - can delete any client
            pass  # No restrictions
        elif current_user.role_id == 1:  # admin - can delete clients from their company
            # Check if the client belongs to a user from the same company
            from ..models import User
            client_user = db.query(User).filter(User.id == db_Client.user_id).first()
            if not client_user or client_user.company_id != current_user.company_id:
                raise HTTPException(status_code=403, detail="Not authorized to delete this Client")
        else:  # standard - only their own clients
            if db_Client.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to delete this Client")
        
        db.delete(db_Client)
        db.commit()
        return {"detail": "Client deleted"}
    except Exception as e:
        logger.error(f"Error deleting Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to delete Client") 