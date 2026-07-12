from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from datetime import date, datetime, timedelta
import io

from database import Base, engine, get_db
import models
import schemas

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Calendário OM")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

STATUS_LABELS = {
    "futuro": "Futuro",
    "em_andamento": "Em andamento",
    "finalizado": "Finalizado",
    "adiado": "Adiado",
    "cancelado": "Cancelado",
    "concluido_antecipado": "Concluído antecipadamente",
}


def compute_status(evento: models.Event) -> str:
    if evento.status_override:
        return evento.status_override
    hoje = date.today()
    if evento.end_date < hoje:
        return "finalizado"
    if evento.start_date <= hoje <= evento.end_date:
        return "em_andamento"
    return "futuro"


# ---------- Páginas ----------

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- Tipos de evento ----------

@app.get("/api/event-types", response_model=list[schemas.EventTypeOut])
def list_event_types(db: Session = Depends(get_db)):
    return db.query(models.EventType).order_by(models.EventType.name).all()


@app.post("/api/event-types", response_model=schemas.EventTypeOut)
def create_event_type(payload: schemas.EventTypeCreate, db: Session = Depends(get_db)):
    existente = db.query(models.EventType).filter(models.EventType.name == payload.name).first()
    if existente:
        raise HTTPException(400, "Já existe um tipo de evento com esse nome.")
    novo = models.EventType(name=payload.name, color=payload.color)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@app.put("/api/event-types/{type_id}", response_model=schemas.EventTypeOut)
def update_event_type(type_id: int, payload: schemas.EventTypeCreate, db: Session = Depends(get_db)):
    tipo = db.query(models.EventType).get(type_id)
    if not tipo:
        raise HTTPException(404, "Tipo de evento não encontrado.")
    tipo.name = payload.name
    tipo.color = payload.color
    db.commit()
    db.refresh(tipo)
    return tipo


@app.delete("/api/event-types/{type_id}")
def delete_event_type(type_id: int, db: Session = Depends(get_db)):
    em_uso = db.query(models.Event).filter(models.Event.event_type_id == type_id).first()
    if em_uso:
        raise HTTPException(400, "Não é possível excluir: existem eventos usando esse tipo.")
    tipo = db.query(models.EventType).get(type_id)
    if not tipo:
        raise HTTPException(404, "Tipo de evento não encontrado.")
    db.delete(tipo)
    db.commit()
    return {"ok": True}


# ---------- Eventos ----------

@app.get("/api/events")
def list_events(db: Session = Depends(get_db)):
    eventos = db.query(models.Event).all()
    resultado = []
    for e in eventos:
        status = compute_status(e)
        resultado.append({
            "id": e.id,
            "title": e.title,
            "start": e.start_date.isoformat(),
            # FullCalendar trata "end" como exclusivo, por isso soma 1 dia
            "end": (e.end_date + timedelta(days=1)).isoformat(),
            "color": e.event_type.color,
            "extendedProps": {
                "location": e.location,
                "responsible": e.responsible,
                "event_type_id": e.event_type_id,
                "event_type_name": e.event_type.name,
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "observations": e.observations,
                "created_by": e.created_by,
                "created_at": e.created_at.strftime("%d/%m/%Y %H:%M") if e.created_at else None,
                "updated_by": e.updated_by,
                "updated_at": e.updated_at.strftime("%d/%m/%Y %H:%M") if e.updated_at else None,
                "start_date": e.start_date.isoformat(),
                "end_date": e.end_date.isoformat(),
            }
        })
    return resultado


@app.post("/api/events", response_model=schemas.EventOut)
def create_event(payload: schemas.EventCreate, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "A data final não pode ser anterior à data inicial.")
    tipo = db.query(models.EventType).get(payload.event_type_id)
    if not tipo:
        raise HTTPException(400, "Tipo de evento inválido.")
    novo = models.Event(
        title=payload.title,
        location=payload.location,
        responsible=payload.responsible,
        event_type_id=payload.event_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        observations=payload.observations,
        created_by=payload.author_name,
        created_at=datetime.utcnow(),
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@app.put("/api/events/{event_id}", response_model=schemas.EventOut)
def update_event(event_id: int, payload: schemas.EventUpdate, db: Session = Depends(get_db)):
    evento = db.query(models.Event).get(event_id)
    if not evento:
        raise HTTPException(404, "Evento não encontrado.")

    dados = payload.dict(exclude_unset=True, exclude={"editor_name"})
    for campo, valor in dados.items():
        if campo == "status_override" and valor == "":
            valor = None
        setattr(evento, campo, valor)

    if evento.end_date < evento.start_date:
        raise HTTPException(400, "A data final não pode ser anterior à data inicial.")

    evento.updated_by = payload.editor_name
    evento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(evento)
    return evento


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    evento = db.query(models.Event).get(event_id)
    if not evento:
        raise HTTPException(404, "Evento não encontrado.")
    db.delete(evento)
    db.commit()
    return {"ok": True}


# ---------- Exportação em PDF ----------

@app.get("/api/export/pdf")
def export_pdf(start: date, end: date, db: Session = Depends(get_db)):
    if end < start:
        raise HTTPException(400, "A data final não pode ser anterior à data inicial.")

    eventos = (
        db.query(models.Event)
        .filter(models.Event.start_date <= end, models.Event.end_date >= start)
        .order_by(models.Event.start_date)
        .all()
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm
    )
    styles = getSampleStyleSheet()
    elementos = []

    titulo = f"Calendário de Atividades — {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    elementos.append(Paragraph(titulo, styles["Title"]))
    elementos.append(Spacer(1, 0.5 * cm))

    dados_tabela = [["Período", "Evento", "Tipo", "Local", "Responsável", "Status", "Observações"]]
    cores_linhas = []

    for e in eventos:
        status = compute_status(e)
        periodo = f"{e.start_date.strftime('%d/%m')} a {e.end_date.strftime('%d/%m')}"
        dados_tabela.append([
            periodo,
            e.title,
            e.event_type.name,
            e.location or "-",
            e.responsible or "-",
            STATUS_LABELS.get(status, status),
            e.observations or "-",
        ])
        cores_linhas.append(e.event_type.color)

    if len(dados_tabela) == 1:
        elementos.append(Paragraph("Nenhum evento encontrado no período selecionado.", styles["Normal"]))
    else:
        tabela = Table(dados_tabela, repeatRows=1, colWidths=[2.6*cm, 5*cm, 3.2*cm, 3.5*cm, 3.5*cm, 3*cm, 5*cm])
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS" if False else "FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
        # Faixa de cor à esquerda de cada linha, conforme o tipo de evento
        for i, cor_hex in enumerate(cores_linhas, start=1):
            try:
                estilo.append(("BACKGROUND", (0, i), (0, i), rl_colors.HexColor(cor_hex)))
            except Exception:
                pass
        tabela.setStyle(TableStyle(estilo))
        elementos.append(tabela)

    doc.build(elementos)
    buffer.seek(0)

    filename = f"calendario_{start.isoformat()}_a_{end.isoformat()}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
