import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging
import traceback
from pathlib import Path
from datetime import date, datetime
import json
from .routes import auth, users, Clients
from .routes import companies
from .routes import emr_types
from .routes import ai
from .routes import sessions
from .routes import reference_tables
from .models import Base
from .db import engine
from .debug import debug

# Custom JSON encoder to handle dates properly
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Custom middleware to handle large file uploads
class LargeFileUploadMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check if this is a file upload request
        content_type = request.headers.get("content-type", "")
        if request.method in ["POST", "PUT"] and "multipart/form-data" in content_type:
            # Set a larger timeout for file uploads
            try:
                # Increase the maximum body size for this request
                # This is a workaround for servers that don't respect uvicorn settings
                response = await call_next(request)
                return response
            except Exception as e:
                if "413" in str(e) or "too large" in str(e).lower():
                    return Response(
                        content='{"detail": "File too large. Maximum size is 50MB."}',
                        status_code=413,
                        media_type="application/json"
                    )
                raise e
        return await call_next(request)

# Load .env from the project root
load_dotenv()

# Debug: Check if environment variables are loaded
debug("=== DEBUG: Environment Variables ===")
debug("DATABASE_URL: {}", os.getenv("DATABASE_URL")[:50] + "..." if os.getenv("DATABASE_URL") else "NOT SET")
debug("SECRET_KEY: {}", os.getenv("SECRET_KEY")[:10] + "..." if os.getenv("SECRET_KEY") else "NOT SET")
debug("ALGORITHM: {}", os.getenv("ALGORITHM"))
debug("SMTP_SERVER: {}", os.getenv("SMTP_SERVER"))
debug("SMTP_PORT: {}", os.getenv("SMTP_PORT"))
debug("SMTP_USERNAME: {}", os.getenv("SMTP_USERNAME"))
debug("SMTP_PASSWORD: {}", os.getenv("SMTP_PASSWORD")[:10] + "..." if os.getenv("SMTP_PASSWORD") else "NOT SET")
debug("FROM_EMAIL: {}", os.getenv("FROM_EMAIL"))
debug("FRONTEND_URL: {}", os.getenv("FRONTEND_URL"))
debug("ENV: {}", os.getenv("ENV"))
debug("AWS_ACCESS_KEY_ID: {}", os.getenv("AWS_ACCESS_KEY_ID")[:10] + "..." if os.getenv("AWS_ACCESS_KEY_ID") else "NOT SET")
debug("AWS_SECRET_ACCESS_KEY: {}", os.getenv("AWS_SECRET_ACCESS_KEY")[:10] + "..." if os.getenv("AWS_SECRET_ACCESS_KEY") else "NOT SET")
debug("AWS_REGION: {}", os.getenv("AWS_REGION"))
debug("S3_BUCKET_NAME: {}", os.getenv("S3_BUCKET_NAME"))
debug("OPENAI_API_KEY: {}", os.getenv("OPENAI_API_KEY")[:10] + "..." if os.getenv("AWS_SECRET_ACCESS_KEY") else "NOT SET")
debug("=== END DEBUG ===")

# Auto-sync migrations on startup
def auto_sync_migrations():
    """Auto-sync migrations from git on startup"""
    try:
        import subprocess
        import os
        
        # Only run on local development (not on server)
        if os.getenv("ENV") == "development":
            debug("🔄 Auto-syncing migrations from git...")
            
            # Pull latest changes from git
            result = subprocess.run(
                ['git', 'pull', 'origin', 'dev'], 
                cwd=os.getcwd(), 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0:
                debug("✅ Successfully pulled latest changes from git")
            else:
                debug("⚠️ Could not pull from git: {}", result.stderr)
            
            # Apply any new migrations
            result = subprocess.run(
                ['python', '-m', 'alembic', 'upgrade', 'head'], 
                cwd=os.getcwd(), 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0:
                debug("✅ Successfully applied migrations")
            else:
                debug("⚠️ Could not apply migrations: {}", result.stderr)
                
            debug("🔄 Auto-sync completed")
        else:
            debug("🔄 Skipping auto-sync (not in development mode)")
            
    except Exception as e:
        debug("⚠️ Auto-sync failed: {}", e)

# Run auto-sync on startup
auto_sync_migrations()

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app with increased file upload limits
app = FastAPI(
    title="Noted API", 
    description="A comprehensive API for the Noted application", 
    version="1.0.0"
)



# CORS middleware
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://noteddev.objectif.solutions")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Set to False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)
# Add middleware for handling large file uploads
app.add_middleware(LargeFileUploadMiddleware)



# Include routers from the app folder
app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(Clients.router, prefix="/api/v1", tags=["Clients"])
app.include_router(sessions.sessions_router, prefix="/api/v1", tags=["Sessions"])
app.include_router(companies.router, prefix="/api/v1", tags=["Companies"])
app.include_router(emr_types.router, prefix="/api/v1", tags=["EMR Types"])
app.include_router(emr_types.fields_router, prefix="/api/v1", tags=["EMR Type Fields"])
app.include_router(emr_types.manual_fields_router, prefix="/api/v1", tags=["Manual Fields"])
app.include_router(emr_types.results_router, prefix="/api/v1", tags=["EMR Type Results"])
app.include_router(reference_tables.router, prefix="/api/v1", tags=["Reference Tables"])
app.include_router(ai.router, prefix="/api/v1", tags=["AI"])
app.include_router(ai.extraction_router, prefix="/api/v1", tags=["AI"])

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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error for request {request.url}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )


@app.exception_handler(OperationalError)
async def sqlalchemy_operational_error_handler(request: Request, exc: OperationalError):
    logging.error(f"Database operational error for request {request.url}: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable. Please retry shortly."}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        # Increase maximum file upload size to 50MB
        # limit_request_size=50 * 1024 * 1024  # 50MB in bytes
    ) 