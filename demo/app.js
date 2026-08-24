const PLAN = [
  {type: 'enhance_sparse_query', title: 'Draft search queries',
   blurb: 'The agent turns your question into database searches. You keep the ones worth running.',
   regenerate: true},
  {type: 'retrieve_sparse_evidence', title: 'Search by query',
   blurb: 'Each chosen query runs against DESTINY, in parallel.'},
  {type: 'generate_concept_filters', title: 'Choose taxonomy concepts',
   blurb: 'A ReAct loop matches your question to the community taxonomy. It asks when it is unsure.'},
  {type: 'retrieve_concept_evidence', title: 'Search by concept',
   blurb: 'A second search, this time over the concepts rather than the words.'},
  {type: 'generate_screening_criteria', title: 'Set screening criteria',
   blurb: 'Inclusion and exclusion rules for everything that came back.',
   regenerate: true},
  {type: 'screen_evidence', title: 'Screen the evidence',
   blurb: 'Every reference is judged against your criteria.'},
  {type: 'generate_map_dimensions', title: 'Choose map dimensions',
   blurb: 'The three axes the map is built from. Edit them however you like.',
   regenerate: true},
  {type: 'generate_map_subtopics', title: 'Fill in subtopics',
   blurb: 'The buckets within each axis. One question per dimension, asked together.',
   regenerate: true},
  {type: 'generate_map', title: 'Place evidence on the map',
   blurb: 'Every included reference gets a coordinate across the three dimensions.'},
];

const STEP = Object.fromEntries(PLAN.map(s => [s.type, s]));
const $ = id => document.getElementById(id);

let session = null;
let ops = {};
let currentId = null;
let map = null;
let mapView = null;
let timer = null;
let startedAt = {};
let answeredAt = {};
let tab = 'run';

/* ---------- api ---------- */

async function api(path, options) {
  const response = await fetch('/api' + path, {
    headers: {'content-type': 'application/json'}, ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || response.statusText));
  }
  return body;
}

const esc = value => String(value ?? '').replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const canon = value => JSON.stringify(value, Object.keys(value ?? {}).sort());

/* ---------- session lifecycle ---------- */

async function start(question, community) {
  session = await api('/sessions/', {
    method: 'POST',
    body: JSON.stringify({workflow: 'evidence_map', question, community}),
  });
  ops = {}; map = null; mapView = null; currentId = null; tab = 'run';
  enter();
  advance();
}

async function openSession(sessionId) {
  session = await api(`/sessions/${sessionId}/`);
  const ids = await api(`/sessions/${sessionId}/operations/`);
  const loaded = await Promise.all(ids.map(id => api(`/operations/${id}/`)));
  ops = {};
  for (const operation of loaded) ops[operation.type] = operation;
  map = null; mapView = null; tab = 'run';
  const live = loaded.reverse().find(o => o.status !== 'complete' && o.status !== 'failed');
  currentId = live ? live.id : null;
  enter();
  if (currentId) poll(); else advance();
  loadMap();
}

function enter() {
  history.replaceState(null, '', `?session=${session.id}`);
  $('start').hidden = true;
  $('app').hidden = false;
  render();
  refreshArtifacts();
}

/* ---------- driving the pipeline ---------- */

const nextStep = () => PLAN.find(step => (ops[step.type] || {}).status !== 'complete');

async function advance() {
  const step = nextStep();
  if (!step) { currentId = null; await loadMap(); render(); return; }
  const existing = ops[step.type];
  if (existing && existing.status !== 'failed') {
    currentId = existing.id;
    if (existing.status === 'awaiting_input') render(); else poll();
    return;
  }
  if (existing) { currentId = existing.id; render(); return; }
  await run(step.type, {});
}

async function run(type, params) {
  try {
    const {id} = await api(`/sessions/${session.id}/operations/`, {
      method: 'POST', body: JSON.stringify({type, params}),
    });
    currentId = id;
    startedAt[id] = Date.now();
    ops[type] = {id, type, status: 'pending', progress: {}, decisions: [], result: null, error: null};
    render();
    poll();
  } catch (error) {
    ops[type] = {id: null, type, status: 'failed', progress: {}, decisions: [],
                 error: {type: 'ClientError', message: error.message}};
    render();
  }
}

async function poll() {
  clearTimeout(timer);
  if (!currentId) return;
  let operation;
  try {
    operation = await api(`/operations/${currentId}/`);
  } catch (error) {
    timer = setTimeout(poll, 2000);
    return;
  }
  ops[operation.type] = operation;
  render();
  if (operation.status === 'pending' || operation.status === 'running') {
    timer = setTimeout(poll, 800);
  } else if (operation.status === 'complete') {
    refreshArtifacts();
    if ($('auto').checked) advance(); else { currentId = null; loadMap(); render(); }
  }
}

async function respond(answers) {
  const operation = await api(`/operations/${currentId}/respond/`, {
    method: 'POST', body: JSON.stringify({answers}),
  });
  answeredAt[operation.id] = Date.now();
  ops[operation.type] = operation;
  render();
  poll();
}

async function retry() {
  const operation = await api(`/operations/${currentId}/retry/`, {method: 'POST'});
  ops[operation.type] = operation;
  poll();
}

async function refreshArtifacts() {
  try {
    const detail = await api(`/sessions/${session.id}/`);
    session = detail;
    renderArtifacts();
  } catch { /* the panel is decoration */ }
}

async function loadMap() {
  try {
    map = await api(`/sessions/${session.id}/map/`);
  } catch { map = null; return; }
  if (!mapView) mapView = {rows: 0, cols: 1, filter: null, cell: null};
  $('tab-map').disabled = false;
  if (nextStep() === undefined && tab === 'run') show('map');
  renderMap();
}

/* ---------- render ---------- */

function render() {
  $('question').textContent = session.question;
  $('sub').innerHTML = [
    `<span>${esc(session.community)}</span>`,
    `<span>v${session.head_version_number}</span>`,
    `<span class="mono">${esc(session.id.slice(0, 8))}</span>`,
  ].join('');
  renderRail();
  if (tab === 'run') renderRun();
}

function renderRail() {
  $('rail').innerHTML = PLAN.map((step, index) => {
    const operation = ops[step.type];
    const status = operation ? operation.status : '';
    const glyph = {complete: '✓', failed: '!', awaiting_input: '?'}[status] || (index + 1);
    return `<li class="s-${status || 'todo'}">
      <span class="pip">${glyph}</span>
      <div>
        <div class="step-name">${esc(step.title)}</div>
        <div class="step-note">${esc(railNote(operation))}</div>
      </div>
    </li>`;
  }).join('');
}

function railNote(operation) {
  if (!operation) return '';
  if (operation.status === 'complete') return summarise(operation.result);
  if (operation.status === 'awaiting_input') return 'waiting on you';
  if (operation.status === 'failed') return 'failed';
  const {done, total, note} = operation.progress || {};
  if (total) return `${note || 'working'} ${done}/${total}`;
  return note || 'working';
}

const summarise = result => !result ? 'done'
  : Object.entries(result).filter(([k]) => k !== 'version')
      .map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(' · ');

function renderRun() {
  const step = nextStep();
  const operation = currentId ? Object.values(ops).find(o => o.id === currentId) : null;
  const parts = [];
  if (operation && step) parts.push(activeCard(STEP[operation.type] || step, operation));
  else if (!step) parts.push(`<div class="card"><div class="card-h"><h2>Mapping complete</h2>
      <span class="tag machine">done</span></div>
      <p class="blurb">Every step has run. The map is on the next tab.</p></div>`);
  parts.push(completed());
  $('view-run').innerHTML = parts.join('');
  wire(operation);
}

function activeCard(step, operation) {
  const status = operation.status;
  const open = (operation.decisions || []).filter(d => d.answer === null);
  const human = status === 'awaiting_input' && open.length;
  const tag = human ? '<span class="tag human">needs you</span>'
    : status === 'failed' ? '<span class="tag bad">failed</span>'
    : status === 'complete' ? '<span class="tag machine">complete</span>'
    : '<span class="tag machine">working</span>';

  const stuck = status === 'pending' && answeredAt[operation.id]
    && Date.now() - answeredAt[operation.id] > 15000;

  let body = '';
  if (human) body = open.map(decision => decisionBlock(decision)).join('') + submitRow(step);
  else if (status === 'failed') body = `<div class="err">${esc((operation.error || {}).type)}: ${esc((operation.error || {}).message)}</div>
      <div class="actions"><button class="btn primary" data-act="retry">Retry</button>
      <button class="btn ghost" data-act="skip">Continue anyway</button></div>`;
  else if (status === 'complete') body = chips(operation.result);
  else body = progress(operation) + (stuck ? stalled() : '');

  return `<div class="card ${human ? 'human' : status === 'failed' ? 'bad' : ''}">
    <div class="card-h"><h2>${esc(step.title)}</h2>${tag}</div>
    <p class="blurb">${esc(step.blurb)}</p>
    <form id="decision-form">${body}</form>
  </div>`;
}

function progress(operation) {
  const {done = 0, total, failed = 0, note = ''} = operation.progress || {};
  const known = total && total > 0;
  const pct = known ? Math.round(100 * done / total) : 0;
  const elapsed = startedAt[operation.id] ? Math.round((Date.now() - startedAt[operation.id]) / 1000) : null;
  return `<div class="bar ${known ? '' : 'indet'}"><i style="width:${known ? pct : 35}%"></i></div>
    <div class="bar-note">
      <span>${esc(note || (operation.status === 'pending' ? 'queued' : 'working'))}${known ? ` — ${done} of ${total}` : ''}${failed ? ` · ${failed} failed` : ''}</span>
      <span>${elapsed === null ? '' : elapsed + 's'}</span>
    </div>`;
}

const stalled = () => `<div class="err" style="margin-top:12px">Still queued after 15 seconds —
    check the worker is up and not busy with another session.
    <div class="actions"><button class="btn ghost" data-act="rerun">Re-run this step</button></div>
  </div>`;

const chips = result => !result ? '' : `<div class="chips">${Object.entries(result)
  .map(([k, v]) => `<span class="chip"><b>${esc(v)}</b> ${esc(k.replace(/_/g, ' '))}</span>`).join('')}</div>`;

function submitRow(step) {
  const regenerate = step.regenerate
    ? `<button type="button" class="btn ghost" data-act="regenerate">Regenerate suggestions</button>` : '';
  return `<div class="actions">
      <button type="button" class="btn primary" data-act="submit">Confirm and continue</button>
      ${regenerate}<span class="err" id="form-error"></span>
    </div>`;
}

function decisionBlock(decision) {
  const constraints = decision.constraints || {};
  const rule = [
    constraints.min ? `at least ${constraints.min}` : '',
    constraints.max ? `at most ${constraints.max}` : '',
    constraints.allow_new ? 'edit or add your own' : '',
  ].filter(Boolean).join(' · ');
  const body = decision.type === 'edit_list' ? editList(decision) : selectMany(decision);
  return `<div class="decision" data-key="${esc(decision.key)}">
    <div class="card-h" style="margin-top:14px"><h3 style="font-size:14px">${esc(decision.prompt)}</h3></div>
    ${rule ? `<div class="hint" style="margin-bottom:8px">${esc(rule)}</div>` : ''}
    ${body}</div>`;
}

function selectMany(decision) {
  const exclusive = (decision.constraints || {}).exclusive || [];
  const preset = !exclusive.length;
  const options = decision.options.map((option, index) => {
    const isExclusive = exclusive.some(e => canon(e) === canon(option.value));
    const mono = /[:()"]|AND|OR/.test(option.label) && option.label.length > 30;
    const max = (decision.constraints || {}).max;
    const on = preset && (max == null || index < max);
    return `<label class="opt ${on ? 'on' : ''}">
      <input type="checkbox" data-kind="check" data-key="${esc(decision.key)}" ${on ? 'checked' : ''}
             data-exclusive="${isExclusive}" data-value='${esc(JSON.stringify(option.value))}'>
      <span class="lbl ${mono ? 'q' : ''}">${esc(option.label)}</span></label>`;
  }).join('');
  return `<div class="opts" data-group="${esc(decision.key)}">${options}</div>`;
}

function editList(decision) {
  const fields = Object.entries((decision.options[0] || {}).value || {})
    .filter(([, v]) => typeof v === 'string').map(([k]) => k);
  const rows = decision.options.map(option => rowHtml(decision.key, option.value, fields)).join('');
  const max = (decision.constraints || {}).max;
  const add = (decision.constraints || {}).allow_new
    ? `<div class="actions"><button type="button" class="btn ghost" data-act="add"
        data-key="${esc(decision.key)}" data-fields='${esc(JSON.stringify(fields))}'
        ${max && decision.options.length >= max ? 'disabled' : ''}>+ Add</button></div>` : '';
  return `<div class="rows" data-rows="${esc(decision.key)}">${rows}</div>${add}`;
}

function rowHtml(key, value, fields) {
  const base = Object.fromEntries(Object.entries(value || {}).filter(([, v]) => typeof v !== 'string'));
  const inputs = fields.map(field => {
    const text = (value || {})[field] ?? '';
    const long = text.length > 60;
    return `<div class="field"><label>${esc(field)}</label>${long
      ? `<textarea data-field="${esc(field)}">${esc(text)}</textarea>`
      : `<input type="text" data-field="${esc(field)}" value="${esc(text)}">`}</div>`;
  }).join('');
  return `<div class="row" data-key="${esc(key)}" data-base='${esc(JSON.stringify(base))}'>
    <div class="fields">${inputs}</div>
    <button type="button" class="icon-btn" data-act="remove">remove</button></div>`;
}

function completed() {
  const done = PLAN.filter(step => (ops[step.type] || {}).status === 'complete');
  if (!done.length) return '';
  return `<div class="done-list"><div class="done-h">Completed</div>${done.map(step =>
    `<div class="done"><span class="tick">✓</span><span class="nm">${esc(step.title)}</span>
      <span class="hint">${esc(summarise(ops[step.type].result))}</span></div>`).join('')}</div>`;
}

/* ---------- form wiring ---------- */

function wire(operation) {
  const form = $('decision-form');
  if (!form || !operation) return;

  form.addEventListener('click', async event => {
    const button = event.target.closest('[data-act]');
    if (!button) return;
    const act = button.dataset.act;
    if (act === 'remove') { button.closest('.row').remove(); return; }
    if (act === 'add') {
      const fields = JSON.parse(button.dataset.fields);
      const container = form.querySelector(`[data-rows="${CSS.escape(button.dataset.key)}"]`);
      container.insertAdjacentHTML('beforeend', rowHtml(button.dataset.key, {}, fields));
      return;
    }
    if (act === 'retry') { await retry(); return; }
    if (act === 'rerun') { await run(operation.type, {}); return; }
    if (act === 'skip') { currentId = null; advance(); return; }
    if (act === 'regenerate') { await run(operation.type, {regenerate: true}); return; }
    if (act === 'submit') await submit(form, operation, button);
  });

  form.addEventListener('change', event => {
    const box = event.target;
    if (box.dataset.kind !== 'check') return;
    box.closest('.opt').classList.toggle('on', box.checked);
    const group = box.closest('.opts');
    if (box.checked) {
      const mine = box.dataset.exclusive === 'true';
      group.querySelectorAll('[data-kind=check]').forEach(other => {
        if (other === box) return;
        if (mine || other.dataset.exclusive === 'true') {
          other.checked = false;
          other.closest('.opt').classList.remove('on');
        }
      });
    }
  });
}

function collect(form, operation) {
  const answers = {};
  for (const decision of operation.decisions.filter(d => d.answer === null)) answers[decision.key] = [];
  form.querySelectorAll('[data-kind=check]').forEach(box => {
    if (box.checked) answers[box.dataset.key].push(JSON.parse(box.dataset.value));
  });
  form.querySelectorAll('.row[data-key]').forEach(row => {
    const record = JSON.parse(row.dataset.base);
    row.querySelectorAll('[data-field]').forEach(input => { record[input.dataset.field] = input.value.trim(); });
    answers[row.dataset.key].push(record);
  });
  return answers;
}

function check(answers, operation) {
  for (const decision of operation.decisions.filter(d => d.answer === null)) {
    const chosen = answers[decision.key];
    const {min = 0, max} = decision.constraints || {};
    if (chosen.length < min) return `${decision.prompt} — pick at least ${min}.`;
    if (max != null && chosen.length > max) return `${decision.prompt} — pick at most ${max}.`;
    if (decision.type === 'edit_list' && chosen.some(r => Object.values(r).some(v => v === '')))
      return 'Every field needs a value.';
  }
  return null;
}

async function submit(form, operation, button) {
  const answers = collect(form, operation);
  const problem = check(answers, operation);
  const error = $('form-error');
  if (problem) { error.textContent = problem; return; }
  button.disabled = true;
  error.textContent = '';
  try {
    await respond(answers);
  } catch (failure) {
    button.disabled = false;
    error.textContent = failure.message;
  }
}

/* ---------- artifacts ---------- */

function renderArtifacts() {
  const artifacts = session.artifacts || {};
  const names = Object.keys(artifacts).sort();
  $('artifacts').innerHTML = names.length
    ? names.map(name => `<button class="artifact" data-artifact="${esc(name)}">
        <span>${esc(name.replace(/_/g, ' '))}</span><span class="v">v${artifacts[name]}</span></button>`).join('')
    : '<div class="hint">none yet</div>';
}

$('artifacts').addEventListener('click', async event => {
  const button = event.target.closest('[data-artifact]');
  if (!button) return;
  const name = button.dataset.artifact;
  const artifact = await api(`/sessions/${session.id}/artifacts/${name}/`);
  $('modal-title').textContent = `${name} · v${artifact.version}`;
  $('modal-body').textContent = JSON.stringify(artifact.payload, null, 2);
  $('modal').hidden = false;
});

$('modal-close').onclick = () => { $('modal').hidden = true; };
$('modal').addEventListener('click', event => { if (event.target.id === 'modal') $('modal').hidden = true; });

/* ---------- map ---------- */

function subtopicsOf(dimension) {
  const declared = dimension.subtopics.map(s => s.name);
  const seen = new Set();
  for (const item of map.mapped_evidence) for (const value of item.coordinate[dimension.name] || []) seen.add(value);
  return declared.concat([...seen].filter(name => !declared.includes(name)));
}

const at = (item, dimension, subtopic) => (item.coordinate[dimension.name] || []).includes(subtopic);

function renderMap() {
  if (!map) { $('view-map').innerHTML = '<div class="empty-state">No map yet.</div>'; return; }
  const dims = map.dimensions;
  const {rows, cols} = mapView;
  const third = [0, 1, 2].find(i => i !== rows && i !== cols);
  const thirdNames = subtopicsOf(dims[third]);
  if (!mapView.filter) mapView.filter = new Set(thirdNames);

  const visible = map.mapped_evidence.filter(item =>
    (item.coordinate[dims[third].name] || []).some(value => mapView.filter.has(value))
    || !(item.coordinate[dims[third].name] || []).length);

  const rowNames = subtopicsOf(dims[rows]);
  const colNames = subtopicsOf(dims[cols]);
  const counts = rowNames.map(r => colNames.map(c =>
    visible.filter(item => at(item, dims[rows], r) && at(item, dims[cols], c)).length));
  const most = Math.max(1, ...counts.flat());
  const filled = counts.flat().filter(n => n > 0).length;

  const axis = (which, selected) => `<div class="control"><label>${which}</label>
    <select data-axis="${which}">${dims.map((d, i) =>
      `<option value="${i}" ${i === selected ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></div>`;

  const table = `<div class="grid-scroll"><table class="map">
    <thead><tr><th>${esc(dims[rows].name)} \\ ${esc(dims[cols].name)}</th>
      ${colNames.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
    <tbody>${rowNames.map((r, i) => `<tr><th>${esc(r)}</th>${colNames.map((c, j) => {
      const count = counts[i][j];
      const size = 16 + 30 * Math.sqrt(count / most);
      const selected = mapView.cell && mapView.cell[0] === i && mapView.cell[1] === j;
      return `<td><button class="cell ${selected ? 'sel' : ''} ${count ? '' : 'empty'}" data-cell="${i},${j}">
        ${count ? `<span class="bubble" style="width:${size}px;height:${size}px">${count}</span>`
                : '<span class="gap">·</span>'}</button></td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>`;

  $('view-map').innerHTML = `
    <div class="map-controls">
      ${axis('rows', rows)}${axis('columns', cols)}
      <div class="control"><label>${esc(dims[third].name)}</label>
        <div class="filters">${thirdNames.map(name =>
          `<button class="f-chip ${mapView.filter.has(name) ? 'on' : ''}" data-filter="${esc(name)}">${esc(name)}</button>`).join('')}</div>
      </div>
    </div>
    <div class="chips" style="margin-bottom:14px">
      <span class="chip"><b>${visible.length}</b> papers shown</span>
      <span class="chip"><b>${filled}</b> of ${rowNames.length * colNames.length} cells covered</span>
      <span class="chip"><b>${rowNames.length * colNames.length - filled}</b> gaps</span>
    </div>
    ${table}
    <div class="papers" id="papers"></div>`;

  renderPapers(visible, rowNames, colNames, dims);
}

function renderPapers(visible, rowNames, colNames, dims) {
  const target = $('papers');
  if (!mapView.cell) { target.innerHTML = '<div class="hint" style="margin-top:14px">Pick a cell to read what is in it.</div>'; return; }
  const [i, j] = mapView.cell;
  const items = visible.filter(item =>
    at(item, dims[mapView.rows], rowNames[i]) && at(item, dims[mapView.cols], colNames[j]));
  target.innerHTML = `<div class="done-h">${esc(rowNames[i])} × ${esc(colNames[j])} — ${items.length} paper${items.length === 1 ? '' : 's'}</div>`
    + (items.length ? items.map(paper).join('')
       : '<div class="hint">Nothing here. That is the point of a gap map.</div>');
}

function paper({evidence, coordinate}) {
  const authors = (evidence.authors || []).slice(0, 3).join(', ')
    + ((evidence.authors || []).length > 3 ? ` +${evidence.authors.length - 3}` : '');
  const link = (evidence.landing_page_urls || [])[0] || (evidence.pdf_urls || [])[0];
  const doi = (evidence.external_identifiers || []).find(id => (id.identifier_type || '') === 'doi');
  const meta = [authors, evidence.year, evidence.publisher, doi && doi.identifier].filter(Boolean);
  return `<div class="paper">
    <div class="t">${link ? `<a href="${esc(link)}" target="_blank" rel="noreferrer">${esc(evidence.title || 'untitled')}</a>`
                          : esc(evidence.title || 'untitled')}</div>
    ${meta.length ? `<div class="m">${meta.map(m => `<span>${esc(m)}</span>`).join('')}</div>` : ''}
    <div class="coord">${Object.entries(coordinate).map(([dimension, values]) =>
      `<span><b>${esc(dimension)}</b> ${esc(values.join(', '))}</span>`).join('')}</div>
  </div>`;
}

$('view-map').addEventListener('click', event => {
  const cell = event.target.closest('[data-cell]');
  if (cell) {
    const [i, j] = cell.dataset.cell.split(',').map(Number);
    const same = mapView.cell && mapView.cell[0] === i && mapView.cell[1] === j;
    mapView.cell = same ? null : [i, j];
    renderMap();
    return;
  }
  const chip = event.target.closest('[data-filter]');
  if (chip) {
    const name = chip.dataset.filter;
    mapView.filter.has(name) ? mapView.filter.delete(name) : mapView.filter.add(name);
    renderMap();
  }
});

$('view-map').addEventListener('change', event => {
  const select = event.target.closest('[data-axis]');
  if (!select) return;
  const chosen = Number(select.value);
  const which = select.dataset.axis === 'rows' ? 'rows' : 'cols';
  const other = which === 'rows' ? 'cols' : 'rows';
  if (mapView[other] === chosen) mapView[other] = mapView[which];
  mapView[which] = chosen;
  mapView.filter = null;
  mapView.cell = null;
  renderMap();
});

/* ---------- tabs and chrome ---------- */

function show(which) {
  tab = which;
  $('tab-run').classList.toggle('on', which === 'run');
  $('tab-map').classList.toggle('on', which === 'map');
  $('view-run').hidden = which !== 'run';
  $('view-map').hidden = which !== 'map';
  if (which === 'run') renderRun(); else renderMap();
}

$('tab-run').onclick = () => show('run');
$('tab-map').onclick = () => show('map');
$('new-session').onclick = () => { clearTimeout(timer); location.reload(); };

$('go').onclick = async () => {
  const question = $('q').value.trim() || $('q').placeholder;
  $('go').disabled = true;
  $('start-hint').textContent = 'starting…';
  try {
    await start(question, $('community').value);
  } catch (error) {
    $('go').disabled = false;
    $('start-hint').textContent = error.message;
  }
};

(async function boot() {
  const deepLink = new URLSearchParams(location.search).get('session');
  if (deepLink) {
    try { await openSession(deepLink); return; }
    catch (error) { $('start-hint').textContent = error.message; }
  }
  try {
    const sessions = await api('/sessions/');
    if (!sessions.length) return;
    $('recent').hidden = false;
    $('recent-list').innerHTML = sessions.slice(0, 6).map(s =>
      `<button data-session="${esc(s.id)}">${esc(s.question.slice(0, 90))}
        <div class="when">${esc(s.community)} · v${s.head_version_number} · ${new Date(s.created_at).toLocaleString()}</div></button>`).join('');
    $('recent-list').onclick = event => {
      const button = event.target.closest('[data-session]');
      if (button) openSession(button.dataset.session);
    };
  } catch (error) {
    $('start-hint').textContent = `${error.message} — is the API running?`;
  }
})();
