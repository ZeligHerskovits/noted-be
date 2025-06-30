from dotenv import load_dotenv
import os
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, users, patients
from .models import Base
from .db import engine

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Noted API", 
    description="A comprehensive API for the Noted application", 
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
   allow_origins=[
        "http://localhost:3000",
        "https://noteddev.objectif.solutions"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from the app folder
app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(patients.router, prefix="/api/v1", tags=["Patients"])

# Root endpoint to test if the API is running
@app.get("/")
def root():
    """Root endpoint to test if the API is running"""
    return {
        "message": "Noted API is running! 🚀✨", 
        "status": "healthy",
        "version": "1.0.0"
    }

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "API is working correctly",
        "timestamp": "2024-01-01T00:00:00Z"
    }

# Test endpoint
@app.get("/test")
def test_endpoint():
    """Simple test endpoint"""
    return {
        "success": True,
        "message": "Test endpoint is working!",
        "data": {
            "app_name": "Noted Backend",
            "version": "1.0.0",
            "environment": "development"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 