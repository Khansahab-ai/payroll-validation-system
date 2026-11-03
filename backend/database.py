
from sqlmodel import SQLModel, Session, create_engine

# SQLite database
DATABASE_URL = "sqlite:///./payroll.db"

# Create database engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Database session dependency for FastAPI
def get_session():
    with Session(engine) as session:
        yield session


# Create all database tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
