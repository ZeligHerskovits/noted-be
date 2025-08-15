from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Client
from typing import List
from app.schemas import ClientCreate, ClientUpdate, ClientResponse
import logging
from app.routes.auth import get_current_user_with_role
from datetime import date
from uuid import UUID
import traceback

router = APIRouter(prefix="/api/Clients", tags=["Clients"])

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
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print(f"GET /api/Clients/{Client_id} called")
    try:
        # First try to find Client by ID only
        db_Client = db.query(Client).filter(Client.id == Client_id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Check if user has permission to view this Client
        if current_user.role_id != 3:  # Not super_admin
            if db_Client.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to view this Client")
        
        return db_Client
    except Exception as e:
        logger.error(f"Error fetching Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch Client")

@router.get("", response_model=List[ClientResponse])
def list_Clients(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print("GET /api/Clients called")
    try:
        if current_user.role_id == 3:  # super_admin
            Clients = db.query(Client).all()
        else:  # admin or standard
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
    current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))
):
    print(f"POST /api/Clients called with: {client_data}")
    try:
        client_dict = client_data.dict(exclude={"user_id"})  # Remove user_id from request
        client_dict["user_id"] = current_user.id  # Assign from token/session
        # Use date_of_birth from frontend (no hardcoding)
        new_client = Client(**client_dict)
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        return new_client
    except Exception as e:
        logger.error(f"Error creating Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create Client")

@router.put("/{Client_id}", response_model=ClientResponse)
def update_Client(Client_id: UUID, Client: ClientUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))):
    print(f"PUT /api/Clients/{Client_id} called with: {Client}")
    try:
        # First try to find Client by ID only
        db_Client = db.query(Client).filter(Client.id == Client_id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Check if user has permission to update this Client
        if current_user.role_id != 3:  # Not super_admin
            if db_Client.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to update this Client")
        
        # Update the Client
        for key, value in Client.dict(exclude_unset=True).items():
            setattr(db_Client, key, value)
        db.commit()
        db.refresh(db_Client)
        return db_Client
    except Exception as e:
        logger.error(f"Error updating Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to update Client")

@router.delete("/{Client_id}", response_model=dict)
def delete_Client(Client_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user_with_role(["super_admin", "admin", "standard"]))):
    print(f"DELETE /api/Clients/{Client_id} called")
    try:
        db_Client = db.query(Client).filter(Client.id == Client_id, Client.user_id == current_user.id).first()
        if not db_Client:
            raise HTTPException(status_code=404, detail="Client not found")
        db.delete(db_Client)
        db.commit()
        return {"detail": "Client deleted"}
    except Exception as e:
        logger.error(f"Error deleting Client: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to delete Client") 