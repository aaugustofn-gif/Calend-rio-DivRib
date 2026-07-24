let calendar;
let tiposEventoCache = [];
let eventoSelecionadoId = null;
let usuariosCache = [];

// Redireciona para o login automaticamente se a sessão expirar (resposta 401)
const _fetchOriginal = window.fetch;
window.fetch = async (...args) => {
  const resp = await _fetchOriginal(...args);
  if (resp.status === 401) {
    window.location.href = "/login";
  }
  return resp;
};

document.addEventListener("DOMContentLoaded", () => {
  // Liga os botões primeiro, sempre — independente do que acontecer no carregamento
  // do calendário ou dos tipos de evento, os botões precisam responder.
  document.getElementById("btn-novo-evento").addEventListener("click", () => abrirModalEvento());
  document.getElementById("btn-tipos").addEventListener("click", abrirModalTipos);
  document.getElementById("btn-exportar").addEventListener("click", abrirModalExportar);
  document.getElementById("form-evento").addEventListener("submit", salvarEvento);
  document.getElementById("form-tipo").addEventListener("submit", salvarTipo);
  document.getElementById("btn-excluir-evento").addEventListener("click", excluirEvento);
  document.getElementById("btn-editar-do-detalhe").addEventListener("click", () => {
    fecharModalDetalhes();
    abrirModalEvento(eventoSelecionadoId);
  });
  document.getElementById("btn-sair").addEventListener("click", sair);
  document.getElementById("btn-assinar-google").addEventListener("click", abrirModalAssinar);
  document.getElementById("btn-copiar-link").addEventListener("click", copiarLinkGoogle);
  document.getElementById("btn-regenerar-link").addEventListener("click", regenerarLinkGoogle);

  const btnUsuarios = document.getElementById("btn-usuarios");
  if (btnUsuarios) {
    btnUsuarios.addEventListener("click", abrirModalUsuarios);
    document.getElementById("form-usuario").addEventListener("submit", salvarUsuario);
    document.getElementById("btn-excluir-usuario").addEventListener("click", excluirUsuario);
  }

  carregarTipos().catch((err) => console.error("Erro ao carregar tipos de evento:", err));

  try {
    if (typeof FullCalendar === "undefined") {
      throw new Error("A biblioteca FullCalendar não carregou (verifique a conexão ou o CDN).");
    }
    iniciarCalendario();
  } catch (err) {
    console.error("Erro ao iniciar o calendário:", err);
    document.getElementById("calendar").innerHTML =
      `<p style="color:#c0392b;padding:16px;">Erro ao carregar o calendário: ${err.message}</p>`;
  }
});

async function sair() {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
}

function iniciarCalendario() {
  const el = document.getElementById("calendar");
  calendar = new FullCalendar.Calendar(el, {
    locale: "pt-br",
    initialView: "dayGridMonth",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,dayGridWeek,listMonth"
    },
    height: "auto",
    events: "/api/events",
    eventClick: (info) => mostrarDetalhes(info.event),
    dateClick: (info) => abrirModalEvento(null, info.dateStr),
  });
  calendar.render();
}

function recarregarEventos() {
  calendar.refetchEvents();
}

// ---------- Tipos de evento ----------

async function carregarTipos() {
  const resp = await fetch("/api/event-types");
  tiposEventoCache = await resp.json();
  const select = document.getElementById("evento-tipo");
  select.innerHTML = tiposEventoCache.map(t => `<option value="${t.id}">${t.name}</option>`).join("");
}

function abrirModalTipos() {
  renderizarListaTipos();
  document.getElementById("tipo-id").value = "";
  document.getElementById("tipo-nome").value = "";
  document.getElementById("tipo-cor").value = "#3788d8";
  document.getElementById("modal-tipos").classList.remove("hidden");
}
function fecharModalTipos() {
  document.getElementById("modal-tipos").classList.add("hidden");
}

function renderizarListaTipos() {
  const div = document.getElementById("lista-tipos");
  div.innerHTML = tiposEventoCache.map(t => `
    <div class="tipo-item">
      <span class="tipo-cor-bolinha" style="background:${t.color}"></span>
      <span>${t.name}</span>
      <button type="button" class="btn btn-secondary" onclick="editarTipo(${t.id})">Editar</button>
      <button type="button" class="btn btn-danger" onclick="excluirTipo(${t.id})">Excluir</button>
    </div>
  `).join("");
}

function editarTipo(id) {
  const tipo = tiposEventoCache.find(t => t.id === id);
  document.getElementById("tipo-id").value = tipo.id;
  document.getElementById("tipo-nome").value = tipo.name;
  document.getElementById("tipo-cor").value = tipo.color;
}

async function excluirTipo(id) {
  if (!confirm("Excluir este tipo de evento?")) return;
  const resp = await fetch(`/api/event-types/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const erro = await resp.json();
    alert(erro.detail || "Erro ao excluir tipo.");
    return;
  }
  await carregarTipos();
  renderizarListaTipos();
}

async function salvarTipo(ev) {
  ev.preventDefault();
  const id = document.getElementById("tipo-id").value;
  const payload = {
    name: document.getElementById("tipo-nome").value,
    color: document.getElementById("tipo-cor").value,
  };
  const url = id ? `/api/event-types/${id}` : "/api/event-types";
  const method = id ? "PUT" : "POST";
  const resp = await fetch(url, {
    method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  if (!resp.ok) {
    const erro = await resp.json();
    alert(erro.detail || "Erro ao salvar tipo.");
    return;
  }
  await carregarTipos();
  renderizarListaTipos();
  document.getElementById("tipo-id").value = "";
  document.getElementById("tipo-nome").value = "";
  recarregarEventos();
}

// ---------- Eventos: modal criar/editar ----------

function abrirModalEvento(eventId = null, dataInicial = null) {
  const form = document.getElementById("form-evento");
  form.reset();
  document.getElementById("evento-id").value = "";
  document.getElementById("bloco-status-manual").classList.add("hidden");
  document.getElementById("btn-excluir-evento").classList.add("hidden");
  document.getElementById("evento-info-registro").classList.add("hidden");

  if (eventId) {
    const fcEvent = calendar.getEventById(String(eventId));
    document.getElementById("modal-evento-titulo").textContent = "Editar Evento";
    document.getElementById("evento-id").value = eventId;
    document.getElementById("evento-nome").value = fcEvent.title;
    document.getElementById("evento-data-inicio").value = fcEvent.extendedProps.start_date;
    document.getElementById("evento-data-fim").value = fcEvent.extendedProps.end_date;
    document.getElementById("evento-tipo").value = fcEvent.extendedProps.event_type_id;
    document.getElementById("evento-local").value = fcEvent.extendedProps.location || "";
    document.getElementById("evento-responsavel").value = fcEvent.extendedProps.responsible || "";
    document.getElementById("evento-observacoes").value = fcEvent.extendedProps.observations || "";
    document.getElementById("bloco-status-manual").classList.remove("hidden");

    let statusOverrideAtual = "";
    if (["adiado", "cancelado", "concluido_antecipado"].includes(fcEvent.extendedProps.status)) {
      statusOverrideAtual = fcEvent.extendedProps.status;
    }
    document.getElementById("evento-status-override").value = statusOverrideAtual;
    document.getElementById("btn-excluir-evento").classList.remove("hidden");

    let info = `Lançado por ${fcEvent.extendedProps.created_by} em ${fcEvent.extendedProps.created_at}.`;
    if (fcEvent.extendedProps.updated_by) {
      info += `<br>Última edição por ${fcEvent.extendedProps.updated_by} em ${fcEvent.extendedProps.updated_at}.`;
    }
    const infoDiv = document.getElementById("evento-info-registro");
    infoDiv.innerHTML = info;
    infoDiv.classList.remove("hidden");
  } else {
    document.getElementById("modal-evento-titulo").textContent = "Novo Evento";
    if (dataInicial) {
      document.getElementById("evento-data-inicio").value = dataInicial;
      document.getElementById("evento-data-fim").value = dataInicial;
    }
  }

  document.getElementById("modal-evento").classList.remove("hidden");
}

function fecharModalEvento() {
  document.getElementById("modal-evento").classList.add("hidden");
}

async function salvarEvento(ev) {
  ev.preventDefault();
  const id = document.getElementById("evento-id").value;

  const payload = {
    title: document.getElementById("evento-nome").value,
    start_date: document.getElementById("evento-data-inicio").value,
    end_date: document.getElementById("evento-data-fim").value,
    event_type_id: parseInt(document.getElementById("evento-tipo").value),
    location: document.getElementById("evento-local").value,
    responsible: document.getElementById("evento-responsavel").value,
    observations: document.getElementById("evento-observacoes").value,
  };

  if (id) {
    payload.status_override = document.getElementById("evento-status-override").value;
    const resp = await fetch(`/api/events/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const erro = await resp.json();
      alert(erro.detail || "Erro ao salvar evento.");
      return;
    }
  } else {
    const resp = await fetch("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const erro = await resp.json();
      alert(erro.detail || "Erro ao criar evento.");
      return;
    }
  }

  fecharModalEvento();
  recarregarEventos();
}

async function excluirEvento() {
  const id = document.getElementById("evento-id").value;
  if (!id) return;
  if (!confirm("Tem certeza que deseja excluir este evento?")) return;
  const resp = await fetch(`/api/events/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    alert("Erro ao excluir evento.");
    return;
  }
  fecharModalEvento();
  recarregarEventos();
}

// ---------- Detalhes (visualização) ----------

function mostrarDetalhes(fcEvent) {
  eventoSelecionadoId = fcEvent.id;
  const p = fcEvent.extendedProps;

  document.getElementById("detalhe-titulo").textContent = fcEvent.title;
  document.getElementById("detalhe-status").textContent = p.status_label;
  document.getElementById("detalhe-tipo").textContent = p.event_type_name;
  document.getElementById("detalhe-periodo").textContent =
    `${formatarData(p.start_date)} a ${formatarData(p.end_date)}`;
  document.getElementById("detalhe-local").textContent = p.location || "-";
  document.getElementById("detalhe-responsavel").textContent = p.responsible || "-";
  document.getElementById("detalhe-observacoes").textContent = p.observations || "-";
  document.getElementById("detalhe-criado").textContent = `${p.created_by} em ${p.created_at}`;

  const linhaEditado = document.getElementById("linha-editado");
  if (p.updated_by) {
    document.getElementById("detalhe-editado").textContent = `${p.updated_by} em ${p.updated_at}`;
    linhaEditado.classList.remove("hidden");
  } else {
    linhaEditado.classList.add("hidden");
  }

  document.getElementById("modal-detalhes").classList.remove("hidden");
}

function fecharModalDetalhes() {
  document.getElementById("modal-detalhes").classList.add("hidden");
}

function formatarData(iso) {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

// ---------- Exportar PDF ----------

function abrirModalExportar() {
  document.getElementById("modal-exportar").classList.remove("hidden");
}
function fecharModalExportar() {
  document.getElementById("modal-exportar").classList.add("hidden");
}

function exportarPdf() {
  const inicio = document.getElementById("export-data-inicio").value;
  const fim = document.getElementById("export-data-fim").value;
  const formato = document.getElementById("export-formato").value;
  if (!inicio || !fim) {
    alert("Selecione as duas datas.");
    return;
  }
  const rota = formato === "timeline" ? "/api/export/pdf-timeline" : "/api/export/pdf";
  window.open(`${rota}?start=${inicio}&end=${fim}`, "_blank");
  fecharModalExportar();
}

// ---------- Usuários (somente admin) ----------

async function carregarUsuarios() {
  const resp = await fetch("/api/usuarios");
  usuariosCache = await resp.json();
  renderizarListaUsuarios();
}

function renderizarListaUsuarios() {
  const div = document.getElementById("lista-usuarios");
  div.innerHTML = usuariosCache.map(u => `
    <div class="tipo-item">
      <span>${u.nome} — NIP ${u.nip}${u.setor ? " — " + u.setor : ""}${u.is_admin ? " (admin)" : ""}</span>
      <button type="button" class="btn btn-secondary" onclick="editarUsuario(${u.id})">Editar</button>
    </div>
  `).join("");
}

function abrirModalUsuarios() {
  document.getElementById("form-usuario").reset();
  document.getElementById("usuario-id").value = "";
  document.getElementById("usuario-nip").disabled = false;
  document.getElementById("label-usuario-senha").textContent = "Senha inicial";
  document.getElementById("btn-excluir-usuario").classList.add("hidden");
  carregarUsuarios();
  document.getElementById("modal-usuarios").classList.remove("hidden");
}

function fecharModalUsuarios() {
  document.getElementById("modal-usuarios").classList.add("hidden");
}

function editarUsuario(id) {
  const u = usuariosCache.find(x => x.id === id);
  document.getElementById("usuario-id").value = u.id;
  document.getElementById("usuario-nome").value = u.nome;
  document.getElementById("usuario-nip").value = u.nip;
  document.getElementById("usuario-nip").disabled = true; // NIP não muda depois de criado
  document.getElementById("usuario-setor").value = u.setor || "";
  document.getElementById("usuario-senha").value = "";
  document.getElementById("label-usuario-senha").textContent = "Nova senha (deixe em branco para não alterar)";
  document.getElementById("usuario-admin").checked = u.is_admin;
  document.getElementById("btn-excluir-usuario").classList.remove("hidden");
}

async function salvarUsuario(ev) {
  ev.preventDefault();
  const id = document.getElementById("usuario-id").value;
  const nome = document.getElementById("usuario-nome").value;
  const setor = document.getElementById("usuario-setor").value;
  const senha = document.getElementById("usuario-senha").value;
  const isAdmin = document.getElementById("usuario-admin").checked;

  if (id) {
    const payload = { nome, setor, is_admin: isAdmin };
    if (senha) payload.nova_senha = senha;
    const resp = await fetch(`/api/usuarios/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const erro = await resp.json();
      alert(erro.detail || "Erro ao salvar usuário.");
      return;
    }
  } else {
    const nip = document.getElementById("usuario-nip").value.trim();
    if (!senha) {
      alert("Defina uma senha inicial para o novo usuário.");
      return;
    }
    const payload = { nome, nip, setor, senha_inicial: senha, is_admin: isAdmin };
    const resp = await fetch("/api/usuarios", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const erro = await resp.json();
      alert(erro.detail || "Erro ao criar usuário.");
      return;
    }
  }

  await carregarUsuarios();
  abrirModalUsuarios();
}

async function excluirUsuario() {
  const id = document.getElementById("usuario-id").value;
  if (!id) return;
  if (!confirm("Excluir este usuário? Ele perderá o acesso ao calendário imediatamente.")) return;
  const resp = await fetch(`/api/usuarios/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const erro = await resp.json();
    alert(erro.detail || "Erro ao excluir usuário.");
    return;
  }
  await carregarUsuarios();
  abrirModalUsuarios();
}

// ---------- Assinar no Google Calendar ----------

async function abrirModalAssinar() {
  const resp = await fetch("/api/me/link-google");
  const dados = await resp.json();
  document.getElementById("link-google-url").value = dados.url;
  document.getElementById("modal-assinar").classList.remove("hidden");
}

function fecharModalAssinar() {
  document.getElementById("modal-assinar").classList.add("hidden");
}

function copiarLinkGoogle() {
  const campo = document.getElementById("link-google-url");
  campo.select();
  campo.setSelectionRange(0, 99999);
  navigator.clipboard.writeText(campo.value).then(() => {
    const btn = document.getElementById("btn-copiar-link");
    const textoOriginal = btn.textContent;
    btn.textContent = "Copiado!";
    setTimeout(() => { btn.textContent = textoOriginal; }, 1500);
  });
}

async function regenerarLinkGoogle() {
  if (!confirm("Isso torna o link antigo inválido — se você já configurou no Google, vai precisar refazer com o novo link. Continuar?")) return;
  const resp = await fetch("/api/me/regenerar-link-google", { method: "POST" });
  const dados = await resp.json();
  document.getElementById("link-google-url").value = dados.url;
}
