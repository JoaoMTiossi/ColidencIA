/* ColidencIA — Frontend Application */
'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  carteiraUploadId: null,
  rpiUploadId: null,
  execucaoId: null,
  despachos: {},         // {codigo: {nome, total, com_nome, tipo_acao, relevante}}
  despachosTotal: 0,     // total de marcas das checkboxes marcadas
  resultados: [],        // página atual
  filtros: { tipo_acao: '', classificacao: '' },
  pagina: 1,
  totalResultados: 0,
  totalPaginas: 1,
  pollInterval: null,
  timerInterval: null,
  timerStart: null,
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);
const show = el => { if (el) el.style.display = ''; };
const hide = el => { if (el) el.style.display = 'none'; };

function toast(msg, type = 'info', duration = 4000) {
  const c = $('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
function setupUploadZone(zoneId, inputId, tipo) {
  const zone = $(zoneId);
  const input = $(inputId);
  if (!zone || !input) return;

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f, tipo);
  });
  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(input.files[0], tipo);
  });
}

async function handleFile(file, tipo) {
  const ext = tipo === 'carteira' ? '.xlsx' : '.xml';
  if (!file.name.toLowerCase().endsWith(ext)) {
    toast(`Arquivo inválido. Esperado: ${ext}`, 'error');
    return;
  }

  const zoneId = tipo === 'carteira' ? 'zone-carteira' : 'zone-rpi';
  const zone = $(zoneId);
  zone.querySelector('.upload-icon').textContent = '⏳';
  zone.querySelector('.upload-label').textContent = 'Enviando...';

  const fd = new FormData();
  fd.append('file', file);

  try {
    const endpoint = tipo === 'carteira' ? '/api/upload/carteira' : '/api/upload/rpi';
    const resp = await fetch(endpoint, { method: 'POST', body: fd });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || 'Erro no upload');
    }
    const data = await resp.json();

    if (tipo === 'carteira') {
      state.carteiraUploadId = data.upload_id;
      renderUploadSuccess(zone, file.name, data.tamanho_bytes, null);
    } else {
      state.rpiUploadId = data.upload_id;
      renderDespachos(data.despachos_disponiveis, data.rpi_numero, data.rpi_data);
      renderUploadSuccess(zone, file.name, data.tamanho_bytes, `RPI ${data.rpi_numero} — ${data.rpi_data}`);
    }
    updateBtnExecutar();
  } catch (e) {
    zone.querySelector('.upload-icon').textContent = tipo === 'carteira' ? '📊' : '📄';
    zone.querySelector('.upload-label').textContent = tipo === 'carteira' ? 'Selecione o Excel da Carteira' : 'Selecione o XML da RPI';
    toast(e.message, 'error');
  }
}

function renderUploadSuccess(zone, filename, bytes, extra) {
  zone.classList.add('success');
  zone.querySelector('.upload-icon').textContent = '✅';
  zone.querySelector('.upload-label').textContent = filename;
  const hint = zone.querySelector('.upload-hint');
  hint.textContent = `${(bytes / 1024).toFixed(0)} KB`;
  let info = zone.querySelector('.upload-info');
  if (!info) {
    info = document.createElement('div');
    info.className = 'upload-info';
    zone.appendChild(info);
  }
  info.textContent = extra || '';
  if (!extra) info.style.display = 'none';
}

// ---------------------------------------------------------------------------
// Despachos
// ---------------------------------------------------------------------------
function renderDespachos(lista, rpiNumero, rpiData) {
  const container = $('despachos-container');
  if (!container) return;

  show($('config-card'));
  container.innerHTML = '';
  state.despachos = {};

  const grupos = {
    OPOSICAO: { label: '🟢 OPOSIÇÃO (prazo 60 dias)', itens: [] },
    PAN: { label: '🟡 PAN (prazo 180 dias)', itens: [] },
    OUTRO: { label: '⚪ Outros', itens: [] },
  };

  lista.forEach(d => {
    state.despachos[d.codigo] = d;
    const g = grupos[d.tipo_acao] || grupos['OUTRO'];
    g.itens.push(d);
  });

  for (const [tipo, grupo] of Object.entries(grupos)) {
    if (!grupo.itens.length) continue;

    const grpDiv = document.createElement('div');
    grpDiv.className = 'despacho-group';

    const title = document.createElement('div');
    title.className = 'despacho-group-title';
    title.textContent = grupo.label;
    grpDiv.appendChild(title);

    grupo.itens.forEach(d => {
      if (!d.relevante) return;
      const item = document.createElement('div');
      item.className = 'despacho-item';

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = `cb-${d.codigo}`;
      cb.value = d.codigo;
      cb.checked = d.relevante;
      cb.addEventListener('change', atualizarTotalMarcas);

      const lbl = document.createElement('label');
      lbl.htmlFor = `cb-${d.codigo}`;
      lbl.textContent = `${d.codigo} — ${d.nome}`;

      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = `${d.com_nome.toLocaleString('pt-BR')} marcas`;

      item.appendChild(cb);
      item.appendChild(lbl);
      item.appendChild(badge);
      grpDiv.appendChild(item);
    });

    container.appendChild(grpDiv);
  }

  atualizarTotalMarcas();
}

function atualizarTotalMarcas() {
  const cbs = document.querySelectorAll('#despachos-container input[type=checkbox]:checked');
  let total = 0;
  cbs.forEach(cb => {
    const d = state.despachos[cb.value];
    if (d) total += d.com_nome || 0;
  });
  state.despachosTotal = total;
  const el = $('total-marcas');
  if (el) el.textContent = `${total.toLocaleString('pt-BR')} marcas serão analisadas`;
}

function getDespachosSelecionados() {
  return Array.from(
    document.querySelectorAll('#despachos-container input[type=checkbox]:checked')
  ).map(cb => cb.value);
}

// ---------------------------------------------------------------------------
// Executar pipeline
// ---------------------------------------------------------------------------
function updateBtnExecutar() {
  const btn = $('btn-executar');
  if (!btn) return;
  btn.disabled = !(state.carteiraUploadId && state.rpiUploadId);
}

async function executar() {
  const btn = $('btn-executar');
  btn.disabled = true;
  btn.textContent = 'Executando...';

  const despachos = getDespachosSelecionados();
  if (!despachos.length) {
    toast('Selecione ao menos um despacho para analisar', 'error');
    btn.disabled = false;
    btn.textContent = '▶ Executar Análise';
    return;
  }

  try {
    const resp = await fetch('/api/executar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        carteira_upload_id: state.carteiraUploadId,
        rpi_upload_id: state.rpiUploadId,
        despachos_selecionados: despachos,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao iniciar pipeline');
    }
    const data = await resp.json();
    state.execucaoId = data.execucao_id;

    show($('area-progresso'));
    hide($('area-resultados'));
    iniciarTimer();
    iniciarPolling();
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.textContent = '▶ Executar Análise';
  }
}

// ---------------------------------------------------------------------------
// Polling de status
// ---------------------------------------------------------------------------
function iniciarPolling() {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(verificarStatus, 1500);
}

async function verificarStatus() {
  if (!state.execucaoId) return;
  try {
    const resp = await fetch(`/api/status/${state.execucaoId}`);
    const data = await resp.json();

    atualizarProgresso(data);

    if (data.status === 'concluido') {
      clearInterval(state.pollInterval);
      clearInterval(state.timerInterval);
      await carregarResultados();
    } else if (data.status === 'erro') {
      clearInterval(state.pollInterval);
      clearInterval(state.timerInterval);
      toast(`Erro no pipeline: ${data.erro_msg || 'desconhecido'}`, 'error', 8000);
      $('btn-executar').disabled = false;
      $('btn-executar').textContent = '▶ Executar Análise';
    }
  } catch (e) {
    console.error('Polling error:', e);
  }
}

function atualizarProgresso(data) {
  const pct = Math.max(0, Math.min(100, data.percentual || 0));
  const fill = $('progress-fill');
  if (fill) fill.style.width = `${pct}%`;

  const msg = $('progress-message');
  if (msg) msg.textContent = data.mensagem || '...';

  const pctEl = $('progress-pct');
  if (pctEl) pctEl.textContent = `${pct}%`;
}

// ---------------------------------------------------------------------------
// Timer
// ---------------------------------------------------------------------------
function iniciarTimer() {
  state.timerStart = Date.now();
  if (state.timerInterval) clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    const seg = Math.floor((Date.now() - state.timerStart) / 1000);
    const el = $('progress-timer');
    if (el) el.textContent = formatTime(seg);
  }, 1000);
}

function formatTime(seg) {
  const m = Math.floor(seg / 60);
  const s = seg % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Resultados
// ---------------------------------------------------------------------------
async function carregarResultados(pagina = 1) {
  state.pagina = pagina;
  const { tipo_acao, classificacao } = state.filtros;
  const params = new URLSearchParams({ page: pagina, per_page: 50 });
  if (tipo_acao) params.set('tipo_acao', tipo_acao);
  if (classificacao) params.set('classificacao', classificacao);

  try {
    const resp = await fetch(`/api/resultados/${state.execucaoId}?${params}`);
    const data = await resp.json();

    state.resultados = data.resultados;
    state.totalResultados = data.total;
    state.totalPaginas = data.pages;

    show($('area-resultados'));
    renderResumo(data.resumo);
    renderTabela(data.resultados);
    renderPaginacao(data.page, data.pages, data.total);

    $('btn-executar').disabled = false;
    $('btn-executar').textContent = '▶ Executar Nova Análise';
    toast(`Análise concluída: ${data.resumo.alertas_total} alertas encontrados`, 'success');

    carregarHistorico();
  } catch (e) {
    toast('Erro ao carregar resultados', 'error');
  }
}

function renderResumo(resumo) {
  $('num-alta').textContent = resumo.alertas_alta || 0;
  $('num-media').textContent = resumo.alertas_media || 0;
  $('num-baixa').textContent = resumo.alertas_baixa || 0;
  $('num-oposicao').textContent = resumo.alertas_oposicao || 0;
  $('num-pan').textContent = resumo.alertas_pan || 0;
  $('num-total').textContent = resumo.alertas_total || 0;

  // Links para download
  const baseUrl = `/api/resultados/${state.execucaoId}/download`;
  $('dl-xlsx').href = `${baseUrl}/xlsx`;
  $('dl-csv').href = `${baseUrl}/csv`;
}

function renderTabela(resultados) {
  const tbody = $('tabela-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!resultados.length) {
    tbody.innerHTML = '<tr><td colspan="12" class="empty-state">Nenhum resultado encontrado com os filtros selecionados.</td></tr>';
    return;
  }

  resultados.forEach((r, i) => {
    const tr = document.createElement('tr');
    const score = r.score_final ?? r.score_nome ?? 0;
    const scorePct = Math.round(score * 100);
    const scoreColor = score >= 0.8 ? '#dc2626' : score >= 0.65 ? '#d97706' : '#16a34a';

    const tipoLabel = r.tipo_acao === 'OPOSICAO' ? 'OPOSIÇÃO' : 'PAN';
    const tipoCls = r.tipo_acao === 'OPOSICAO' ? 'badge-oposicao' : 'badge-pan';
    const classCls = `badge-${(r.classificacao || 'baixa').toLowerCase()}`;

    tr.innerHTML = `
      <td>${r.id || (state.pagina - 1) * 50 + i + 1}</td>
      <td><span class="badge-class ${tipoCls}">${tipoLabel}</span></td>
      <td><span class="badge-class ${classCls}">${r.classificacao || '-'}</span></td>
      <td>
        <div class="score-bar">
          <span class="score-val" style="color:${scoreColor}">${scorePct}%</span>
          <div class="score-track"><div class="score-fill" style="width:${scorePct}%;background:${scoreColor}"></div></div>
        </div>
      </td>
      <td><strong>${esc(r.marca_base)}</strong><br><small>NCL ${r.ncl_base || '?'}</small></td>
      <td><strong>${esc(r.marca_rpi)}</strong><br><small>NCL ${r.ncl_rpi || '?'}</small></td>
      <td>${esc(r.despacho_codigo || '')} <small>${esc(r.processo_rpi || '')}</small></td>
      <td style="max-width:180px">${esc((r.titular_rpi || '').substring(0, 60))}</td>
      <td class="justificativa-cell">${esc(r.justificativa_ia || '')}</td>
      <td>${r.camada_deteccao ?? '-'}</td>
      <td><small>${esc((r.spec_base || '').substring(0, 80))}</small></td>
      <td><small>${esc((r.spec_rpi || '').substring(0, 80))}</small></td>
    `;
    tbody.appendChild(tr);
  });
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderPaginacao(pagina, total, count) {
  const el = $('paginacao');
  if (!el) return;
  el.innerHTML = '';

  if (total <= 1) return;

  const add = (lbl, pg, disabled = false, active = false) => {
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (active ? ' active' : '');
    btn.textContent = lbl;
    btn.disabled = disabled;
    btn.addEventListener('click', () => carregarResultados(pg));
    el.appendChild(btn);
  };

  add('«', 1, pagina === 1);
  add('‹', pagina - 1, pagina === 1);

  const start = Math.max(1, pagina - 2);
  const end = Math.min(total, pagina + 2);
  for (let p = start; p <= end; p++) {
    add(p, p, false, p === pagina);
  }

  add('›', pagina + 1, pagina === total);
  add('»', total, pagina === total);

  const info = document.createElement('span');
  info.style.cssText = 'color:var(--color-muted);font-size:12px;margin-left:8px';
  info.textContent = `${count} resultados`;
  el.appendChild(info);
}

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------
function aplicarFiltros() {
  state.filtros.tipo_acao = $('filtro-tipo').value;
  state.filtros.classificacao = $('filtro-class').value;
  carregarResultados(1);
}

// ---------------------------------------------------------------------------
// Histórico
// ---------------------------------------------------------------------------
async function carregarHistorico() {
  try {
    const resp = await fetch('/api/historico');
    const data = await resp.json();
    renderHistorico(data.execucoes);
  } catch (e) {
    console.error('Histórico error:', e);
  }
}

function renderHistorico(execucoes) {
  const el = $('historico-lista');
  if (!el) return;
  el.innerHTML = '';

  if (!execucoes.length) {
    el.innerHTML = '<div class="empty-state">Nenhuma execução anterior</div>';
    return;
  }

  execucoes.forEach(e => {
    const div = document.createElement('div');
    div.className = 'historico-item';

    const data = e.data_execucao ? new Date(e.data_execucao).toLocaleString('pt-BR') : '-';
    const statusEmoji = e.status === 'concluido' ? '✅' : e.status === 'erro' ? '❌' : '⏳';

    div.innerHTML = `
      <div class="hist-rpi">${statusEmoji} RPI ${e.numero_rpi || '-'} <span style="font-weight:400;color:var(--color-muted)">(${e.data_rpi || '-'})</span></div>
      <div class="hist-date">${data}</div>
      <div class="hist-stats">
        ${e.alertas_total ?? 0} alertas
        ${e.alertas_oposicao ? `· ${e.alertas_oposicao} oposição` : ''}
        ${e.alertas_pan ? `· ${e.alertas_pan} PAN` : ''}
        ${e.tempo_execucao_seg ? `· ${e.tempo_execucao_seg}s` : ''}
      </div>
      <div class="hist-actions">
        <button class="hist-btn" onclick="verExecucao(${e.id})">Ver</button>
        <a class="hist-btn" href="/api/resultados/${e.id}/download/xlsx" download>XLSX</a>
        <a class="hist-btn" href="/api/resultados/${e.id}/download/csv" download>CSV</a>
        <button class="hist-btn danger" onclick="deletarExecucao(${e.id})">🗑</button>
      </div>
    `;
    el.appendChild(div);
  });
}

async function verExecucao(id) {
  state.execucaoId = id;
  await carregarResultados(1);
  window.scrollTo({ top: $('area-resultados').offsetTop - 20, behavior: 'smooth' });
}

async function deletarExecucao(id) {
  if (!confirm('Remover esta execução e seus dados?')) return;
  try {
    await fetch(`/api/execucao/${id}`, { method: 'DELETE' });
    toast('Execução removida', 'success');
    carregarHistorico();
  } catch (e) {
    toast('Erro ao remover', 'error');
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  setupUploadZone('zone-carteira', 'input-carteira', 'carteira');
  setupUploadZone('zone-rpi', 'input-rpi', 'rpi');

  const btnExecutar = $('btn-executar');
  if (btnExecutar) btnExecutar.addEventListener('click', executar);

  const filtroTipo = $('filtro-tipo');
  const filtroClass = $('filtro-class');
  if (filtroTipo) filtroTipo.addEventListener('change', aplicarFiltros);
  if (filtroClass) filtroClass.addEventListener('change', aplicarFiltros);

  carregarHistorico();
  hide($('config-card'));
});
