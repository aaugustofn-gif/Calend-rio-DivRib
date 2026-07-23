from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class LoginRequest(BaseModel):
    nip: str
    senha: str


class TrocarSenhaRequest(BaseModel):
    nova_senha: str
    confirmar_senha: str


class UsuarioCreate(BaseModel):
    nome: str
    nip: str
    setor: Optional[str] = None
    senha_inicial: str
    is_admin: bool = False


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    setor: Optional[str] = None
    is_admin: Optional[bool] = None
    nova_senha: Optional[str] = None  # se preenchido, reseta a senha (e marca para trocar no próximo login)


class UsuarioOut(BaseModel):
    id: int
    nome: str
    nip: str
    setor: Optional[str]
    is_admin: bool
    precisa_trocar_senha: bool

    class Config:
        from_attributes = True


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


class EventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    responsible: Optional[str] = None
    event_type_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    observations: Optional[str] = None
    status_override: Optional[str] = None  # "adiado" | "cancelado" | "concluido_antecipado" | "" (limpa override)


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
