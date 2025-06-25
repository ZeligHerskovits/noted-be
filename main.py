from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from passlib.context import CryptContext

# Database connection
DATABASE_URL = "postgresql+psycopg2://devuser:noteddev@1234@3.149.182.148:5432/noted_dev"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# SQLAlchemy model for the existing users table (fields must match the actual table)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

# Pydantic model for registration
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role_id: int

app = FastAPI()

@app.post("/auth/register")
def register_user(request: RegisterRequest):
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        # Hash the password
        hashed_password = get_password_hash(request.password)
        # Create new user instance
        new_user = User(
            email=request.email,
            hashed_password=hashed_password,
            full_name=request.full_name,
            role_id=request.role_id
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"success": True, "user_id": new_user.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()