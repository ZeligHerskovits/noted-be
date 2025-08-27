"""
Migration utilities for automatically handling database schema changes
"""
import os
import subprocess
from pathlib import Path
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

class AutoMigrationManager:
    """Manages automatic database migrations for dynamic field creation"""
    
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.getcwd()
        self.alembic_dir = os.path.join(self.project_root, "alembic")
        self.versions_dir = os.path.join(self.alembic_dir, "versions")
        
    def create_field_migration(self, field_name: str, field_type: str = "TEXT") -> bool:
        """
        Creates an Alembic migration file to add a new field to the sessions table
        
        Args:
            field_name: Name of the field to add
            field_type: SQL data type (default: TEXT)
            
        Returns:
            bool: True if migration file was created successfully, False otherwise
        """
        try:
            # Generate migration file
            migration_file = self._generate_migration_file(field_name, field_type)
            if not migration_file:
                logger.error(f"Failed to generate migration file for field: {field_name}")
                return False
                
            logger.info(f"✅ Migration file created: {migration_file}")
            logger.info(f"📝 To apply the migration, run: alembic upgrade head")
            return True
                
        except Exception as e:
            logger.error(f"Error creating migration for field {field_name}: {str(e)}")
            return False

    def rename_column_migration(self, old_column_name: str, new_column_name: str, table_name: str = "sessions") -> bool:
        """
        Creates an Alembic migration file to rename a column in the specified table
        
        Args:
            old_column_name: Current name of the column
            new_column_name: New name for the column
            table_name: Name of the table (default: sessions)
            
        Returns:
            bool: True if migration file was created successfully, False otherwise
        """
        try:
            # Safety check: prevent self-loops
            current_head = self._get_current_head()
            if current_head == 'HEAD_PLACEHOLDER' or not current_head:
                print("⚠️  Invalid current head, using base migration")
                current_head = "3c7694b9a164"
            
            print(f"🔍 Creating migration from current head: {current_head}")
            
            # Generate migration file for column rename
            migration_file = self._generate_rename_migration_file(old_column_name, new_column_name, table_name)
            if not migration_file:
                logger.error(f"Failed to generate rename migration file for column: {old_column_name} -> {new_column_name}")
                return False
                
            logger.info(f"✅ Rename migration file created: {migration_file}")
            logger.info(f"📝 To apply the migration, run: alembic upgrade head")
            return True
                
        except Exception as e:
            logger.error(f"Error creating rename migration for column {old_column_name} -> {new_column_name}: {str(e)}")
            return False
    
    def _generate_migration_file(self, field_name: str, field_type: str) -> Optional[str]:
        """Generates an Alembic migration file for adding a field to sessions table"""
        try:
            # Get the current head revision
            current_head = self._get_current_head()
            
            # Create migration content
            migration_content = self._create_migration_content(field_name, field_type, current_head)
            
            # Generate a short revision ID and filename
            revision_id = self._generate_short_revision_id(f"add_{field_name}", "sessions")
            filename = f"{revision_id}.py"
            filepath = os.path.join(self.versions_dir, filename)
            
            # Write migration file
            with open(filepath, 'w') as f:
                f.write(migration_content)
                
            logger.info(f"Generated migration file: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating migration file: {str(e)}")
            return None

    def _generate_rename_migration_file(self, old_column_name: str, new_column_name: str, table_name: str) -> Optional[str]:
        """Generates an Alembic migration file for renaming a column"""
        try:
            # Get the current head revision
            current_head = self._get_current_head()
            
            # Create migration content for column rename
            migration_content = self._create_rename_migration_content(old_column_name, new_column_name, table_name, current_head)
            
            # Generate a short revision ID and filename
            revision_id = self._generate_short_revision_id(f"rename_{old_column_name}_to_{new_column_name}", table_name)
            filename = f"{revision_id}.py"
            filepath = os.path.join(self.versions_dir, filename)
            
            # Write migration file
            with open(filepath, 'w') as f:
                f.write(migration_content)
                
            logger.info(f"Generated rename migration file: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating rename migration file: {str(e)}")
            return None
    
    def _get_current_head(self) -> str:
        """Gets the current head revision from Alembic - BULLETPROOF VERSION"""
        try:
            # Method 1: Get from database directly (most reliable)
            from .db import engine
            from sqlalchemy import text
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.fetchone()
                if row and row[0] and row[0] != 'HEAD_PLACEHOLDER':
                    print(f"🔍 Database current revision: {row[0]}")
                    return row[0]
            
            # Method 2: Parse migration files to find the latest valid revision
            valid_migrations = []
            for filename in os.listdir(self.versions_dir):
                if filename.endswith('.py') and not filename.startswith('__'):
                    filepath = os.path.join(self.versions_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            content = f.read()
                            
                            # Extract revision ID
                            revision = None
                            down_revision = None
                            
                            for line in content.split('\n'):
                                if line.startswith("revision = '") and 'HEAD_PLACEHOLDER' not in line:
                                    revision = line.split("'")[1]
                                elif line.startswith("down_revision = '") and 'HEAD_PLACEHOLDER' not in line:
                                    down_revision = line.split("'")[1]
                            
                            # Only add if we have both revision and down_revision
                            if revision and down_revision and revision != down_revision:
                                # Extract timestamp for sorting
                                if '_' in filename:
                                    parts = filename.split('_')
                                    timestamp = parts[-1].replace('.py', '')
                                    valid_migrations.append((timestamp, revision, down_revision))
                    except Exception as e:
                        print(f"⚠️  Skipping file {filename}: {e}")
                        continue
            
            # Find the latest migration (the one that's not referenced as down_revision by any other)
            if valid_migrations:
                valid_migrations.sort(reverse=True)  # Most recent first
                
                # Get all down_revisions
                all_down_revisions = set(mig[2] for mig in valid_migrations)
                
                # Find the revision that's not a down_revision (the head)
                for timestamp, revision, down_revision in valid_migrations:
                    if revision not in all_down_revisions:
                        print(f"🔍 Found head revision: {revision}")
                        return revision
                
                # Fallback: return the most recent revision
                latest_revision = valid_migrations[0][1]
                print(f"🔍 Using latest revision as fallback: {latest_revision}")
                return latest_revision
            
            # Method 3: Final fallback to base migration
            print("🔍 Using base migration as final fallback")
            return "3c7694b9a164"
            
        except Exception as e:
            print(f"❌ Error in _get_current_head: {str(e)}")
            print("🔍 Using base migration as error fallback")
            return "3c7694b9a164"
    
    def _create_migration_content(self, field_name: str, field_type: str, down_revision: str) -> str:
        """Creates the content for the Alembic migration file"""
        # Sanitize field name for SQL
        safe_field_name = self.sanitize_field_name(field_name)
        revision_id = self._generate_short_revision_id(f"add_{field_name}", "sessions")
        
        # Map field types to proper SQLAlchemy column types
        type_mapping = {
            'TEXT': 'Text',
            'STRING': 'String',
            'INTEGER': 'Integer',
            'BOOLEAN': 'Boolean',
            'DATETIME': 'DateTime',
            'DATE': 'Date',
            'FLOAT': 'Float',
            'DECIMAL': 'Numeric',
            'JSON': 'JSON',
            'JSONB': 'JSONB'
        }
        
        # Get the proper SQLAlchemy type with correct casing
        sqlalchemy_type = type_mapping.get(field_type.upper(), 'Text')
        
        migration_content = f'''"""Auto-generated migration: Add {field_name} field to sessions table

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {self._get_timestamp()}

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add {field_name} field to sessions table"""
    op.add_column('sessions', sa.Column('{safe_field_name}', sa.{sqlalchemy_type}(), nullable=True))

def downgrade() -> None:
    """Remove {field_name} field from sessions table"""
    op.drop_column('sessions', '{safe_field_name}')
'''
        return migration_content

    def _create_rename_migration_content(self, old_column_name: str, new_column_name: str, table_name: str, down_revision: str) -> str:
        """Creates the content for the Alembic column rename migration file"""
        timestamp = self._get_timestamp()
        revision_id = self._generate_short_revision_id(f"rename_{old_column_name}_to_{new_column_name}", table_name)
        
        migration_content = f'''"""Auto-generated migration: Rename column {old_column_name} to {new_column_name} in {table_name} table

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {timestamp}

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column {old_column_name} to {new_column_name} in {table_name} table"""
    op.alter_column('{table_name}', '{old_column_name}', new_column_name='{new_column_name}')

def downgrade() -> None:
    """Rename column {new_column_name} back to {old_column_name} in {table_name} table"""
    op.alter_column('{table_name}', '{new_column_name}', new_column_name='{old_column_name}')
'''
        return migration_content
    
    def sanitize_field_name(self, field_name: str) -> str:
        """Sanitizes field name for safe use in SQL and file names"""
        
        # Special case: client id fields should use double underscore to avoid conflict with existing client_id
        field_name_lower = field_name.lower()
        if field_name_lower in ['clientid', 'client id', 'clientid', 'client id', 'client id', 'client id']:
            return 'client__id'  # Double underscore to avoid conflict with existing client_id field
        
        # Replace spaces and special characters with underscores
        sanitized = field_name.replace(' ', '_').replace('-', '_').replace('.', '_')
        # Remove any other non-alphanumeric characters except underscores
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
        # Ensure it starts with a letter or underscore
        if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
            sanitized = 'f_' + sanitized
        return sanitized.lower()
    
    def _sanitize_field_name(self, field_name: str) -> str:
        """Legacy method - use sanitize_field_name instead"""
        return self.sanitize_field_name(field_name)
    
    def _get_timestamp(self) -> str:
        """Generates a timestamp string for unique identifiers"""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _generate_short_revision_id(self, operation: str, table: str) -> str:
        """Generates a short revision ID to avoid StringDataRightTruncation errors"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create a short, descriptive revision ID with timestamp to ensure uniqueness
        short_op = operation.replace('_', '')[:8]  # First 8 chars of operation
        short_table = table[:6]  # First 6 chars of table name
        short_timestamp = timestamp[-6:]  # Last 6 chars of timestamp (MMSS)
        
        return f"{short_op}_{short_table}_{short_timestamp}"
    
    def check_field_exists(self, db: Session, field_name: str) -> bool:
        """Checks if a field already exists in the sessions table"""
        try:
            # Sanitize field name
            safe_field_name = self._sanitize_field_name(field_name)
            
            # Query to check if column exists
            query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'sessions' 
                AND column_name = :field_name
            """)
            
            result = db.execute(query, {"field_name": safe_field_name})
            return result.fetchone() is not None
            
        except Exception as e:
            logger.error(f"Error checking if field exists: {str(e)}")
            return False
    
    def find_actual_column_name(self, db: Session, old_field_name: str, old_api_name: str) -> str:
        """Finds the actual column name in the sessions table that corresponds to a field"""
        try:
            # Get all columns that might match
            possible_names = [
                old_api_name,
                self.sanitize_field_name(old_field_name),
                old_field_name.lower().replace(' ', '_'),
                old_field_name.lower().replace(' ', ''),
                old_field_name.lower().replace(' ', '_').replace('-', '_'),
                old_field_name.lower().replace(' ', '').replace('-', '')
            ]
            
            # Remove duplicates while preserving order
            possible_names = list(dict.fromkeys([name for name in possible_names if name]))
            
            # Check which one actually exists
            for name in possible_names:
                if self.check_field_exists(db, name):
                    print(f"🔍 Found actual column: '{name}' for field '{old_field_name}'")
                    return name
            
            # If none found, try to get all columns and find the closest match
            print(f"⚠️  No exact match found for '{old_field_name}', searching for similar columns...")
            all_columns = self.get_all_session_columns(db)
            for col in all_columns:
                if old_field_name.lower() in col.lower() or col.lower() in old_field_name.lower():
                    print(f"🔍 Found similar column: '{col}' for field '{old_field_name}'")
                    return col
            
            # Last resort: return the sanitized version
            fallback = self.sanitize_field_name(old_field_name)
            print(f"⚠️  Using fallback column name: '{fallback}' for field '{old_field_name}'")
            return fallback
            
        except Exception as e:
            logger.error(f"Error finding actual column name: {str(e)}")
            return self.sanitize_field_name(old_field_name)
    
    def get_all_session_columns(self, db: Session) -> list:
        """Gets all column names from the sessions table"""
        try:
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'sessions' 
                ORDER BY column_name
            """))
            return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Error getting session columns: {str(e)}")
            return []

# Global instance
migration_manager = AutoMigrationManager() 