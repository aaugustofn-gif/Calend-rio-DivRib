import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Formato esperado da variável de ambiente DATABASE_URL (TiDB Cloud):
# mysql+pymysql://usuario:senha@host:4000/nome_do_banco?ssl_verify_cert=true&ssl_verify_identity=true
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Variável de ambiente DATABASE_URL não configurada.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
