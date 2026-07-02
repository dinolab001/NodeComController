from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.engine import URL
import json
from app.services.kv_storage import StorageService

def get_engine():
    creds_json = StorageService.get_data("supabase_creds")
    if not creds_json:
        raise Exception("Database credentials not found in KV storage.")
    creds = json.loads(creds_json)

    db_url = URL.create(
        drivername="postgresql+psycopg2",
        username=creds.get("db_user"),
        password=creds.get("db_password"),
        host=creds.get("db_host"),
        port=creds.get("db_port", 5432),
        database=creds.get("db_name", "postgres"),
    )
    return create_engine(str(db_url))


def get_session():
    engine = get_engine()
    with Session(engine) as session:
        yield session
