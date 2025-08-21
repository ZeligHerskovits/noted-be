from sqlalchemy.orm import Session
from .models import User, Otp, Role, Company, EmrType, EMRTypeField, EMRTypeResult, Client, Session as SessionModel, ManualField
from passlib.context import CryptContext
import jwt
import datetime
from sqlalchemy import and_
import random
import secrets
import os
import subprocess
from uuid import UUID
from typing import List, Optional

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password: str, full_name: str, company_id: UUID, mobile_phone: str = None, user_type: str = None):
    hashed_password = get_password_hash(password)
    user = User(email=email, hashed_password=hashed_password, full_name=full_name, role_id=1, company_id=company_id, mobile_phone=mobile_phone, is_active=False, user_type=user_type)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: int = 60*24, role: str = None):
    to_encode = data.copy()
    if role:
        to_encode["role"] = role
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_otp(db: Session, user_id: UUID, otp_code: str):
    return db.query(Otp).filter(
        and_(
            Otp.user_id == user_id,
            Otp.otp_code == otp_code,
            Otp.used == False
        )
    ).order_by(Otp.expires_at.desc()).first()

def mark_otp_used(db: Session, otp: Otp):
    otp.used = True
    db.commit()
    db.refresh(otp)
    return otp

def reset_user_password(db: Session, user: User, new_password: str, otp: Otp):
    user.hashed_password = get_password_hash(new_password)
    otp.used = True
    db.commit()
    db.refresh(user)
    db.refresh(otp)
    return user

def get_user_role(db: Session, user: User):
    role = db.query(Role).filter(Role.id == user.role_id).first()
    return role.name if role else None

def generate_and_store_otp(db: Session, user: User, expires_minutes: int = 10):
    otp_code = ''.join(random.choices('0123456789', k=6))
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes)
    otp = Otp(user_id=user.id, otp_code=otp_code, expires_at=expires_at, used=False)
    db.add(otp)
    db.commit()
    db.refresh(otp)
    return otp_code

def get_all_clients(db: Session):
    clients = db.query(Client).all()
   
    return clients

def get_all_users_with_roles(db: Session):
    users = db.query(User).all()
    companies = {c.id: c.name for c in db.query(Company).all()}
    roles = {r.id: r.name for r in db.query(Role).all()}
    enriched_users = []
    for user in users:
        user_dict = user.__dict__.copy()
        user_dict['company_name'] = companies.get(user.company_id)
        user_dict['role_name'] = roles.get(user.role_id)
        user_dict['is_active'] = user.is_active
        enriched_users.append(user_dict)
    return enriched_users

def create_company(db: Session, name: str, industry: str, emr: str = None):
    company = Company(name=name, industry=industry, emr=emr)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company

def generate_device_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def set_email_verification_token(db: Session, user: User, token: str):
    user.email_verification_token = token
    db.commit()
    db.refresh(user)
    return user

def verify_email_token(db: Session, token: str):
    user = db.query(User).filter(User.email_verification_token == token).first()
    if user:
        user.is_email_verified = True
        user.email_verification_token = None
        db.commit()
        db.refresh(user)
    return user

# EMR Type CRUD operations
def create_emr_type(db: Session, name: str, session_type: Optional[str] = None,
                   documentation_methods: Optional[str] = None, files: Optional[List[dict]] = None,
                   instructions: Optional[str] = None, response: Optional[str] = None):
    emr_type = EmrType(
        name=name,
        session_type=session_type,
        documentation_methods=documentation_methods,
        files=files,
        instructions=instructions,
        response=response,
        status='draft'  # Set default status to draft
    )
    db.add(emr_type)
    db.commit()
    db.refresh(emr_type)
    return emr_type

def get_emr_type(db: Session, emr_type_id: UUID):
    return db.query(EmrType).filter(EmrType.id == emr_type_id).first()

def get_all_emr_types(db: Session):
    return db.query(EmrType).all()

def update_emr_type(db: Session, emr_type_id: UUID, name: Optional[str] = None,
                   session_type: Optional[str] = None, documentation_methods: Optional[str] = None,
                   files: Optional[List[dict]] = None, instructions: Optional[str] = None,
                   response: Optional[str] = None, status: Optional[str] = None,
                   total_chunks: Optional[int] = None, processed_chunks: Optional[int] = None):
    print(f"=== DEBUG: update_emr_type called with emr_type_id={emr_type_id}, processed_chunks={processed_chunks}, total_chunks={total_chunks} ===")
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        print(f"=== DEBUG: EMR type not found for id={emr_type_id} ===")
        return None

    if name is not None:
        emr_type.name = name
    if session_type is not None:
        emr_type.session_type = session_type
    if documentation_methods is not None:
        emr_type.documentation_methods = documentation_methods
    if files is not None:
        emr_type.files = files
    if instructions is not None:
        emr_type.instructions = instructions
    if response is not None:
        emr_type.response = response
    if status is not None:
        emr_type.status = status
    if total_chunks is not None:
        emr_type.total_chunks = total_chunks
        print(f"=== DEBUG: Updated total_chunks to {total_chunks} ===")
    if processed_chunks is not None:
        emr_type.processed_chunks = processed_chunks
        print(f"=== DEBUG: Updated processed_chunks to {processed_chunks} ===")

    print(f"=== DEBUG: About to commit database changes ===")
    db.commit()
    print(f"=== DEBUG: Database commit completed ===")
    db.refresh(emr_type)
    print(f"=== DEBUG: Database refresh completed, current processed_chunks={emr_type.processed_chunks} ===")
    return emr_type

def delete_emr_type(db: Session, emr_type_id: UUID):
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        return False

    db.delete(emr_type)
    db.commit()
    return True

# EMR Type Field CRUD operations
def create_emr_type_field(db: Session, name: str, type: str, analyzable: Optional[str] = None, api_name: Optional[str] = None):
    # If api_name is not provided, auto-generate it from the field name
    if api_name is None:
        from .migration_utils import migration_manager
        api_name = migration_manager.sanitize_field_name(name)
    
    try:
        # Step 1: Create EMR field (don't commit yet)
        field = EMRTypeField(name=name, type=type, analyzable=analyzable, api_name=api_name)
        db.add(field)
        db.flush()  # Don't commit yet
        
        # Step 2: Create and apply migration to add field to sessions table
        from .migration_utils import migration_manager
        import subprocess
        import os
        
        # Check if field already exists in sessions table
        if not migration_manager.check_field_exists(db, api_name):
            # Create migration file to add field to sessions table
            migration_success = migration_manager.create_field_migration(api_name, "TEXT")
            if migration_success:
                print(f"✅ Successfully created migration for field '{name}'")
                
                # Auto-apply the migration
                try:
                    result = subprocess.run(
                        ['python', '-m', 'alembic', 'upgrade', 'head'],
                        cwd=os.getcwd(),
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        print(f"🎉 Successfully applied migration! Field '{api_name}' added to sessions table")
                        
                        # Auto-commit migration to git for sync
                        try:
                            subprocess.run(['git', 'add', 'alembic/versions/'], cwd=os.getcwd(), capture_output=True)
                            subprocess.run(['git', 'commit', '-m', f'Auto-commit: Add field {name} to sessions'], cwd=os.getcwd(), capture_output=True)
                            subprocess.run(['git', 'push', 'origin', 'dev'], cwd=os.getcwd(), capture_output=True)
                            print("✅ Migration auto-committed to git for sync")
                        except Exception as e:
                            print(f"⚠️ Could not auto-commit migration: {e}")
                    else:
                        # Sessions column creation failed - ROLLBACK everything
                        print(f"❌ Sessions column creation failed: {result.stderr}")
                        db.rollback()
                        raise Exception("Failed to create sessions column")
                except Exception as e:
                    # Sessions column creation failed - ROLLBACK everything
                    print(f"❌ Sessions column creation failed: {str(e)}")
                    db.rollback()
                    raise Exception("Failed to create sessions column")
            else:
                # Migration creation failed - ROLLBACK everything
                print(f"❌ Failed to create migration for field '{name}'")
                db.rollback()
                raise Exception("Failed to create migration")
        else:
            print(f"ℹ️  Field '{api_name}' already exists in sessions table")
        
        # Step 3: Both succeeded - COMMIT everything
        db.commit()
        db.refresh(field)
        return field
        
    except Exception as e:
        # ANY error - ROLLBACK everything
        db.rollback()
        print(f"❌ Transaction failed: {str(e)}")
        raise Exception("Failed to create field. Please try again.")

def get_emr_type_field(db: Session, field_id: UUID):
    return db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()

def get_all_emr_type_fields(db: Session):
    return db.query(EMRTypeField).all()

def update_emr_type_field(db: Session, field_id: UUID, name: Optional[str] = None, type: Optional[str] = None, analyzable: Optional[str] = None, api_name: Optional[str] = None):
    field = get_emr_type_field(db, field_id)
    if not field:
        return None

    # Store old name for column renaming
    old_name = field.name
    old_api_name = field.api_name

    try:
        # Step 1: Update EMR field (don't commit yet)
        if name is not None:
            field.name = name
            # If name is updated and api_name is not provided, auto-update api_name
            if api_name is None:
                from .migration_utils import migration_manager
                field.api_name = migration_manager.sanitize_field_name(name)
        if type is not None:
            field.type = type
        if analyzable is not None:
            field.analyzable = analyzable
        if api_name is not None:
            field.api_name = api_name
        
        db.flush()  # Don't commit yet

        # Step 2: If the name changed, rename the column in sessions table
        if name is not None and name != old_name:
            try:
                from .migration_utils import migration_manager
                
                # Find the actual current column name in the database
                actual_old_column_name = migration_manager.find_actual_column_name(db, old_name, old_api_name)
                new_sanitized_name = field.api_name
                
                if actual_old_column_name != new_sanitized_name:
                    # Create migration to rename the column
                    migration_success = migration_manager.rename_column_migration(
                        actual_old_column_name, 
                        new_sanitized_name, 
                        "sessions"
                    )
                    if migration_success:
                        print(f"✅ Successfully created migration to rename column '{actual_old_column_name}' to '{new_sanitized_name}' in sessions table")
                        
                        # Auto-apply the migration
                        try:
                            import subprocess
                            import os
                            result = subprocess.run(
                                ['python', '-m', 'alembic', 'upgrade', 'head'],
                                cwd=os.getcwd(),
                                capture_output=True,
                                text=True,
                                timeout=30
                            )
                            if result.returncode == 0:
                                print(f"🎉 Successfully applied migration! Column renamed from '{actual_old_column_name}' to '{new_sanitized_name}'")
                                
                                # Auto-commit migration to git for sync
                                try:
                                    subprocess.run(['git', 'add', 'alembic/versions/'], cwd=os.getcwd(), capture_output=True)
                                    subprocess.run(['git', 'commit', '-m', f'Auto-commit: Rename field {old_name} to {name}'], cwd=os.getcwd(), capture_output=True)
                                    subprocess.run(['git', 'push', 'origin', 'dev'], cwd=os.getcwd(), capture_output=True)
                                    print("✅ Migration auto-committed to git for sync")
                                except Exception as e:
                                    print(f"⚠️ Could not auto-commit migration: {e}")
                            else:
                                # Sessions column rename failed - ROLLBACK everything
                                print(f"❌ Sessions column rename failed: {result.stderr}")
                                db.rollback()
                                raise Exception("Failed to rename sessions column")
                        except Exception as e:
                            # Sessions column rename failed - ROLLBACK everything
                            print(f"❌ Sessions column rename failed: {str(e)}")
                            db.rollback()
                            raise Exception("Failed to rename sessions column")
                    else:
                        # Migration creation failed - ROLLBACK everything
                        print(f"❌ Failed to create migration for column rename")
                        db.rollback()
                        raise Exception("Failed to create rename migration")
            except Exception as e:
                # Column rename failed - ROLLBACK everything
                print(f"❌ Column rename failed: {str(e)}")
                db.rollback()
                raise Exception("Failed to rename column")

        # Step 3: Both succeeded - COMMIT everything
        db.commit()
        db.refresh(field)
        return field
        
    except Exception as e:
        # ANY error - ROLLBACK everything
        db.rollback()
        print(f"❌ Transaction failed: {str(e)}")
        raise Exception("Failed to update field. Please try again.")

def delete_emr_type_field(db: Session, field_id: UUID):
    field = get_emr_type_field(db, field_id)
    if not field:
        return False

    db.delete(field)
    db.commit()
    return True

# EMR Type Result CRUD operations
def create_emr_type_result(db: Session, emr_type_id: UUID, key: str, value: Optional[str] = None, status: Optional[str] = None, label: Optional[str] = None):
    result = EMRTypeResult(
        emr_type_id=emr_type_id,
        key=key,
        value=value,
        status=status,
        label=label
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result

def get_emr_type_results_by_emr_type(db: Session, emr_type_id: UUID):
    return db.query(EMRTypeResult).filter(EMRTypeResult.emr_type_id == emr_type_id).all()

def get_all_emr_type_results(db: Session):
    """Get all EMR type results"""
    return db.query(EMRTypeResult).all()

def delete_all_emr_type_results_by_emr_type(db: Session, emr_type_id: UUID):
    results = db.query(EMRTypeResult).filter(EMRTypeResult.emr_type_id == emr_type_id).all()
    for result in results:
        db.delete(result)
    db.commit()
    return True

# Session CRUD operations
def create_session(db: Session, user_id: UUID, **session_data):
    """Create a new session with dynamic fields"""
    # Get the EMR type name from emr_type_id
    emr_type_id = session_data.get('emr_type_id')
    if emr_type_id:
        emr_type = db.query(EmrType).filter(EmrType.id == emr_type_id).first()
        if emr_type:
            session_data['emr_name'] = emr_type.name
    
    # Get all dynamic fields from emr_type_fields (global)
    emr_fields = db.query(EMRTypeField).all()
    
    # Create mapping from original name to api_name (case-insensitive)
    field_name_mapping = {}
    for field in emr_fields:
        if field.api_name:
            # Store both original case and lowercase versions
            field_name_mapping[field.name] = field.api_name
            field_name_mapping[field.name.lower()] = field.api_name  # Lowercase version
            field_name_mapping[field.api_name] = field.api_name  # Also allow api_name directly
            
            # Create variations without dashes for flexible matching
            name_without_dashes = field.name.replace('-', ' ').replace('  ', ' ').strip()
            field_name_mapping[name_without_dashes] = field.api_name
            field_name_mapping[name_without_dashes.lower()] = field.api_name
            
            # Create variations with underscores
            name_with_underscores = field.name.replace('-', '_').replace(' ', '_')
            field_name_mapping[name_with_underscores] = field.api_name
            field_name_mapping[name_with_underscores.lower()] = field.api_name
            
            # Create variations with no spaces/dashes
            name_no_spaces = field.name.replace('-', '').replace(' ', '')
            field_name_mapping[name_no_spaces] = field.api_name
            field_name_mapping[name_no_spaces.lower()] = field.api_name
            
            # Create variations with just spaces (no dashes)
            name_just_spaces = field.name.replace('-', ' ')
            field_name_mapping[name_just_spaces] = field.api_name
            field_name_mapping[name_just_spaces.lower()] = field.api_name
    
    dynamic_field_names = {field.api_name for field in emr_fields if field.api_name}
    
    # Debug: Print what we have
    print(f"🔍 Field name mapping: {field_name_mapping}")
    print(f"🔍 Session data keys: {list(session_data.keys())}")
    print(f"🔍 Session data values: {session_data}")
    
    # Static fields that are always allowed
    static_fields = {
        'client_id', 'emr_type_id', 'emr_name', 'manual_instructions', 
        'session_response', 'user_id'
    }
    
    # Combine static and dynamic field names
    allowed_fields = static_fields | dynamic_field_names
    
    # Smart field name matching function
    def find_matching_api_name(field_key, field_mapping):
        """Find the matching api_name for any field key variation"""
        # Try exact match first
        if field_key in field_mapping:
            return field_mapping[field_key]
        
        # Try lowercase
        if field_key.lower() in field_mapping:
            return field_mapping[field_key.lower()]
        
        # Try case-insensitive matching for all keys
        field_key_lower = field_key.lower()
        for original_name, api_name in field_mapping.items():
            if original_name.lower() == field_key_lower:
                return api_name
        
        # Try normalized versions (replace spaces, dashes, underscores)
        normalized_key = field_key.lower().replace('-', ' ').replace('_', ' ').replace('  ', ' ').strip()
        for original_name, api_name in field_mapping.items():
            normalized_original = original_name.lower().replace('-', ' ').replace('_', ' ').replace('  ', ' ').strip()
            if normalized_key == normalized_original:
                return api_name
        
        # Try removing all spaces/dashes/underscores
        clean_key = field_key.lower().replace('-', '').replace('_', '').replace(' ', '')
        for original_name, api_name in field_mapping.items():
            clean_original = original_name.lower().replace('-', '').replace('_', '').replace(' ', '')
            if clean_key == clean_original:
                return api_name
        
        return None
    
    # Transform session_data keys to match api_names
    transformed_data = {}
    for key, value in session_data.items():
        if key in allowed_fields:
            # Direct match (static field or api_name)
            transformed_data[key] = value
        else:
            # Try to find matching api_name
            api_name = find_matching_api_name(key, field_name_mapping)
            if api_name:
                transformed_data[api_name] = value
                print(f"🔍 Smart matched '{key}' → '{api_name}'")
            else:
                print(f"⚠️ Field '{key}' not found in allowed fields or field mapping")
    
    print(f"🔍 Allowed fields: {allowed_fields}")
    print(f"🔍 Transformed data: {transformed_data}")
    
    # Create session using raw SQL to handle dynamic columns
    from sqlalchemy import text
    
    # Get all column names from the sessions table
    result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions'"))
    all_columns = [row[0] for row in result.fetchall()]
    
    # Filter data to only include columns that exist in the table
    table_data = {k: v for k, v in transformed_data.items() if k in all_columns}
    
    # Add user_id to the data
    table_data['user_id'] = user_id
    
    # Create session using raw SQL
    columns = ', '.join(table_data.keys())
    placeholders = ', '.join([f':{key}' for key in table_data.keys()])
    
    query = text(f"INSERT INTO sessions ({columns}) VALUES ({placeholders}) RETURNING *")
    result = db.execute(query, table_data)
    
    # Get the created session
    session_data = result.fetchone()
    db.commit()
    
    # Convert Row object to dictionary using _mapping
    session_dict = dict(session_data._mapping)
    
    # Create a simple object with all the data instead of SessionModel
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    session = SessionResult(**session_dict)
    return session

def get_session(db: Session, session_id: UUID):
    """Get session by ID with all dynamic fields"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE id = :session_id")
    result = db.execute(query, {"session_id": session_id})
    session_data = result.fetchone()
    
    if not session_data:
        return None
    
    # Convert Row object to dictionary
    session_dict = dict(session_data._mapping)
    
    # Create a simple object with all the data
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return SessionResult(**session_dict)

def get_sessions_by_user(db: Session, user_id: UUID):
    """Get all sessions for a specific user with all dynamic fields"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE user_id = :user_id")
    result = db.execute(query, {"user_id": user_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        session_dict = dict(session_data._mapping)
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**session_dict))
    
    return sessions

def get_all_sessions(db: Session):
    """Get all sessions (for super admin) with all dynamic fields"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions")
    result = db.execute(query)
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        session_dict = dict(session_data._mapping)
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**session_dict))
    
    return sessions

def get_sessions_by_emr_type(db: Session, emr_type_id: UUID):
    """Get all sessions for a specific EMR type with all dynamic fields"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE emr_type_id = :emr_type_id")
    result = db.execute(query, {"emr_type_id": emr_type_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        session_dict = dict(session_data._mapping)
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**session_dict))
    
    return sessions

def get_sessions_by_client(db: Session, client_id: UUID):
    """Get all sessions for a specific client with all dynamic fields"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE client_id = :client_id")
    result = db.execute(query, {"client_id": client_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        session_dict = dict(session_data._mapping)
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**session_dict))
    
    return sessions

def update_session(db: Session, session_id: UUID, **session_data):
    """Update a session with dynamic fields"""
    from sqlalchemy import text
    
    # First check if session exists
    check_query = text("SELECT id FROM sessions WHERE id = :session_id")
    result = db.execute(check_query, {"session_id": session_id})
    if not result.fetchone():
        return None
    
    # Get all dynamic fields from emr_type_fields (global)
    emr_fields = db.query(EMRTypeField).all()
    
    # Create mapping from original name to api_name (case-insensitive)
    field_name_mapping = {}
    for field in emr_fields:
        if field.api_name:
            # Store both original case and lowercase versions
            field_name_mapping[field.name] = field.api_name
            field_name_mapping[field.name.lower()] = field.api_name  # Lowercase version
            field_name_mapping[field.api_name] = field.api_name  # Also allow api_name directly
            
            # Create variations without dashes for flexible matching
            name_without_dashes = field.name.replace('-', ' ').replace('  ', ' ').strip()
            field_name_mapping[name_without_dashes] = field.api_name
            field_name_mapping[name_without_dashes.lower()] = field.api_name
            
            # Create variations with underscores
            name_with_underscores = field.name.replace('-', '_').replace(' ', '_')
            field_name_mapping[name_with_underscores] = field.api_name
            field_name_mapping[name_with_underscores.lower()] = field.api_name
            
            # Create variations with no spaces/dashes
            name_no_spaces = field.name.replace('-', '').replace(' ', '')
            field_name_mapping[name_no_spaces] = field.api_name
            field_name_mapping[name_no_spaces.lower()] = field.api_name
            
            # Create variations with just spaces (no dashes)
            name_just_spaces = field.name.replace('-', ' ')
            field_name_mapping[name_just_spaces] = field.api_name
            field_name_mapping[name_just_spaces.lower()] = field.api_name
    
    dynamic_field_names = {field.api_name for field in emr_fields if field.api_name}
    
    # Smart field name matching function
    def find_matching_api_name(field_key, field_mapping):
        """Find the matching api_name for any field key variation"""
        # Try exact match first
        if field_key in field_mapping:
            return field_mapping[field_key]
        
        # Try lowercase
        if field_key.lower() in field_mapping:
            return field_mapping[field_key.lower()]
        
        # Try normalized versions
        normalized_key = field_key.lower().replace('-', ' ').replace('_', ' ').replace('  ', ' ').strip()
        if normalized_key in field_mapping:
            return field_mapping[normalized_key]
        
        # Try removing all spaces/dashes/underscores
        clean_key = field_key.lower().replace('-', '').replace('_', '').replace(' ', '')
        for original_name, api_name in field_mapping.items():
            clean_original = original_name.lower().replace('-', '').replace('_', '').replace(' ', '')
            if clean_key == clean_original:
                return api_name
        
        return None
    
    # Static fields that are always allowed
    static_fields = {
        'client_id', 'emr_type_id', 'emr_name', 'manual_instructions', 
        'session_response', 'user_id'
    }
    
    # Combine static and dynamic field names
    allowed_fields = static_fields | dynamic_field_names
    
    # Get all column names from the sessions table
    result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions'"))
    all_columns = [row[0] for row in result.fetchall()]
    
    # Transform session_data keys to match api_names
    # Use a temporary dictionary to store the best value for each canonical api_name
    temp_transformed_data = {}
    
    # Iterate through the incoming session_data
    for key, value in session_data.items():
        print(f"🔍 Processing field: '{key}' = '{value}' (type: {type(value)})")
        
        # Find the canonical API name for the current key
        canonical_api_name = find_matching_api_name(key, field_name_mapping)
        
        if canonical_api_name:
            current_stored_value = temp_transformed_data.get(canonical_api_name)
            
            should_overwrite = False
            
            if canonical_api_name not in temp_transformed_data: # If not yet stored, always add
                should_overwrite = True
            elif value is not None and value != '': # New value is non-empty/non-None
                if current_stored_value is None or current_stored_value == '':
                    # New value is good, existing is empty/None, so overwrite
                    should_overwrite = True
                else:
                    # Both new and existing are good, last one wins (overwrite)
                    should_overwrite = True
            elif value is None or value == '': # New value is empty/None
                # If new value is empty/None, only overwrite if existing is also empty/None
                if current_stored_value is None or current_stored_value == '':
                    should_overwrite = True
                # Else (existing is good), do not overwrite
            
            if should_overwrite:
                temp_transformed_data[canonical_api_name] = value
                print(f"🔍 Smart matched '{key}' → '{canonical_api_name}' = '{value}' for update (OVERWRITING)")
            else:
                print(f"🔍 Smart matched '{key}' → '{canonical_api_name}' = '{value}' for update (SKIPPING - keeping existing '{current_stored_value}')")
        else:
            # If no canonical API name found, it's either a static field or an unknown field.
            # For static fields, add them directly to the transformed data.
            if key in allowed_fields: 
                temp_transformed_data[key] = value
                print(f"🔍 Direct match (static/allowed): '{key}' → '{key}' = '{value}'")
            else:
                print(f"⚠️ Field '{key}' not found in allowed fields or field mapping for update (SKIPPED)")

    # Now, `transformed_data` is the final set of key-value pairs after smart matching and prioritization.
    transformed_data = temp_transformed_data
    print(f"🔍 Transformed data (after smart prioritization): {transformed_data}")
    
    # Filter transformed_data to only include valid columns
    update_data = {}
    for key, value in transformed_data.items():
        if key in all_columns and value is not None:
            update_data[key] = value
            print(f"🔍 Added to update: '{key}' = '{value}'")
        else:
            print(f"⚠️ Field '{key}' filtered out - not in columns or value is None (value: '{value}', type: {type(value)})")
    
    print(f"🔍 Final update data: {update_data}")
    
    if not update_data:
        # No valid fields to update, just return the session
        return get_session(db, session_id)
    
    # Build the UPDATE query
    set_clause = ', '.join([f"{key} = :{key}" for key in update_data.keys()])
    query = text(f"UPDATE sessions SET {set_clause} WHERE id = :session_id RETURNING *")
    
    # Execute the update
    update_data['session_id'] = session_id
    result = db.execute(query, update_data)
    updated_session_data = result.fetchone()
    db.commit()
    
    # Convert Row object to dictionary
    session_dict = dict(updated_session_data._mapping)
    
    # Create a simple object with all the data
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return SessionResult(**session_dict)

def delete_session(db: Session, session_id: UUID):
    """Delete a session"""
    session = get_session(db, session_id)
    if not session:
        return False
    
    db.delete(session)
    db.commit()
    return True

# Manual Field CRUD operations
def create_manual_field(db: Session, name: str, emr_type_id: UUID):
    """Create a new manual field"""
    manual_field = ManualField(name=name, emr_type_id=emr_type_id)
    db.add(manual_field)
    db.commit()
    db.refresh(manual_field)
    return manual_field

def get_manual_field(db: Session, field_id: UUID):
    """Get manual field by ID"""
    return db.query(ManualField).filter(ManualField.id == field_id).first()

def get_all_manual_fields(db: Session):
    """Get all manual fields"""
    return db.query(ManualField).all()

def get_manual_fields_by_emr_type(db: Session, emr_type_id: UUID):
    """Get all manual fields for a specific EMR type"""
    return db.query(ManualField).filter(ManualField.emr_type_id == emr_type_id).all()

def update_manual_field(db: Session, field_id: UUID, name: Optional[str] = None):
    """Update a manual field"""
    manual_field = get_manual_field(db, field_id)
    if not manual_field:
        return None

    if name is not None:
        manual_field.name = name

    db.commit()
    db.refresh(manual_field)
    return manual_field

def delete_manual_field(db: Session, field_id: UUID):
    """Delete a manual field"""
    manual_field = get_manual_field(db, field_id)
    if not manual_field:
        return False

    db.delete(manual_field)
    db.commit()
    return True 