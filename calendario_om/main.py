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
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase.pdfmetrics import stringWidth

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

STATUS_CORES = {
    "futuro": "#3788d8",
    "em_andamento": "#d38222",
    "finalizado": "#27ae60",
    "adiado": "#969696",
    "cancelado": "#c0392b",
    "concluido_antecipado": "#27ae60",
}

NOMES_MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


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


# ---------- Exportação em PDF: gráfico "linha do tempo" ----------

FONTE_TITULO_CAIXA = "Helvetica-Bold"
FONTE_DATA_CAIXA = "Helvetica"
TAM_TITULO, TAM_DATA = 8, 7
MAX_TEXT_W = 130       # largura máxima de uma linha de texto dentro da caixa
PAD_X, PAD_Y = 7, 5
GAP_ENTRE_CAIXAS = 10
NIVEL_ALTURA = 62       # distância entre "andares" do tronco
SEG_W = 100             # largura de cada mês na linha do tempo
MARGEM = 50
TL_H = 22


def meses_do_periodo(start: date, end: date):
    meses = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        meses.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return meses


def _medir(texto, fonte, tamanho):
    return stringWidth(texto, fonte, tamanho)


def _quebrar_texto(texto, fonte, tamanho, largura_max):
    if _medir(texto, fonte, tamanho) <= largura_max:
        return [texto]
    palavras = texto.split(" ")
    linha1, linha2 = "", ""
    for p in palavras:
        teste = (linha1 + " " + p).strip()
        if _medir(teste, fonte, tamanho) <= largura_max or not linha1:
            linha1 = teste
        else:
            linha2 = (linha2 + " " + p).strip()

    def forcar(l):
        while _medir(l, fonte, tamanho) > largura_max and len(l) > 1:
            l = l[:-2] + "…"
        return l

    linha1 = forcar(linha1)
    if linha2:
        linha2 = forcar(linha2)
        return [linha1, linha2]
    return [linha1]


class _EventoDesenho:
    def __init__(self, titulo, data_txt, mes_idx, cor_hex):
        self.titulo = titulo
        self.data_txt = data_txt
        self.mes_idx = mes_idx
        self.cor = rl_colors.HexColor(cor_hex)

        self.linhas_titulo = _quebrar_texto(titulo, FONTE_TITULO_CAIXA, TAM_TITULO, MAX_TEXT_W)
        largura_titulo = max(_medir(l, FONTE_TITULO_CAIXA, TAM_TITULO) for l in self.linhas_titulo)
        largura_data = _medir(data_txt, FONTE_DATA_CAIXA, TAM_DATA)
        self.largura = max(largura_titulo, largura_data) + PAD_X * 2
        self.largura = max(self.largura, 80)
        n_linhas = len(self.linhas_titulo) + 1
        self.altura = n_linhas * 12 + PAD_Y * 2


@app.get("/api/export/pdf-timeline")
def export_pdf_timeline(start: date, end: date, db: Session = Depends(get_db)):
    if end < start:
        raise HTTPException(400, "A data final não pode ser anterior à data inicial.")

    meses = meses_do_periodo(start, end)
    if len(meses) > 24:
        raise HTTPException(400, "Período muito longo para este formato (máximo de 24 meses).")

    eventos_db = (
        db.query(models.Event)
        .filter(models.Event.start_date <= end, models.Event.end_date >= start)
        .order_by(models.Event.start_date)
        .all()
    )

    mes_para_indice = {ym: i for i, ym in enumerate(meses)}

    eventos_desenho = []
    for e in eventos_db:
        ym = (e.start_date.year, e.start_date.month)
        if ym in mes_para_indice:
            idx = mes_para_indice[ym]
        elif ym < meses[0]:
            idx = 0
        else:
            idx = len(meses) - 1

        status = compute_status(e)
        cor_hex = STATUS_CORES.get(status, "#3788d8")
        if e.start_date == e.end_date:
            data_txt = e.start_date.strftime("%d/%m")
        else:
            data_txt = f"{e.start_date.strftime('%d/%m')}-{e.end_date.strftime('%d/%m')}"

        eventos_desenho.append(_EventoDesenho(e.title, data_txt, idx, cor_hex))

    # ---------- Agrupar por mês, dividindo em cima/baixo ----------
    por_mes = {}
    for ev in eventos_desenho:
        por_mes.setdefault(ev.mes_idx, []).append(ev)

    grupos = []
    for idx, evs in por_mes.items():
        metade = (len(evs) + 1) // 2
        cima, baixo = evs[:metade], evs[metade:]
        if cima:
            grupos.append({"mes_idx": idx, "lado": 1, "eventos": cima})
        if baixo:
            grupos.append({"mes_idx": idx, "lado": -1, "eventos": baixo})

    largura_pagina = MARGEM * 2 + len(meses) * SEG_W

    def centro_do_mes(idx):
        return MARGEM + (idx + 0.5) * SEG_W

    faixas_ocupadas = {1: [], -1: []}
    for g in grupos:
        total_w = sum(ev.largura for ev in g["eventos"]) + GAP_ENTRE_CAIXAS * (len(g["eventos"]) - 1)
        centro = centro_do_mes(g["mes_idx"])
        x_inicio = centro - total_w / 2

        centros_caixas = []
        x_cursor = x_inicio
        for ev in g["eventos"]:
            cx = x_cursor + ev.largura / 2
            centros_caixas.append(cx)
            x_cursor += ev.largura + GAP_ENTRE_CAIXAS

        span_x0, span_x1 = x_inicio, x_cursor - GAP_ENTRE_CAIXAS
        lado = g["lado"]

        nivel = 1
        while True:
            colide = any(
                not (span_x1 < ox0 - 10 or span_x0 > ox1 + 10)
                for (ox0, ox1, onivel) in faixas_ocupadas[lado] if onivel == nivel
            )
            if not colide:
                break
            nivel += 1

        faixas_ocupadas[lado].append((span_x0, span_x1, nivel))
        g["centro_mes_x"] = centro
        g["centros_caixas"] = centros_caixas
        g["nivel"] = nivel

    nivel_max_cima = max([g["nivel"] for g in grupos if g["lado"] == 1], default=0)
    nivel_max_baixo = max([g["nivel"] for g in grupos if g["lado"] == -1], default=0)

    altura_acima = nivel_max_cima * NIVEL_ALTURA + 70 if nivel_max_cima else 40
    altura_abaixo = nivel_max_baixo * NIVEL_ALTURA + 70 if nivel_max_baixo else 40
    altura_pagina = altura_acima + TL_H + altura_abaixo + 60  # + espaço pro título

    buffer = io.BytesIO()
    c = pdfcanvas.Canvas(buffer, pagesize=(largura_pagina, altura_pagina))

    TL_Y_TOPO = altura_pagina - altura_acima - 40  # y (de baixo pra cima) do topo da barra de meses
    TL_Y_BASE = TL_Y_TOPO - TL_H

    # Título
    titulo_txt = f"Calendário Anual de Atividades — {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGEM, altura_pagina - 25, titulo_txt)

    # Legenda
    itens_legenda = [("Futuro", "#3788d8"), ("Em andamento", "#d38222"), ("Finalizado", "#27ae60")]
    lx = largura_pagina - MARGEM - 300
    c.setFont("Helvetica", 9)
    for nome, cor in itens_legenda:
        c.setFillColor(rl_colors.HexColor(cor))
        c.roundRect(lx, altura_pagina - 30, 14, 10, 2, fill=1, stroke=0)
        c.setFillColor(rl_colors.HexColor("#1e1e1e"))
        c.drawString(lx + 20, altura_pagina - 28, nome)
        lx += 100

    if not eventos_db:
        c.setFont("Helvetica", 11)
        c.drawCentredString(largura_pagina / 2, altura_pagina / 2, "Nenhum evento encontrado no período selecionado.")
        c.showPage()
        c.save()
        buffer.seek(0)
        filename = f"calendario_timeline_{start.isoformat()}_a_{end.isoformat()}.pdf"
        return StreamingResponse(
            buffer, media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # Barra de meses
    c.setFillColor(rl_colors.HexColor("#1e3250"))
    c.rect(MARGEM, TL_Y_BASE, len(meses) * SEG_W, TL_H, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 10)
    for i, (ano, mnum) in enumerate(meses):
        x0 = MARGEM + i * SEG_W
        if i > 0:
            c.setStrokeColor(rl_colors.white)
            c.line(x0, TL_Y_BASE, x0, TL_Y_TOPO)
        label = NOMES_MESES[mnum - 1]
        if len(meses) > 12 or meses[0][0] != meses[-1][0]:
            label += f"/{str(ano)[2:]}"
        c.setFillColor(rl_colors.white)
        c.drawCentredString(x0 + SEG_W / 2, TL_Y_BASE + 7, label)

    # Grupos de eventos
    for g in grupos:
        lado = g["lado"]
        nivel = g["nivel"]
        centro_mes_x = g["centro_mes_x"]
        cor_tronco = rl_colors.HexColor("#787878")

        altura_bus = TL_Y_TOPO + nivel * NIVEL_ALTURA if lado == 1 else TL_Y_BASE - nivel * NIVEL_ALTURA
        y_tl = TL_Y_TOPO if lado == 1 else TL_Y_BASE

        c.setStrokeColor(cor_tronco)
        c.setLineWidth(1.3)
        c.line(centro_mes_x, y_tl, centro_mes_x, altura_bus)
        c.setFillColor(cor_tronco)
        c.circle(centro_mes_x, y_tl, 2, fill=1, stroke=0)

        xs = g["centros_caixas"]
        bus_x0, bus_x1 = min(xs + [centro_mes_x]), max(xs + [centro_mes_x])
        c.line(bus_x0, altura_bus, bus_x1, altura_bus)

        for ev, cx in zip(g["eventos"], xs):
            box_h = ev.altura
            c.setStrokeColor(ev.cor)
            if lado == 1:
                y_box_baixo = altura_bus + 8
                y_box_topo = y_box_baixo + box_h
                c.line(cx, altura_bus, cx, y_box_baixo)
            else:
                y_box_topo = altura_bus - 8
                y_box_baixo = y_box_topo - box_h
                c.line(cx, altura_bus, cx, y_box_topo)

            x0 = cx - ev.largura / 2
            c.setFillColor(rl_colors.white)
            c.roundRect(x0, y_box_baixo, ev.largura, box_h, 4, fill=1, stroke=1)

            ty = y_box_baixo + box_h - PAD_Y - TAM_TITULO
            c.setFont(FONTE_TITULO_CAIXA, TAM_TITULO)
            c.setFillColor(rl_colors.HexColor("#1e1e1e"))
            for linha in ev.linhas_titulo:
                c.drawCentredString(cx, ty, linha)
                ty -= 12
            c.setFont(FONTE_DATA_CAIXA, TAM_DATA)
            c.setFillColor(rl_colors.HexColor("#646464"))
            c.drawCentredString(cx, ty, ev.data_txt)

    c.showPage()
    c.save()
    buffer.seek(0)

    filename = f"calendario_timeline_{start.isoformat()}_a_{end.isoformat()}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
