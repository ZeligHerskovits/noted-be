from sqlalchemy.orm import Session
from .models import User, Otp, Role, Company, EmrType, EMRTypeField, EMRTypeResult, Client, Session as SessionModel, ManualField, CopingSkill, ClinicalSpecialty, DocumentationMethod, UserCopingSkill, UserClinicalSpecialty, UserEMRDocumentationPair, Modality, ModalityStep, Activity, SubActivity
from passlib.context import CryptContext
import jwt
import datetime
from sqlalchemy import and_
import random
import secrets
import boto3
import os
import subprocess
from uuid import UUID
from typing import List, Optional
from .debug import debug

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password: str, full_name: str, company_id: UUID, mobile_phone: str = None, user_type: str = None):
    hashed_password = get_password_hash(password)
    user = User(email=email, hashed_password=hashed_password, full_name=full_name, role_id=1, company_id=company_id, 
                mobile_phone=mobile_phone, is_active=False, user_type=user_type)
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
        
        # Get related data from junction tables
        user_dict['emr_type_documentation_pairs'] = get_user_emr_documentation_pairs(db, user.id)
        user_dict['coping_skills'] = [j.coping_skill_id for j in db.query(UserCopingSkill).filter(UserCopingSkill.user_id == user.id).all()]
        user_dict['clinical_specialties'] = [j.clinical_specialty_id for j in db.query(UserClinicalSpecialty).filter(UserClinicalSpecialty.user_id == user.id).all()]
        # Handle type_writing - SQLAlchemy already converts PostgreSQL array to Python list
        if user.type_writing:
            if isinstance(user.type_writing, list):
                user_dict['type_writing'] = user.type_writing
            else:
                # Fallback for string format
                array_str = str(user.type_writing).strip('{}')
                if array_str:
                    user_dict['type_writing'] = [item.strip('"') for item in array_str.split(',')]
                else:
                    user_dict['type_writing'] = []
        else:
            user_dict['type_writing'] = []
        
        enriched_users.append(user_dict)
    return enriched_users

def create_company(db: Session, name: str, industry: str, emr: List[str] = None):
    # Convert single string to list for backward compatibility if needed
    if emr is not None and isinstance(emr, str):
        emr = [emr]
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

# Add this global S3 client (same pattern as emr_types.py)
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
    verify=False  # Add this to match your existing pattern
)

def get_default_session_instructions_from_s3():
    """Fetch default session instructions from S3"""
    try:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set")
            
        s3_key = "default-session-instructions.txt"
        
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        default_instructions = response['Body'].read().decode('utf-8')
        
        return default_instructions
        
    except Exception as e:
        # Fallback to a basic template if S3 fails
        fallback_instructions = """I'm a therapist providing sessions for my client, below are the rules on how to write a session note:

for each session, I need 3 notes as follows
Section 1: Field "Methods"
Section 2: Field "Progress_towards_goal"
Section 3: Field "Recommended_changes"

Please provide comprehensive analysis based on the session data."""
        
        print(f"Warning: Could not fetch from S3: {e}. Using fallback instructions.")
        return fallback_instructions

import html
import re

def parse_instructions_into_sections(instructions_text: str):
    """Put EVERYTHING up to the SECOND 'Section 2:' into methods_instructions."""
    try:
        s = html.unescape(instructions_text)
        # Clean up whitespace: remove \n, \r, extra spaces, tabs
        s = re.sub(r'\s+', ' ', s).strip()

        sections = {
            'methods_instructions': '',
            'progress_towards_goal_instructions': '',
            'recommended_changes_instructions': ''
        }

        # Find all 'Section 2:' markers
        s2_positions = [m.start() for m in re.finditer(r'Section 2:', s)]
        debug(f"Found Section 2 positions: {s2_positions}")
        
        # Index where methods should stop: the SECOND 'Section 2:' if present
        if len(s2_positions) >= 2:
            cut2 = s2_positions[1]  # second occurrence
        elif len(s2_positions) == 1:
            cut2 = s2_positions[0]  # only one; best effort
        else:
            cut2 = -1               # none; whole thing is Section 1
        
        debug(f"cut2 = {cut2}")
        debug(f"Length of s: {len(s)}")
        debug(f"Length of s[:cut2]: {len(s[:cut2]) if cut2 != -1 else len(s)}")

        # Find 'Section 3:' AFTER the cut2 (if any)
        s3_idx = s.find('Section 3:', cut2 if cut2 != -1 else 0)

        # 1) methods_instructions = from begining til second 'Section 2:' or maybe its first Section 2:
        sections['methods_instructions'] = s[:cut2].strip() if cut2 != -1 else s.strip()
        debug(f"Length of methods_instructions: {len(sections['methods_instructions'])}")

        # 2) progress_towards_goal_instructions: = from SECOND or maybe first 'Section 2:' -> 'Section 3:' (or to end if no Section 3:)
        if cut2 != -1:
            if s3_idx != -1 and s3_idx > cut2:
                sections['progress_towards_goal_instructions'] = s[cut2:s3_idx].strip()
            else:
                sections['progress_towards_goal_instructions'] = s[cut2:].strip()

        # 3) recommended_changes_instructions: = from 'Section 3:' -> end
        if s3_idx != -1:
            sections['recommended_changes_instructions'] = s[s3_idx:].strip()

        return sections

    except Exception as e:
        print(f"Error parsing S3 instructions: {e}")
        return {
            'methods_instructions': '',
            'progress_towards_goal_instructions': '',
            'recommended_changes_instructions': ''
        }
# EMR Type CRUD operations
def create_emr_type(db: Session, name: str, session_type: Optional[str] = None,
                   documentation_method_id: Optional[UUID] = None, files: Optional[List[dict]] = None,
                   json_response: Optional[str] = None,
                   emr_url: Optional[str] = None, created_from_chrome: bool = False,
                   user_id: Optional[UUID] = None):
    
    # Get session instructions from the selected documentation method
    parsed_sections = {
        'methods_instructions': '',
        'progress_towards_goal_instructions': '',
        'recommended_changes_instructions': ''
    }
    
    if documentation_method_id:
        # Get the documentation method and its session instructions
        doc_method = get_documentation_method(db, documentation_method_id)
        if doc_method and doc_method.session_instructions:
            # Parse the documentation method's session instructions into the three sections
            parsed_sections = parse_instructions_into_sections(doc_method.session_instructions)
        else:
            raise Exception(f"You select a documentation method with no instructions")   
    else:
        raise Exception(f"You didnt select a valid documentation method")   
       
    emr_type = EmrType(
        name=name,
        session_type=session_type,
        documentation_method_id=documentation_method_id,
        files=files,
        json_response=json_response,
        status='draft',  # Set default status to draft
        methods_instructions=parsed_sections['methods_instructions'],
        progress_towards_goal_instructions=parsed_sections['progress_towards_goal_instructions'],
        recommended_changes_instructions=parsed_sections['recommended_changes_instructions'],
        emr_url=emr_url,
        created_from_chrome=created_from_chrome,
        user_id=user_id
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
                   session_type: Optional[str] = None, documentation_method_id: Optional[UUID] = None,
                   files: Optional[List[dict]] = None, 
                   json_response: Optional[str] = None, status: Optional[str] = None,
                   previous_status: Optional[str] = None,
                   total_chunks: Optional[int] = None, processed_chunks: Optional[int] = None,
                   methods_instructions: Optional[str] = None, progress_towards_goal_instructions: Optional[str] = None,
                   recommended_changes_instructions: Optional[str] = None, emr_url: Optional[str] = None,
                   xpath_pattern: Optional[str] = None):
    debug("=== DEBUG: update_emr_type called with emr_type_id={}, processed_chunks={}, total_chunks={} ===", emr_type_id, processed_chunks, total_chunks)
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        debug("=== DEBUG: EMR type not found for id={} ===", emr_type_id)
        return None

    if name is not None:
        emr_type.name = name
    if session_type is not None:
        emr_type.session_type = session_type
    if documentation_method_id is not None:
        # Check if documentation method actually changed from the previous value
        if emr_type.documentation_method_id != documentation_method_id:
            emr_type.documentation_method_id = documentation_method_id
            
            # Only update session instructions if documentation method changed
            doc_method = get_documentation_method(db, documentation_method_id)
            if doc_method and doc_method.session_instructions:
                # Parse the new documentation method's session instructions
                parsed_sections = parse_instructions_into_sections(doc_method.session_instructions)
                emr_type.methods_instructions = parsed_sections['methods_instructions']
                emr_type.progress_towards_goal_instructions = parsed_sections['progress_towards_goal_instructions']
                emr_type.recommended_changes_instructions = parsed_sections['recommended_changes_instructions']
            else:
                raise Exception(f"You select a documentation method with no instructions")  

    if files is not None:
        emr_type.files = files
    if json_response is not None:
        emr_type.json_response = json_response
    if status is not None:
        emr_type.status = status
    if previous_status is not None:
        emr_type.previous_status = previous_status
    if total_chunks is not None:
        emr_type.total_chunks = total_chunks
        debug("=== DEBUG: Updated total_chunks to {} ===", total_chunks)
    if processed_chunks is not None:
        emr_type.processed_chunks = processed_chunks
        debug("=== DEBUG: Updated processed_chunks to {} ===", processed_chunks)
    if methods_instructions is not None:
        emr_type.methods_instructions = methods_instructions
    if progress_towards_goal_instructions is not None:
        emr_type.progress_towards_goal_instructions = progress_towards_goal_instructions
    if recommended_changes_instructions is not None:
        emr_type.recommended_changes_instructions = recommended_changes_instructions
    if emr_url is not None:
        emr_type.emr_url = emr_url
    if xpath_pattern is not None:
        emr_type.xpath_pattern = xpath_pattern
        debug("=== DEBUG: Updated xpath_pattern ===")

    debug("=== DEBUG: About to commit database changes ===")
    db.commit()
    debug("=== DEBUG: Database commit completed ===")
    db.refresh(emr_type)
    debug("=== DEBUG: Database refresh completed, current processed_chunks={} ===", emr_type.processed_chunks)
    return emr_type

def delete_emr_type(db: Session, emr_type_id: UUID):
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        return False

    db.delete(emr_type)
    db.commit()
    return True

# EMR Type Field CRUD operations
def create_emr_type_field(db: Session, name: str, type: str, analyzable: Optional[str] = None, api_name: Optional[str] = None, dropdown_values: Optional[str] = None, instructions: Optional[str] = None):
    # If api_name is not provided, auto-generate it from the field name
    if api_name is None:
        from .migration_utils import migration_manager
        api_name = migration_manager.sanitize_field_name(name)
    
    # Check if EMR type field already exists (by name and emr_type_id)
    from .models import EMRTypeField
    existing_field = db.query(EMRTypeField).filter(
        EMRTypeField.name == name
    ).first()
    
    if existing_field:
        raise Exception(f"EMR type field with name '{name}' already exists")
    
    try:
        # Step 1: Create EMR field (don't commit yet)
        field = EMRTypeField(name=name, type=type, analyzable=analyzable, api_name=api_name, dropdown_values=dropdown_values, instructions=instructions)
        db.add(field)
        db.flush()  # Don't commit yet
        
        # Step 2: Create and apply migration to add field to sessions table
        from .migration_utils import migration_manager
        import subprocess
        import os
        
        # Check if field already exists in sessions table
        if not migration_manager.check_field_exists(db, api_name):
            # Create migration file to add field to sessions table with the correct type
            migration_success = migration_manager.create_field_migration(api_name, type)
            if migration_success:
                debug("✅ Successfully created migration for field '{}'", name)
                
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
                        debug("🎉 Successfully applied migration! Field '{}' added to sessions table", api_name)
                        
                        # Auto-commit migration to git for sync
                        try:
                            subprocess.run(['git', 'add', 'alembic/versions/'], cwd=os.getcwd(), capture_output=True)
                            subprocess.run(['git', 'commit', '-m', f'Auto-commit: Add field {name} to sessions'], cwd=os.getcwd(), capture_output=True)
                            subprocess.run(['git', 'push', 'origin', 'dev'], cwd=os.getcwd(), capture_output=True)
                            debug("✅ Migration auto-committed to git for sync")
                        except Exception as e:
                            debug("⚠️ Could not auto-commit migration: {}", e)
                    else:
                        # Sessions column creation failed - ROLLBACK everything
                        debug("❌ Sessions column creation failed: {}", result.stderr)
                        db.rollback()
                        raise Exception("Failed to create sessions column")
                except Exception as e:
                    # Sessions column creation failed - ROLLBACK everything
                    debug("❌ Sessions column creation failed: {}", str(e))
                    db.rollback()
                    raise Exception("Failed to create sessions column")
            else:
                # Migration creation failed - ROLLBACK everything
                debug("❌ Failed to create migration for field '{}'", name)
                db.rollback()
                raise Exception("Failed to create migration")
        else:
            debug("ℹ️  Field '{}' already exists in sessions table", api_name)
        
        # Step 3: Both succeeded - COMMIT everything
        db.commit()
        db.refresh(field)
        return field
        
    except Exception as e:
        # ANY error - ROLLBACK everything
        db.rollback()
        debug("❌ Transaction failed: {}", str(e))
        raise Exception("Failed to create field. Please try again.")

def get_emr_type_field(db: Session, field_id: UUID):
    return db.query(EMRTypeField).filter(EMRTypeField.id == field_id).first()

def get_all_emr_type_fields(db: Session):
    return db.query(EMRTypeField).all()

def update_emr_type_field(db: Session, field_id: UUID, name: Optional[str] = None, type: Optional[str] = None, analyzable: Optional[str] = None, api_name: Optional[str] = None, dropdown_values: Optional[str] = None, instructions: Optional[str] = None):
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
        if dropdown_values is not None:
            field.dropdown_values = dropdown_values
        if instructions is not None:
            field.instructions = instructions
        
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
                        debug("✅ Successfully created migration to rename column '{}' to '{}' in sessions table", actual_old_column_name, new_sanitized_name)
                        
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
                                debug("🎉 Successfully applied migration! Column renamed from '{}' to '{}'", actual_old_column_name, new_sanitized_name)
                                
                                # Auto-commit migration to git for sync
                                try:
                                    subprocess.run(['git', 'add', 'alembic/versions/'], cwd=os.getcwd(), capture_output=True)
                                    subprocess.run(['git', 'commit', '-m', f'Auto-commit: Rename field {old_name} to {name}'], cwd=os.getcwd(), capture_output=True)
                                    subprocess.run(['git', 'push', 'origin', 'dev'], cwd=os.getcwd(), capture_output=True)
                                    debug("✅ Migration auto-committed to git for sync")
                                except Exception as e:
                                    debug("⚠️ Could not auto-commit migration: {}", e)
                            else:
                                # Sessions column rename failed - ROLLBACK everything
                                debug("❌ Sessions column rename failed: {}", result.stderr)
                                db.rollback()
                                raise Exception("Failed to rename sessions column")
                        except Exception as e:
                            # Sessions column rename failed - ROLLBACK everything
                            debug("❌ Sessions column rename failed: {}", str(e))
                            db.rollback()
                            raise Exception("Failed to rename sessions column")
                    else:
                        # Migration creation failed - ROLLBACK everything
                        debug("❌ Failed to create migration for column rename")
                        db.rollback()
                        raise Exception("Failed to create rename migration")
            except Exception as e:
                # Column rename failed - ROLLBACK everything
                debug("❌ Column rename failed: {}", str(e))
                db.rollback()
                raise Exception("Failed to rename column")

        # Step 3: Both succeeded - COMMIT everything
        db.commit()
        db.refresh(field)
        return field
        
    except Exception as e:
        # ANY error - ROLLBACK everything
        db.rollback()
        debug("❌ Transaction failed: {}", str(e))
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

def _create_field_mapping(emr_fields, return_type="api_name"):
    """Create smart field mapping that handles various frontend field name formats"""
    field_mapping = {}
    for field in emr_fields:
        if field.api_name:
            # Normalize the field name to ensure single spaces between words
            normalized_name = ' '.join(field.name.split())  # This normalizes multiple spaces to single spaces
            
            # Decide what value to return based on parameter
            field_value = field.type if return_type == "type" else field.api_name
            
            # Store normalized name and lowercase version (don't store original with multiple spaces)
            field_mapping[normalized_name] = field_value
            field_mapping[normalized_name.lower()] = field_value
            
            # Create variations for flexible matching
            # 1. Remove spaces: "Appt Date" -> "ApptDate"
            no_spaces = normalized_name.replace(' ', '')
            field_mapping[no_spaces] = field_value
            field_mapping[no_spaces.lower()] = field_value
            
            # 2. Replace spaces with underscores: "Appt Date" -> "Appt_Date"
            with_underscores = normalized_name.replace(' ', '_')
            field_mapping[with_underscores] = field_value
            field_mapping[with_underscores.lower()] = field_value
            
            # 3. Replace spaces with dashes: "Appt Date" -> "Appt-Date"
            with_dashes = normalized_name.replace(' ', '-')
            field_mapping[with_dashes] = field_value
            field_mapping[with_dashes.lower()] = field_value
            
            # 4. CamelCase variations: "Appt Date" -> "apptDate"
            words = normalized_name.split()
            if len(words) > 1:
                camel_case = words[0].lower() + ''.join(word.capitalize() for word in words[1:])
                field_mapping[camel_case] = field_value
                field_mapping[camel_case.lower()] = field_value
            
            # 5. Handle dash variations (frontend has dashes, EMR field doesn't)
            # Remove dashes from EMR field name: "Appt-Date" -> "ApptDate"
            no_dashes = normalized_name.replace('-', '')
            field_mapping[no_dashes] = field_value
            field_mapping[no_dashes.lower()] = field_value
            
            # 6. Handle underscore variations (frontend has underscores, EMR field doesn't)
            # Remove underscores from EMR field name: "Appt_Date" -> "ApptDate"
            no_underscores = normalized_name.replace('_', '')
            field_mapping[no_underscores] = field_value
            field_mapping[no_underscores.lower()] = field_value
            
            # 7. Replace dashes with spaces: "Appt-Date" -> "Appt Date"
            dash_to_space = normalized_name.replace('-', ' ')
            field_mapping[dash_to_space] = field_value
            field_mapping[dash_to_space.lower()] = field_value
            
            # 8. Replace underscores with spaces: "Appt_Date" -> "Appt Date"
            underscore_to_space = normalized_name.replace('_', ' ')
            field_mapping[underscore_to_space] = field_value
            field_mapping[underscore_to_space.lower()] = field_value
            
            # 9. Handle extra spaces around dashes
            normalized_dash = normalized_name.replace(' - ', '-').replace(' -', '-').replace('- ', '-')
            if normalized_dash != normalized_name:
                field_mapping[normalized_dash] = field_value
                field_mapping[normalized_dash.lower()] = field_value
            
            # 10. Handle extra spaces around underscores
            normalized_underscore = normalized_name.replace(' _ ', '_').replace(' _', '_').replace('_ ', '_')
            if normalized_underscore != normalized_name:
                field_mapping[normalized_underscore] = field_value
                field_mapping[normalized_underscore.lower()] = field_value
    
    return field_mapping

def _create_field_type_mapping(emr_fields):
    """Create smart field type mapping that handles various field name formats for results"""
    return _create_field_mapping(emr_fields, return_type="type")

def _find_matching_api_name(key, field_mapping):
    """Smart function to find matching api_name with space normalization"""
    # First try exact match
    api_name = field_mapping.get(key) or field_mapping.get(key.lower())
    if api_name:
        return api_name
    
    # If no exact match, try normalizing spaces in the key
    normalized_key = ' '.join(key.split())  # Normalize multiple spaces to single spaces
    api_name = field_mapping.get(normalized_key) or field_mapping.get(normalized_key.lower())
    if api_name:
        return api_name
    
    # If still no match, try matching against all field_mapping keys with space normalization
    for field_key, field_api_name in field_mapping.items():
        normalized_field_key = ' '.join(field_key.split())  # Normalize field mapping key
        normalized_input_key = ' '.join(key.split())        # Normalize input key
        if normalized_field_key.lower() == normalized_input_key.lower():
            return field_api_name
    
    return None

# Session CRUD operations
def create_session(db: Session, user_id: UUID, **session_data):
    """Create a new session with dynamic fields - SIMPLIFIED"""
    
    # Get the EMR type name from emr_type_id
    emr_type_id = session_data.get('emr_type_id')
    if emr_type_id:
        emr_type = db.query(EmrType).filter(EmrType.id == emr_type_id).first()
        if emr_type:
            session_data['emr_name'] = emr_type.name
    
    # Get all EMR fields for smart matching
    emr_fields = db.query(EMRTypeField).all()
    
    # Create smart mapping: frontend name → api_name (handles various formats)
    field_mapping = _create_field_mapping(emr_fields)
    
    # Transform session_data keys to api_names
    transformed_data = {}
    for key, value in session_data.items():
        # Check if key is client_id, if so just copy it directly
        if key == 'client_id':
            transformed_data[key] = value
            continue
        # Try to find matching api_name with smart space handling
        api_name = _find_matching_api_name(key, field_mapping)
        if api_name:
            transformed_data[api_name] = value
        else:
            # Keep original key if no mapping found
            transformed_data[key] = value
    
    # Add user_id
    transformed_data['user_id'] = user_id
    
    # Create session using raw SQL - only save fields that exist in sessions table
    from sqlalchemy import text
    
    # Get all existing columns and their types from sessions table
    result = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sessions'"))
    columns_info = {row[0]: row[1] for row in result.fetchall()}
    existing_columns = set(columns_info.keys())
    
    # Filter to only include fields that exist in the sessions table
    valid_data = {k: v for k, v in transformed_data.items() if k in existing_columns}
    
    # Handle date/time conversion
    for key, value in valid_data.items():
        col_type = columns_info.get(key)
        if col_type in ['timestamp without time zone', 'timestamp with time zone', 'date']:
            if value == '' or value == 'None' or value is None:
                valid_data[key] = None
            elif isinstance(value, str) and value:
                # Try to parse common date formats
                try:
                    from dateutil import parser
                    parsed_date = parser.parse(value)
                    if col_type == 'date':
                        valid_data[key] = parsed_date.date()
                    else:
                        valid_data[key] = parsed_date
                except:
                    valid_data[key] = None  # Invalid date, set to None
    
    if not valid_data:
        raise Exception("No valid fields to insert")
    
    columns = ', '.join(valid_data.keys())
    placeholders = ', '.join([f':{key}' for key in valid_data.keys()])
    
    query = text(f"INSERT INTO sessions ({columns}) VALUES ({placeholders}) RETURNING *")
    result = db.execute(query, valid_data)
    
    session_data = result.fetchone()
    db.commit()
    
    # Return simple object
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return SessionResult(**dict(session_data._mapping))

def get_session(db: Session, session_id: UUID):
    """Get session by ID"""
    from sqlalchemy import text
    
    # Use raw SQL to get all columns including dynamic ones
    query = text("SELECT * FROM sessions WHERE id = :session_id")
    result = db.execute(query, {"session_id": session_id})
    session_data = result.fetchone()
    
    if not session_data:
        return None
    
    # Return simple object with all fields
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return SessionResult(**dict(session_data._mapping))

def get_sessions_by_user(db: Session, user_id: UUID):
    """Get all sessions for a specific user"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE user_id = :user_id")
    result = db.execute(query, {"user_id": user_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**dict(session_data._mapping)))
    
    return sessions

def get_all_sessions(db: Session):
    """Get all sessions (for super admin)"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions")
    result = db.execute(query)
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**dict(session_data._mapping)))
    
    return sessions

def get_sessions_by_emr_type(db: Session, emr_type_id: UUID):
    """Get all sessions for a specific EMR type"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE emr_type_id = :emr_type_id")
    result = db.execute(query, {"emr_type_id": emr_type_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**dict(session_data._mapping)))
    
    return sessions

def get_sessions_by_client(db: Session, client_id: UUID):
    """Get all sessions for a specific client"""
    from sqlalchemy import text
    
    query = text("SELECT * FROM sessions WHERE client_id = :client_id")
    result = db.execute(query, {"client_id": client_id})
    sessions_data = result.fetchall()
    
    sessions = []
    for session_data in sessions_data:
        class SessionResult:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        sessions.append(SessionResult(**dict(session_data._mapping)))
    
    return sessions

def update_session(db: Session, session_id: UUID, **session_data):
    """Update a session with dynamic fields - SIMPLIFIED"""
    from sqlalchemy import text
    
    # First check if session exists
    check_query = text("SELECT id FROM sessions WHERE id = :session_id")
    result = db.execute(check_query, {"session_id": session_id})
    if not result.fetchone():
        return None
    
    # Get all EMR fields for smart matching
    emr_fields = db.query(EMRTypeField).all()
    
    # Create smart mapping: frontend name → api_name (handles various formats)
    field_mapping = _create_field_mapping(emr_fields)
    
    # Transform session_data keys to api_names
    transformed_data = {}
    for key, value in session_data.items():
         # Check if key is client_id, if so just copy it directly
        if key == 'client_id':
            transformed_data[key] = value
            continue
        # Try to find matching api_name with smart space handling
        api_name = _find_matching_api_name(key, field_mapping)
        if api_name:
            transformed_data[api_name] = value
        else:
            # Keep original key if no mapping found
            transformed_data[key] = value
    
    # Get all existing columns and their types from sessions table
    result = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sessions'"))
    columns_info = {row[0]: row[1] for row in result.fetchall()}
    existing_columns = set(columns_info.keys())
    
    # Filter to only include fields that exist in the sessions table
    valid_data = {k: v for k, v in transformed_data.items() if k in existing_columns}
    
    # Handle date/time conversion
    for key, value in valid_data.items():
        col_type = columns_info.get(key)
        if col_type in ['timestamp without time zone', 'timestamp with time zone', 'date']:
            if value == '' or value == 'None' or value is None:
                valid_data[key] = None
            elif isinstance(value, str) and value:
                # Try to parse common date formats
                try:
                    from dateutil import parser
                    parsed_date = parser.parse(value)
                    if col_type == 'date':
                        valid_data[key] = parsed_date.date()
                    else:
                        valid_data[key] = parsed_date
                except:
                    valid_data[key] = None  # Invalid date, set to None
    
    # Build the UPDATE query
    if not valid_data:
        return get_session(db, session_id)
    
    set_clause = ', '.join([f"{key} = :{key}" for key in valid_data.keys()])
    query = text(f"UPDATE sessions SET {set_clause} WHERE id = :session_id RETURNING *")
    
    # Execute the update
    valid_data['session_id'] = session_id
    result = db.execute(query, valid_data)
    updated_session_data = result.fetchone()
    db.commit()
    
    # Return simple object
    class SessionResult:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return SessionResult(**dict(updated_session_data._mapping))

def delete_session(db: Session, session_id: UUID):
    """Delete a session"""
    from .models import Session as SessionModel
    
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        return False
    
    db.delete(session)
    db.commit()
    return True

# Manual Field CRUD operations
def create_manual_field(db: Session, name: str, emr_type_id: UUID):
    """Create a new manual field"""
    # Look up the corresponding EMR type field to get the type
    from .models import EMRTypeField
    emr_field = db.query(EMRTypeField).filter(
        EMRTypeField.name == name
    ).first()
    
    # Get the type from the EMR type field, or default to "text"
    field_type = emr_field.type if emr_field else "text"
    
    manual_field = ManualField(name=name, emr_type_id=emr_type_id, type=field_type)
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
        # If name changed, also update the type by looking up the new field
        from .models import EMRTypeField
        emr_field = db.query(EMRTypeField).filter(
            EMRTypeField.name == name
        ).first()
        
        if emr_field:
            manual_field.type = emr_field.type

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

# Coping Skills CRUD operations
def create_coping_skill(db: Session, short_description: str, long_description: Optional[str] = None):
    """Create a new coping skill"""
    coping_skill = CopingSkill(short_description=short_description, long_description=long_description)
    db.add(coping_skill)
    db.commit()
    db.refresh(coping_skill)
    return coping_skill

def get_coping_skill(db: Session, coping_skill_id: UUID):
    """Get coping skill by ID"""
    return db.query(CopingSkill).filter(CopingSkill.id == coping_skill_id).first()

def get_all_coping_skills(db: Session):
    """Get all coping skills"""
    return db.query(CopingSkill).all()

def update_coping_skill(db: Session, coping_skill_id: UUID, short_description: Optional[str] = None, long_description: Optional[str] = None):
    """Update a coping skill"""
    coping_skill = get_coping_skill(db, coping_skill_id)
    if not coping_skill:
        return None

    if short_description is not None:
        coping_skill.short_description = short_description
    if long_description is not None:
        coping_skill.long_description = long_description

    db.commit()
    db.refresh(coping_skill)
    return coping_skill

def delete_coping_skill(db: Session, coping_skill_id: UUID):
    """Delete a coping skill"""
    coping_skill = get_coping_skill(db, coping_skill_id)
    if not coping_skill:
        return False

    db.delete(coping_skill)
    db.commit()
    return True

# Clinical Specialties CRUD operations
def create_clinical_specialty(db: Session, short_description: str, long_description: Optional[str] = None):
    """Create a new clinical specialty"""
    clinical_specialty = ClinicalSpecialty(short_description=short_description, long_description=long_description)
    db.add(clinical_specialty)
    db.commit()
    db.refresh(clinical_specialty)
    return clinical_specialty

def get_clinical_specialty(db: Session, clinical_specialty_id: UUID):
    """Get clinical specialty by ID"""
    return db.query(ClinicalSpecialty).filter(ClinicalSpecialty.id == clinical_specialty_id).first()

def get_all_clinical_specialties(db: Session):
    """Get all clinical specialties"""
    return db.query(ClinicalSpecialty).all()

def update_clinical_specialty(db: Session, clinical_specialty_id: UUID, short_description: Optional[str] = None, long_description: Optional[str] = None):
    """Update a clinical specialty"""
    clinical_specialty = get_clinical_specialty(db, clinical_specialty_id)
    if not clinical_specialty:
        return None

    if short_description is not None:
        clinical_specialty.short_description = short_description
    if long_description is not None:
        clinical_specialty.long_description = long_description

    db.commit()
    db.refresh(clinical_specialty)
    return clinical_specialty

def delete_clinical_specialty(db: Session, clinical_specialty_id: UUID):
    """Delete a clinical specialty"""
    clinical_specialty = get_clinical_specialty(db, clinical_specialty_id)
    if not clinical_specialty:
        return False

    db.delete(clinical_specialty)
    db.commit()
    return True

# Documentation Methods CRUD operations
def create_documentation_method(db: Session, name: str, session_instructions: Optional[str] = None):
    """Create a new documentation method"""
    documentation_method = DocumentationMethod(name=name, session_instructions=session_instructions)
    db.add(documentation_method)
    db.commit()
    db.refresh(documentation_method)
    return documentation_method

def get_documentation_method(db: Session, documentation_method_id: UUID):
    """Get documentation method by ID"""
    return db.query(DocumentationMethod).filter(DocumentationMethod.id == documentation_method_id).first()

def get_all_documentation_methods(db: Session):
    """Get all documentation methods"""
    return db.query(DocumentationMethod).all()

def update_documentation_method(db: Session, documentation_method_id: UUID, name: Optional[str] = None, session_instructions: Optional[str] = None):
    """Update a documentation method"""
    documentation_method = get_documentation_method(db, documentation_method_id)
    if not documentation_method:
        return None

    if name is not None:
        documentation_method.name = name
    if session_instructions is not None:
        documentation_method.session_instructions = session_instructions

    db.commit()
    db.refresh(documentation_method)
    return documentation_method

def delete_documentation_method(db: Session, documentation_method_id: UUID):
    """Delete a documentation method"""
    documentation_method = get_documentation_method(db, documentation_method_id)
    if not documentation_method:
        return False

    db.delete(documentation_method)
    db.commit()
    return True

# Modality CRUD operations
def create_modality(db: Session, name: str, short_term: Optional[str] = None, description: Optional[str] = None, modality_setting: Optional[str] = None):
    """Create a new modality"""
    modality = Modality(name=name, short_term=short_term, description=description, modality_setting=modality_setting)
    db.add(modality)
    db.commit()
    db.refresh(modality)
    return modality

def get_modality(db: Session, modality_id: UUID):
    """Get modality by ID"""
    return db.query(Modality).filter(Modality.id == modality_id).first()

def get_all_modalities(db: Session):
    """Get all modalities"""
    return db.query(Modality).all()

def update_modality(db: Session, modality_id: UUID, name: Optional[str] = None, short_term: Optional[str] = None, description: Optional[str] = None, modality_setting: Optional[str] = None):
    """Update a modality"""
    modality = get_modality(db, modality_id)
    if not modality:
        return None

    if name is not None:
        modality.name = name
    if short_term is not None:
        modality.short_term = short_term
    if description is not None:
        modality.description = description
    if modality_setting is not None:
        modality.modality_setting = modality_setting

    db.commit()
    db.refresh(modality)
    return modality

def delete_modality(db: Session, modality_id: UUID):
    """Delete a modality"""
    modality = get_modality(db, modality_id)
    if not modality:
        return False

    db.delete(modality)
    db.commit()
    return True

# Modality Step CRUD operations
def create_modality_step(db: Session, modality_id: UUID, name: str):
    """Create a new modality step"""
    modality_step = ModalityStep(modality_id=modality_id, name=name)
    db.add(modality_step)
    db.commit()
    db.refresh(modality_step)
    return modality_step

def get_modality_step(db: Session, modality_step_id: UUID):
    """Get modality step by ID"""
    return db.query(ModalityStep).filter(ModalityStep.id == modality_step_id).first()

def get_all_modality_steps(db: Session):
    """Get all modality steps with modality names"""
    steps = db.query(ModalityStep).all()
    result = []
    for step in steps:
        modality = db.query(Modality).filter(Modality.id == step.modality_id).first()
        step_dict = step.__dict__.copy()
        step_dict['modality_name'] = modality.name if modality else None
        result.append(step_dict)
    return result

def update_modality_step(db: Session, modality_step_id: UUID, modality_id: Optional[UUID] = None, name: Optional[str] = None):
    """Update a modality step"""
    modality_step = get_modality_step(db, modality_step_id)
    if not modality_step:
        return None

    if modality_id is not None:
        modality_step.modality_id = modality_id
    if name is not None:
        modality_step.name = name

    db.commit()
    db.refresh(modality_step)
    return modality_step

def delete_modality_step(db: Session, modality_step_id: UUID):
    """Delete a modality step"""
    modality_step = get_modality_step(db, modality_step_id)
    if not modality_step:
        return False

    db.delete(modality_step)
    db.commit()
    return True

# Activity CRUD operations
def create_activity(db: Session, name: str, short_term: Optional[str] = None, description: Optional[str] = None, activity_setting: Optional[str] = None):
    """Create a new activity"""
    activity = Activity(name=name, short_term=short_term, description=description, activity_setting=activity_setting)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity

def get_activity(db: Session, activity_id: UUID):
    """Get activity by ID"""
    return db.query(Activity).filter(Activity.id == activity_id).first()

def get_all_activities(db: Session):
    """Get all activities"""
    return db.query(Activity).all()

def update_activity(db: Session, activity_id: UUID, name: Optional[str] = None, short_term: Optional[str] = None, description: Optional[str] = None, activity_setting: Optional[str] = None):
    """Update an activity"""
    activity = get_activity(db, activity_id)
    if not activity:
        return None

    if name is not None:
        activity.name = name
    if short_term is not None:
        activity.short_term = short_term
    if description is not None:
        activity.description = description
    if activity_setting is not None:
        activity.activity_setting = activity_setting

    db.commit()
    db.refresh(activity)
    return activity

def delete_activity(db: Session, activity_id: UUID):
    """Delete an activity"""
    activity = get_activity(db, activity_id)
    if not activity:
        return False

    db.delete(activity)
    db.commit()
    return True

# Sub-Activity CRUD operations
def create_sub_activity(db: Session, activity_id: UUID, name: str):
    """Create a new sub-activity"""
    sub_activity = SubActivity(activity_id=activity_id, name=name)
    db.add(sub_activity)
    db.commit()
    db.refresh(sub_activity)
    return sub_activity

def get_sub_activity(db: Session, sub_activity_id: UUID):
    """Get sub-activity by ID"""
    return db.query(SubActivity).filter(SubActivity.id == sub_activity_id).first()

def get_all_sub_activities(db: Session):
    """Get all sub-activities with activity names"""
    sub_activities = db.query(SubActivity).all()
    result = []
    for sub_activity in sub_activities:
        activity = db.query(Activity).filter(Activity.id == sub_activity.activity_id).first()
        sub_activity_dict = sub_activity.__dict__.copy()
        sub_activity_dict['activity_name'] = activity.name if activity else None
        result.append(sub_activity_dict)
    return result

def update_sub_activity(db: Session, sub_activity_id: UUID, activity_id: Optional[UUID] = None, name: Optional[str] = None):
    """Update a sub-activity"""
    sub_activity = get_sub_activity(db, sub_activity_id)
    if not sub_activity:
        return None

    if activity_id is not None:
        sub_activity.activity_id = activity_id
    if name is not None:
        sub_activity.name = name

    db.commit()
    db.refresh(sub_activity)
    return sub_activity

def delete_sub_activity(db: Session, sub_activity_id: UUID):
    """Delete a sub-activity"""
    sub_activity = get_sub_activity(db, sub_activity_id)
    if not sub_activity:
        return False

    db.delete(sub_activity)
    db.commit()
    return True

# User Update with New Fields
def get_user_emr_documentation_pairs(db: Session, user_id: UUID):
    """Get user's EMR documentation pairs with names"""
    pairs = db.query(UserEMRDocumentationPair).filter(UserEMRDocumentationPair.user_id == user_id).all()
    result = []
    for pair in pairs:
        emr_type = db.query(EmrType).filter(EmrType.id == pair.emr_type_id).first()
        doc_method = db.query(DocumentationMethod).filter(DocumentationMethod.id == pair.documentation_method_id).first()
        result.append({
            'id': pair.id,
            'emr_type_id': pair.emr_type_id,
            'emr_type_name': emr_type.name if emr_type else None,
            'documentation_method_id': pair.documentation_method_id,
            'documentation_method_name': doc_method.name if doc_method else None,
            'created_at': pair.created_at
        })
    return result

def update_user_emr_documentation_pairs(db: Session, user_id: UUID, pairs_data: List[dict]):
    """Update user's EMR documentation pairs"""
    # Delete existing pairs
    db.query(UserEMRDocumentationPair).filter(UserEMRDocumentationPair.user_id == user_id).delete()
    db.flush()
    
    # Add new pairs
    if pairs_data:
        for pair_data in pairs_data:
            pair = UserEMRDocumentationPair(
                user_id=user_id,
                emr_type_id=pair_data['emr_type_id'],
                documentation_method_id=pair_data['documentation_method_id']
            )
            db.add(pair)
    
    db.commit()

def update_company_emr_documentation_pairs(db: Session, company_id: UUID, pairs_data: List[dict]):
    """Update EMR documentation pairs for ALL users in a company"""
    # Get all users in the company
    company_users = db.query(User).filter(User.company_id == company_id).all()
    
    for user in company_users:
        # Delete existing pairs for this user
        db.query(UserEMRDocumentationPair).filter(UserEMRDocumentationPair.user_id == user.id).delete()
        db.flush()
        
        # Add new pairs for this user
        if pairs_data:
            for pair_data in pairs_data:
                pair = UserEMRDocumentationPair(
                    user_id=user.id,
                    emr_type_id=pair_data['emr_type_id'],
                    documentation_method_id=pair_data['documentation_method_id']
                )
                db.add(pair)
    
    db.commit()
    return len(company_users)  # Return number of users updated

def update_user_with_relations(db: Session, user_id: UUID, current_user_role: int = None, **update_data):
    """Update user and handle junction table relationships"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None, {}
    
    # Update basic user fields
    for field, value in update_data.items():
        if field in ['coping_skills', 'clinical_specialties', 'type_writing', 'emr_type_documentation_pairs']:
            continue  # Handle these separately
        if hasattr(user, field) and value is not None:
            setattr(user, field, value)
    
    # Handle new pairs table
    update_info = {}
    if 'emr_type_documentation_pairs' in update_data:
        # Check if current user is admin (role 1) or super admin (role 3)
        if current_user_role in [1, 3]:
            # Update ALL users in the same company
            users_updated = update_company_emr_documentation_pairs(db, user.company_id, update_data['emr_type_documentation_pairs'])
            update_info = {
                'company_wide_update': True,
                'users_updated': users_updated,
                'message': f'EMR documentation pairs updated for {users_updated} users in your company'
            }
        else:
            # Update only the specific user
            update_user_emr_documentation_pairs(db, user_id, update_data['emr_type_documentation_pairs'])
            update_info = {
                'company_wide_update': False,
                'users_updated': 1,
                'message': 'EMR documentation pairs updated for this user only'
            }
    
    # Old junction table logic removed - now using pairs table only
    
    if 'coping_skills' in update_data:
        # Delete existing relationships
        db.query(UserCopingSkill).filter(UserCopingSkill.user_id == user_id).delete()
        db.flush()  # Ensure delete is committed before insert
        # Add new relationships
        if update_data['coping_skills']:
            for coping_skill_id in update_data['coping_skills']:
                junction = UserCopingSkill(user_id=user_id, coping_skill_id=coping_skill_id)
                db.add(junction)
    
    if 'clinical_specialties' in update_data:
        # Delete existing relationships
        db.query(UserClinicalSpecialty).filter(UserClinicalSpecialty.user_id == user_id).delete()
        db.flush()  # Ensure delete is committed before insert
        # Add new relationships
        if update_data['clinical_specialties']:
            for clinical_specialty_id in update_data['clinical_specialties']:
                junction = UserClinicalSpecialty(user_id=user_id, clinical_specialty_id=clinical_specialty_id)
                db.add(junction)
    
    if 'type_writing' in update_data:
        # SQLAlchemy handles PostgreSQL array conversion automatically
        user.type_writing = update_data['type_writing']
    
    db.commit()
    db.refresh(user)
    return user, update_info 