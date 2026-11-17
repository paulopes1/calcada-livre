"use strict";
const ROTULO = { buraco: "Buraco", obstaculo: "Obstáculo", piso_quebrado: "Piso quebrado" };
const COR = { buraco: "#b42318", obstaculo: "#b54708", piso_quebrado: "#6941c6" };
const SITUACAO = {
  pendente_validacao: "Aguardando validação", aberta: "Aberta", validada: "Validada",
  rejeitada: "Rejeitada", resolvida: "Resolvida",
};
const PRIORIDADE = { alta: "Alta", media: "Média", baixa: "Baixa" };
const ORIGEM = { app: "Aplicativo", video: "Vídeo", carrinho: "Carrinho" };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => `${Math.round(v * 100)}%`;

let ocorrencias = [];
let filtroTipo = "";

// ---------- aviso flutuante ----------
let avisoTimer = null;
function avisar(msg) {
  const el = $("aviso");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

// ---------- mapa (centro inicial: Av. Paulista, São Paulo) ----------
let mapa = null, camada = null, marcadorUsuario = null;
if (window.L) {
  mapa = L.map("mapa", { keyboard: true, scrollWheelZoom: false }).setView([-23.5614, -46.6559], 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; colaboradores do OpenStreetMap",
  }).addTo(mapa);
  camada = L.layerGroup().addTo(mapa);
  mapa.on("focus", () => mapa.scrollWheelZoom.enable());
  mapa.on("click", (e) => {
    mapa.scrollWheelZoom.enable();
    $("mapa").classList.remove("marcando");
    definirLocal(e.latlng.lat, e.latlng.lng, "Local marcado no mapa", { buscarEndereco: true });
  });
} else {
  $("mapa").textContent = "Mapa indisponível sem internet. A tabela abaixo mostra as ocorrências.";
}

// ---------- passo 1: foto ou vídeo, com prévia ----------
const EXT_VIDEO = /\.(mp4|webm|mov|avi|mkv|m4v|3gp)$/i;
const ehVideo = (arq) => (arq.type || "").startsWith("video/") || EXT_VIDEO.test(arq.name || "");
const tamanho = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.ceil(b / 1024)} KB`);

$("foto").addEventListener("change", () => {
  const arquivo = $("foto").files[0];
  if (!arquivo) { limparFoto(); return; }
  const video = ehVideo(arquivo);
  $("previa").hidden = video;
  if (!video) $("previa").src = URL.createObjectURL(arquivo);
  $("icone-video").hidden = !video;
  $("icone-arquivo").hidden = video;
  $("texto-foto").innerHTML = `<strong>${esc(arquivo.name)}</strong><span>${video ? "Vídeo" : "Foto"} · ${tamanho(arquivo.size)} · clique para trocar</span>`;
  $("btn-enviar").textContent = video ? "Enviar e analisar vídeo" : "Enviar foto";
});
function limparFoto() {
  $("previa").hidden = true;
  $("previa").removeAttribute("src");
  $("icone-video").hidden = true;
  $("icone-arquivo").hidden = false;
  $("texto-foto").innerHTML = "<strong>Escolher foto ou vídeo</strong><span>Foto até 10 MB · vídeo MP4, WEBM ou MOV até 200 MB</span>";
  $("btn-enviar").textContent = "Enviar foto";
}

// ---------- passo 2: local (endereço, mapa ou GPS) ----------
const NOMINATIM = "https://nominatim.openstreetmap.org";
function statusLocal(msg, definido = false) {
  $("local-status").textContent = msg;
  $("local-status").classList.toggle("definido", definido);
}
function mostrarAba(modo) {
  document.querySelectorAll(".aba-painel").forEach((p) => { p.hidden = p.dataset.modo !== modo; });
}
document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", () => mostrarAba(r.value)));

function definirLocal(lat, lon, msg, { buscarEndereco = false, centralizar = false } = {}) {
  $("latitude").value = lat.toFixed(6);
  $("longitude").value = lon.toFixed(6);
  statusLocal(`${msg} (${lat.toFixed(5)}, ${lon.toFixed(5)})`, true);
  if (mapa) {
    if (marcadorUsuario) marcadorUsuario.setLatLng([lat, lon]);
    else {
      marcadorUsuario = L.marker([lat, lon], { title: "Local da barreira (arraste para ajustar)", draggable: true }).addTo(mapa);
      marcadorUsuario.on("dragend", () => {
        const p = marcadorUsuario.getLatLng();
        definirLocal(p.lat, p.lng, "Local ajustado no mapa", { buscarEndereco: true });
      });
    }
    if (centralizar) mapa.setView([lat, lon], 17);
  }
  if (buscarEndereco) enderecoDoPonto(lat, lon);
}

// endereço digitado -> coordenadas (OpenStreetMap / Nominatim)
async function buscarEndereco() {
  const q = $("endereco").value.trim();
  if (q.length < 4) { statusLocal("Digite rua e número, bairro ou cidade."); $("endereco").focus(); return false; }
  statusLocal("Procurando o endereço…");
  try {
    const url = `${NOMINATIM}/search?format=jsonv2&limit=1&countrycodes=br&accept-language=pt-BR&q=${encodeURIComponent(q)}`;
    const res = await (await fetch(url, { headers: { Accept: "application/json" } })).json();
    if (!res.length) { statusLocal("Endereço não encontrado. Confira o texto ou marque o ponto no mapa."); return false; }
    definirLocal(parseFloat(res[0].lat), parseFloat(res[0].lon), "Endereço encontrado", { centralizar: true });
    return true;
  } catch {
    statusLocal("Serviço de endereços indisponível. Marque o ponto no mapa.");
    return false;
  }
}

// coordenadas -> endereço legível (preenche o campo quando a pessoa usa o mapa ou o GPS)
async function enderecoDoPonto(lat, lon) {
  try {
    const url = `${NOMINATIM}/reverse?format=jsonv2&zoom=18&accept-language=pt-BR&lat=${lat}&lon=${lon}`;
    const r = await (await fetch(url, { headers: { Accept: "application/json" } })).json();
    const a = r.address || {};
    const rua = [a.road, a.house_number].filter(Boolean).join(", ");
    const texto = [rua, a.suburb || a.neighbourhood, a.city || a.town].filter(Boolean).join(" - ");
    if (texto) $("endereco").value = texto;
  } catch { /* sem internet: as coordenadas já bastam */ }
}

$("btn-buscar").addEventListener("click", buscarEndereco);
$("endereco").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); buscarEndereco(); } });
$("btn-mapa").addEventListener("click", () => {
  if (!mapa) { statusLocal("Mapa indisponível agora. Use o endereço."); return; }
  $("mapa").classList.add("marcando");
  $("mapa").scrollIntoView({ behavior: "smooth", block: "center" });
  $("mapa").focus({ preventScroll: true });
  statusLocal("Clique no mapa no ponto da barreira.");
});
$("btn-local").addEventListener("click", () => {
  if (!navigator.geolocation) { statusLocal("Este navegador não informa a localização. Use o endereço ou o mapa."); return; }
  statusLocal("Buscando sua localização…");
  navigator.geolocation.getCurrentPosition(
    (p) => definirLocal(p.coords.latitude, p.coords.longitude, "Localização encontrada", { buscarEndereco: true, centralizar: true }),
    () => statusLocal("Não foi possível obter a localização. Use o endereço ou o mapa."),
    { enableHighAccuracy: true, timeout: 10000 },
  );
});

// ---------- reduz a foto no aparelho (pouca conectividade) ----------
async function reduzirFoto(arquivo, ladoMax = 1280, qualidade = 0.82) {
  try {
    const bmp = await createImageBitmap(arquivo);
    const escala = Math.min(1, ladoMax / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * escala);
    canvas.height = Math.round(bmp.height * escala);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", qualidade));
    return blob && blob.size < arquivo.size ? blob : arquivo;
  } catch { return arquivo; }
}

// ---------- envio ----------
$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const arquivo = $("foto").files[0];
  const res = $("resultado");
  const mostrar = (tipo, html) => { res.hidden = false; res.className = `resultado ${tipo}`; res.innerHTML = html; res.focus(); };
  if (!arquivo) {
    mostrar("alerta", `<div class="resultado-topo"><span class="resultado-icone" aria-hidden="true">!</span><div><h3>Escolha uma foto antes de enviar.</h3></div></div>`);
    $("foto").focus();
    return;
  }
  const btn = $("btn-enviar");
  if (ehVideo(arquivo)) { await enviarVideo(arquivo, btn, mostrar); return; }
  btn.disabled = true;
  btn.innerHTML = `<span class="giro" aria-hidden="true"></span>Analisando a foto…`;
  try {
    // endereço digitado, mas ainda não buscado: tenta localizar antes de enviar
    if ($("endereco").value.trim() && !$("latitude").value) await buscarEndereco();
    const fd = new FormData();
    fd.append("foto", await reduzirFoto(arquivo), "foto.jpg");
    for (const k of ["latitude", "longitude", "endereco", "descricao"]) if ($(k).value.trim()) fd.append(k, $(k).value.trim());
    fd.append("origem", "app");
    const r = await fetch("/detectar", { method: "POST", body: fd });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail?.[0]?.msg || body.detail || "erro ao analisar a foto");
    if (!body.ocorrencia) {
      mostrar("alerta", `<div class="resultado-topo"><span class="resultado-icone" aria-hidden="true">!</span>
        <div><h3>Nenhuma barreira identificada</h3><p class="sub">${esc(body.mensagem)}</p></div></div>`);
      return;
    }
    const o = body.ocorrencia;
    const ok = o.status === "aberta";
    mostrar(ok ? "ok" : "alerta", `
      <div class="resultado-topo">
        <span class="resultado-icone" aria-hidden="true">${ok ? "✓" : "!"}</span>
        <div><h3>${esc(body.mensagem)}</h3><p class="sub">Protocolo ${esc(o.protocolo)}</p></div>
      </div>
      <dl>
        <dt>Tipo</dt><dd><span class="selo ${esc(o.tipo)}">${esc(ROTULO[o.tipo] || o.tipo)}</span> ${pct(o.confianca)} de confiança</dd>
        <dt>Prioridade</dt><dd>${esc(PRIORIDADE[o.prioridade] || o.prioridade)}</dd>
        <dt>Situação</dt><dd>${esc(SITUACAO[o.status] || o.status)}</dd>
        ${o.endereco ? `<dt>Local</dt><dd>${esc(o.endereco)}</dd>` : ""}
      </dl>
      <img src="${esc(o.foto_url)}" alt="Foto enviada com a barreira marcada: ${esc(ROTULO[o.tipo])}">`);
    $("form").reset();
    limparFoto();
    statusLocal("Nenhum local escolhido.");
    mostrarAba("endereco");
    if (marcadorUsuario) { marcadorUsuario.remove(); marcadorUsuario = null; }
    carregar();
  } catch (e) {
    mostrar("alerta", `<div class="resultado-topo"><span class="resultado-icone" aria-hidden="true">!</span>
      <div><h3>Não foi possível enviar agora</h3><p class="sub">${esc(e.message)}. Verifique a conexão e tente de novo.</p></div></div>`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar foto";
  }
});

// ---------- vídeo: envio com progresso e análise ao vivo ----------
function limparFormulario() {
  $("form").reset();
  limparFoto();
  statusLocal("Nenhum local escolhido.");
  mostrarAba("endereco");
  if (marcadorUsuario) { marcadorUsuario.remove(); marcadorUsuario = null; }
}

function subirVideo(fd, aoProgresso) {
  return new Promise((ok, falha) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/videos");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) aoProgresso(e.loaded / e.total); };
    xhr.onload = () => {
      let corpo = {};
      try { corpo = JSON.parse(xhr.responseText); } catch { /* resposta sem JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) ok(corpo);
      else falha(new Error(corpo.detail?.[0]?.msg || corpo.detail || `erro ${xhr.status}`));
    };
    xhr.onerror = () => falha(new Error("falha de conexão"));
    xhr.send(fd);
  });
}

async function enviarVideo(arquivo, btn, mostrar) {
  btn.disabled = true;
  btn.innerHTML = `<span class="giro" aria-hidden="true"></span>Enviando vídeo… 0%`;
  try {
    if ($("endereco").value.trim() && !$("latitude").value) await buscarEndereco();
    const fd = new FormData();
    fd.append("video", arquivo, arquivo.name);
    for (const k of ["latitude", "longitude", "endereco"]) if ($(k).value.trim()) fd.append(k, $(k).value.trim());
    const r = await subirVideo(fd, (p) => { btn.innerHTML = `<span class="giro" aria-hidden="true"></span>Enviando vídeo… ${Math.round(p * 100)}%`; });
    $("resultado").hidden = true;
    abrirAnalise(r, arquivo.name);
    limparFormulario();
  } catch (e) {
    mostrar("alerta", `<div class="resultado-topo"><span class="resultado-icone" aria-hidden="true">!</span>
      <div><h3>Não foi possível enviar o vídeo</h3><p class="sub">${esc(e.message)}.</p></div></div>`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar foto";
  }
}

let analiseTimer = null;
function abrirAnalise(r, nome) {
  const dlg = $("dlg-video");
  $("dlg-arquivo").textContent = nome;
  $("dlg-estado").textContent = "Analisando…";
  $("dlg-estado").className = "dlg-estado";
  $("dlg-barra").style.width = "0";
  $("dlg-carregando").hidden = false;
  for (const t of ["buraco", "obstaculo", "piso_quebrado"]) $(`dlg-n-${t}`).textContent = "0";
  $("dlg-lista").innerHTML = `<li class="vazio">Nenhuma ainda.</li>`;
  const img = $("dlg-stream");
  img.onload = () => { $("dlg-carregando").hidden = true; };
  img.src = `${r.ao_vivo_url}?t=${Date.now()}`;
  dlg.showModal();

  let vistas = 0;
  clearInterval(analiseTimer);
  analiseTimer = setInterval(async () => {
    let s;
    try { s = await (await fetch(r.status_url)).json(); } catch { return; }
    if (s.progresso != null) $("dlg-barra").style.width = `${Math.round(s.progresso * 100)}%`;
    for (const t of ["buraco", "obstaculo", "piso_quebrado"]) $(`dlg-n-${t}`).textContent = s.contagem[t];
    if (s.ocorrencias.length !== vistas) {
      vistas = s.ocorrencias.length;
      $("dlg-lista").innerHTML = s.ocorrencias.slice().reverse().map((o) => `
        <li><span class="selo ${esc(o.tipo)}">${esc(ROTULO[o.tipo])}</span>
            <span class="protocolo">${esc(o.protocolo)}</span><span>${pct(o.confianca)}</span></li>`).join("");
      carregar();
    }
    if (["concluida", "erro", "interrompida"].includes(s.status)) {
      clearInterval(analiseTimer);
      const n = s.ocorrencias.length;
      if (s.status === "concluida") {
        $("dlg-barra").style.width = "100%";
        $("dlg-estado").textContent = n
          ? `Análise concluída: ${n} ${n === 1 ? "barreira registrada" : "barreiras registradas"} a ${Math.round(s.fps_medio)} FPS.`
          : "Análise concluída: nenhuma barreira identificada com segurança.";
        $("dlg-estado").className = "dlg-estado fim";
      } else {
        $("dlg-estado").textContent = s.status === "erro" ? `Não foi possível analisar: ${s.erro}` : "Análise interrompida.";
        $("dlg-estado").className = "dlg-estado erro";
      }
      carregar();
    }
  }, 1000);
}

function fecharAnalise() {
  clearInterval(analiseTimer);
  $("dlg-stream").removeAttribute("src"); // encerra o fluxo (interrompe a análise se ainda estiver rodando)
  if ($("dlg-video").open) $("dlg-video").close();
  carregar();
}
$("dlg-fechar").addEventListener("click", fecharAnalise);
$("dlg-video").addEventListener("cancel", (e) => { e.preventDefault(); fecharAnalise(); });
$("dlg-mapa").addEventListener("click", () => {
  fecharAnalise();
  $("mapa-sec").scrollIntoView({ behavior: "smooth", block: "start" });
});

// ---------- filtros por tipo (mapa e tabela) ----------
document.querySelectorAll(".filtro").forEach((b) => b.addEventListener("click", () => {
  filtroTipo = b.dataset.tipo;
  document.querySelectorAll(".filtro").forEach((x) => {
    const ativo = x === b;
    x.classList.toggle("ativo", ativo);
    x.setAttribute("aria-pressed", String(ativo));
  });
  desenhar();
}));

// ---------- validação humana (painel da zeladoria) ----------
$("lista").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-acao]");
  if (!btn) return;
  const status = btn.dataset.acao === "confirmar" ? "validada" : "rejeitada";
  btn.disabled = true;
  try {
    const r = await fetch(`/ocorrencias/${btn.dataset.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
    });
    if (!r.ok) throw new Error();
    avisar(status === "validada" ? "Ocorrência confirmada e enviada para a zeladoria." : "Ocorrência rejeitada.");
    carregar();
  } catch {
    btn.disabled = false;
    avisar("Não foi possível atualizar a ocorrência.");
  }
});

// ---------- dados: resumo, tabela e mapa ----------
async function carregar() {
  try {
    ocorrencias = await (await fetch("/ocorrencias?limite=200")).json();
    $("n-total").textContent = ocorrencias.length;
    for (const t of ["buraco", "obstaculo", "piso_quebrado"]) $(`n-${t}`).textContent = ocorrencias.filter((o) => o.tipo === t).length;
    $("n-pendente").textContent = ocorrencias.filter((o) => o.status === "pendente_validacao").length;
    desenhar();
  } catch {
    $("lista").innerHTML = `<tr><td colspan="8" class="vazio">Sem conexão com o servidor. Nova tentativa em instantes.</td></tr>`;
  }
}

function desenhar() {
  const lista = filtroTipo ? ocorrencias.filter((o) => o.tipo === filtroTipo) : ocorrencias;
  $("contagem-lista").textContent = `${lista.length} ${lista.length === 1 ? "ocorrência" : "ocorrências"}`;
  $("lista").innerHTML = lista.length ? lista.map(linha).join("")
    : `<tr><td colspan="8" class="vazio">${filtroTipo ? "Nenhuma ocorrência deste tipo." : "Nenhuma ocorrência registrada até agora."}</td></tr>`;

  if (!camada) return;
  camada.clearLayers();
  for (const o of lista) {
    if (o.latitude == null || o.longitude == null) continue;
    L.circleMarker([o.latitude, o.longitude], { radius: 9, color: "#ffffff", weight: 2.5, fillColor: COR[o.tipo] || "#444", fillOpacity: 1 })
      .bindPopup(`<div class="popup-titulo"><span class="selo ${esc(o.tipo)}">${esc(ROTULO[o.tipo])}</span> ${pct(o.confianca)}</div>`
        + `${o.endereco ? esc(o.endereco) + "<br>" : ""}${esc(SITUACAO[o.status])} · ${esc(o.protocolo)}`
        + `<img src="${esc(o.foto_url)}" alt="Foto da ocorrência ${esc(o.protocolo)}">`)
      .addTo(camada);
  }
}

function linha(o) {
  const local = o.endereco || (o.latitude != null ? `${o.latitude.toFixed(5)}, ${o.longitude.toFixed(5)}` : "Não informado");
  const acoes = o.status === "pendente_validacao"
    ? `<button type="button" class="acao confirmar" data-acao="confirmar" data-id="${o.id}">Confirmar<span class="sr"> ocorrência ${esc(o.protocolo)}</span></button>
       <button type="button" class="acao rejeitar" data-acao="rejeitar" data-id="${o.id}">Rejeitar<span class="sr"> ocorrência ${esc(o.protocolo)}</span></button>`
    : "";
  return `<tr>
    <td class="protocolo">${esc(o.protocolo)}</td>
    <td><span class="selo ${esc(o.tipo)}">${esc(ROTULO[o.tipo] || o.tipo)}</span></td>
    <td class="local">${esc(local)}</td>
    <td><span class="barra"><span aria-hidden="true"><i style="width:${Math.round(o.confianca * 100)}%"></i></span>${pct(o.confianca)}</span></td>
    <td>${esc(PRIORIDADE[o.prioridade] || o.prioridade)}</td>
    <td><span class="situacao ${esc(o.status)}">${esc(SITUACAO[o.status] || o.status)}</span></td>
    <td>${esc(ORIGEM[o.origem] || o.origem)}</td>
    <td><div class="acoes">${acoes}<a class="acao" href="${esc(o.foto_url)}" target="_blank" rel="noopener">Foto<span class="sr"> da ocorrência ${esc(o.protocolo)}</span></a></div></td>
  </tr>`;
}

carregar();
setInterval(carregar, 5000); // atualiza ao vivo as ocorrências vindas do vídeo e do carrinho
