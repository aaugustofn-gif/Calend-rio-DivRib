from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    nip = Column(String(8), unique=True, nullable=False, index=True)
    setor = Column(String(150), nullable=True)
    senha_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    precisa_trocar_senha = Column(Boolean, default=True, nullable=False)
    ics_token = Column(String(64), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventType(Base):
    __tablename__ = "event_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    color = Column(String(7), nullable=False, default="#3788d8")  # hex, ex: #3788d8

    events = relationship("Event", back_populates="event_type")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    location = Column(String(200), nullable=True)
    responsible = Column(String(150), nullable=True)  # responsável pelo evento
    event_type_id = Column(Integer, ForeignKey("event_types.id"), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Ajuste manual de status: None = automático (calculado por data)
    # Valores possíveis: "adiado", "cancelado", "concluido_antecipado"
    status_override = Column(String(30), nullable=True, default=None)

    observations = Column(Text, nullable=True)

    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    updated_by = Column(String(150), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    event_type = relationship("EventType", back_populates="events")
