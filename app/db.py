from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Corrected connection string with password 'noteddev@1234' encoded as 'noteddev%401234'
DATABASE_URL = "postgresql+psycopg2://devuser:noteddev%401234@3.149.182.148:5432/noted_dev"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() 