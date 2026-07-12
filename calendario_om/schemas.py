from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class EventTypeCreate(BaseModel):
    name: str
    color: str  # formato hex, ex: "#3788d8"


class EventTypeOut(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


class EventCreate(BaseModel):
    title: str
    location: Optional[str] = None
    responsible: Optional[str] = None
    event_type_id: int
    start_date: date
    end_date: date
    observations: Optional[str] = None
    author_name: str  # quem está lançando o evento


class EventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    responsible: Optional[str] = None
    event_type_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    observations: Optional[str] = None
    status_override: Optional[str] = None  # "adiado" | "cancelado" | "concluido_antecipado" | "" (limpa override)
    editor_name: str  # quem está editando


class EventOut(BaseModel):
    id: int
    title: str
    location: Optional[str]
    responsible: Optional[str]
    event_type_id: int
    start_date: date
    end_date: date
    status_override: Optional[str]
    observations: Optional[str]
    created_by: str
    created_at: datetime
    updated_by: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
