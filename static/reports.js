// reports.js — program-team Reports page (/reports). Vanilla ES module, no build step.
// API: /api/reports/* with header X-Reports-Key (CONTRACT.md "REPORTS"). The access code lives in sessionStorage
// (this tab only). Every DOM node is built with createElement/textContent — report data is never parsed as HTML.
import { t, applyI18n, mountLangSwitch, onLangChange, locale } from './i18n.js';

const SS_KEY = 'reports.key';
const LIMIT = 25;
const API = '/api/reports';

// sessionStorage can throw (private mode, blocked storage): log it with context; the code then lives in memory only.
function ssGet(k) {
  try { return window.sessionStorage.getItem(k); } catch (err) { console.warn(`[reports] sessionStorage read failed (${k})`, err); return null; }
}
function ssSet(k, v) { try { window.sessionStorage.setItem(k, v); } catch (err) { console.warn(`[reports] sessionStorage write failed (${k}); keeping the code in memory`, err); } }
function ssDel(k) { try { window.sessionStorage.removeItem(k); } catch (err) { console.warn(`[reports] sessionStorage delete failed (${k})`, err); } }

let accessKey = ssGet(SS_KEY) || '';
const state = {
  filters: { mode: '', school: '', from: '', to: '' },
  schools: { sort: 'name', dir: 'asc', offset: 0 },
  sessionsOffset: 0, progressOffset: 0, studentsOffset: 0,
};
let renderSeq = 0;

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ tiny DOM helper
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style') e.setAttribute('style', v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : String(c));
  return e;
}

// ------------------------------------------------------------------ formatting
const nf = (n, d = 0) => Number(n).toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
const int = (n) => nf(n || 0);
const rate = (r) => `${nf((r || 0) * 100, 1)}%`;
const scorePct = (v) => (v === null || v === undefined ? '–' : `${nf(v, 1)}%`);
function fmtDate(iso) {
  if (!iso) return '–';
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: 'numeric' });
}
const typeLabel = (type) => ({ live: t('rp_type_live'), homework: t('rp_type_homework'), 'one-screen': t('rp_type_one') }[type] || type);
const schoolLabel = (s) => (s === '(not set)' ? t('rp_school_not_set') : s);

// ------------------------------------------------------------------ API
class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

function qs(params) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== '' && v !== null && v !== undefined) u.set(k, v);
  const s = u.toString();
  return s ? `?${s}` : '';
}

async function request(path, params, keyOverride) {
  let r;
  try {
    r = await fetch(API + path + qs(params), { headers: { 'X-Reports-Key': keyOverride ?? accessKey } });
  } catch {
    throw new ApiError(0, t('rp_error'));
  }
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, detail);
  }
  return r;
}

async function api(path, params) {
  try {
    return await (await request(path, params)).json();
  } catch (e) {
    if (e.status === 503) showNotConfigured();
    else if (e.status === 401 || e.status === 429) signOut(e.status === 429 ? 'rp_too_many' : 'rp_code_expired');
    throw e;
  }
}

async function downloadCsv(path, params) {
  setStatus(t('rp_loading'));
  try {
    const r = await request(path, { ...params, format: 'csv' });
    const blob = await r.blob();
    const m = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '');
    const name = m ? m[1] : 'report.csv';
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: name, hidden: true });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    setStatus(t('rp_downloaded', { name }));
  } catch (e) {
    if (e.status === 503) { showNotConfigured(); return; }
    if (e.status === 401 || e.status === 429) signOut(e.status === 429 ? 'rp_too_many' : 'rp_code_expired');
    setStatus(t('rp_error'));
  }
}

function csvButton(path, params, label) {
  return h('button', { type: 'button', class: 'rp-btn rp-btn-secondary rp-btn-sm', onclick: () => downloadCsv(path, params) },
    h('span', { 'aria-hidden': 'true', text: '⬇ ' }), label ? `${t('rp_download')}: ${label}` : t('rp_download'));
}

// ------------------------------------------------------------------ gate
function showGate(msgKey) {
  $('gate').hidden = false;
  $('app').hidden = true;
  $('signout').hidden = true;
  const err = $('gate-err');
  err.textContent = msgKey ? t(msgKey) : '';
  $('code').setAttribute('aria-invalid', msgKey ? 'true' : 'false');
}

// REPORTS_KEY is not set on the server (every /api/reports/* call is 503): say so plainly and lock the form, so
// nobody keeps guessing a code that cannot work.
let notConfigured = false;
function showNotConfigured() {
  notConfigured = true;
  accessKey = '';
  ssDel(SS_KEY);
  showGate('rp_not_configured');
  $('code').disabled = true;
  $('gate-form').querySelector('button[type="submit"]').disabled = true;
}

async function checkConfigured() {
  let r;
  try { r = await fetch(`${API}/status`); } catch (err) { console.warn('[reports] status probe failed (network)', err); return; }
  if (r.status === 503) showNotConfigured();
}

function signOut(msgKey) {
  accessKey = '';
  ssDel(SS_KEY);
  showGate(msgKey);
  $('code').value = '';
  $('code').focus();
}

async function onGateSubmit(ev) {
  ev.preventDefault();
  const code = $('code').value.trim();
  if (!code) { showGate('rp_code_empty'); $('code').focus(); return; }
  const btn = ev.submitter || $('gate-form').querySelector('button');
  btn.disabled = true;
  try {
    await request('/summary', {}, code);
    accessKey = code;
    ssSet(SS_KEY, code);
    $('code').value = '';
    $('gate-err').textContent = '';
    await render({ focus: true });
  } catch (e) {
    if (e.status === 503) { showNotConfigured(); return; }
    showGate(e.status === 429 ? 'rp_too_many' : e.status === 401 ? 'rp_code_wrong' : 'rp_error');
    $('code').focus();
  } finally {
    if (!notConfigured) btn.disabled = false;
  }
}

// ------------------------------------------------------------------ routing
function route() {
  const parts = (location.hash.replace(/^#\/?/, '') || '').split('/').filter(Boolean).map((p) => {
    try { return decodeURIComponent(p); } catch { return p; }
  });
  if (parts[0] === 'school' && parts[1]) return { view: parts[2] === 'progress' ? 'progress' : 'sessions', school: parts[1] };
  if (parts[0] === 'session' && parts[1] && parts[2]) return { view: 'session', kind: parts[1], id: parts[2], school: parts[3] || '' };
  return { view: 'overview' };
}
const schoolHref = (s, tab) => `#/school/${encodeURIComponent(s)}${tab === 'progress' ? '/progress' : ''}`;
const sessionHref = (kind, id, school) => `#/session/${kind}/${id}/${encodeURIComponent(school || '')}`;

function crumbs(r) {
  const items = [[t('rp_overview'), '#/']];
  if (r.school) items.push([schoolLabel(r.school), schoolHref(r.school)]);
  if (r.view === 'progress') items.push([t('rp_tab_progress'), null]);
  if (r.view === 'session') items.push([t('rp_session'), null]);
  const ol = h('ol');
  items.forEach(([label, href], i) => {
    const last = i === items.length - 1;
    ol.append(h('li', {}, last ? h('span', { 'aria-current': 'page', text: label }) : h('a', { href, text: label })));
  });
  $('crumbs').replaceChildren(ol);
}

function setStatus(msg) { $('status').textContent = msg; }

// ------------------------------------------------------------------ filters
function filterParams({ withSchool = true } = {}) {
  const f = state.filters;
  return { mode: f.mode, school: withSchool ? f.school : '', from: f.from, to: f.to };
}

function readFilters() {
  state.filters = {
    mode: $('f-mode').value, school: $('f-school').value.trim(),
    from: $('f-from').value, to: $('f-to').value,
  };
  state.schools.offset = 0;
  state.sessionsOffset = 0;
  state.progressOffset = 0;
}

// ------------------------------------------------------------------ building blocks
function sectionLabel(text) { return h('p', { class: 'rp-label', text }); }

function card(titleText, id, ...kids) {
  // An actions row (Download CSV…) given anywhere in kids goes into the card header, next to the title.
  const actions = kids.filter((k) => k && k.classList && k.classList.contains('rp-card-actions'));
  const rest = kids.filter((k) => !actions.includes(k));
  // A plain div (not a <section> landmark): the table inside is the named, scrollable region.
  return h('div', { class: 'rp-card', 'data-card': id },
    h('div', { class: 'rp-card-head' }, h('h2', { id, class: 'rp-h2', text: titleText }), ...actions), ...rest);
}

function kpiCard(label, value, sub) {
  return h('div', { class: 'rp-kpi rp-card' },
    h('p', { class: 'rp-label', text: label }),
    h('p', { class: 'rp-kpi-num', text: value }),
    sub ? h('p', { class: 'rp-muted rp-kpi-sub', text: sub }) : null);
}

/** Scrollable table wrapper (keyboard-focusable region, so wide tables never scroll the page). */
function tableWrap(label, table) {
  return h('div', { class: 'rp-table-wrap', role: 'region', 'aria-label': label, tabindex: '0' }, table);
}

function simpleTable(caption, cols, rows) {
  // cols: [{label, num?}], rows: [[cells]] — first cell is the row header (th scope=row).
  const thead = h('thead', {}, h('tr', {}, cols.map((c) => h('th', { scope: 'col', class: c.num ? 'rp-num' : null, text: c.label }))));
  const tbody = h('tbody', {}, rows.map((r) => h('tr', {}, r.map((cell, i) => {
    const attrs = { class: cols[i] && cols[i].num ? 'rp-num' : null };
    return i === 0 ? h('th', { scope: 'row', ...attrs }, cell) : h('td', attrs, cell);
  }))));
  return h('table', { class: 'rp-table' }, h('caption', { class: 'rp-sr', text: caption }), thead, tbody);
}

function pager(total, offset, limit, onPage) {
  if (total <= limit) return null;
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + limit, total);
  return h('nav', { class: 'rp-pager', 'aria-label': t('rp_page', { from, to, n: total }) },
    h('button', { type: 'button', class: 'rp-btn rp-btn-ghost rp-btn-sm', disabled: offset <= 0 ? true : null,
      onclick: () => onPage(Math.max(0, offset - limit)) }, t('rp_prev')),
    h('span', { class: 'rp-muted', text: t('rp_page', { from: int(from), to: int(to), n: int(total) }) }),
    h('button', { type: 'button', class: 'rp-btn rp-btn-ghost rp-btn-sm', disabled: to >= total ? true : null,
      onclick: () => onPage(offset + limit) }, t('rp_next')));
}

function bar(fraction, variant) {
  const pct = Math.max(0, Math.min(100, (fraction || 0) * 100));
  return h('span', { class: `rp-bar${variant ? ` rp-bar-${variant}` : ''}`, 'aria-hidden': 'true' },
    h('span', { class: 'rp-bar-fill', style: `width:${pct.toFixed(1)}%` }));
}

// ------------------------------------------------------------------ views
async function viewOverview(seq) {
  const params = filterParams();
  const sp = { ...state.schools };
  const [sum, sch] = await Promise.all([
    api('/summary', params),
    api('/schools', { ...params, sort: sp.sort, dir: sp.dir, limit: LIMIT, offset: sp.offset }),
  ]);
  if (seq !== renderSeq) return null;
  const range = sum.date_range.from ? `${fmtDate(sum.date_range.from)} – ${fmtDate(sum.date_range.to)}` : '–';
  const kpis = h('div', { class: 'rp-kpis' },
    kpiCard(t('rp_kpi_sessions'), int(sum.sessions), t('rp_kpi_sessions_sub', { live: int(sum.live_games), hw: int(sum.homework_games), cls: int(sum.class_sessions) })),
    kpiCard(t('rp_kpi_schools'), int(sum.schools), sum.sessions_school_not_set ? t('rp_kpi_schools_sub', { n: int(sum.sessions_school_not_set) }) : null),
    kpiCard(t('rp_kpi_participants'), int(sum.participants), t('rp_kpi_participants_sub')),
    kpiCard(t('rp_kpi_participation'), rate(sum.participation_rate), t('rp_kpi_participation_sub', { n: int(sum.participated) })),
    kpiCard(t('rp_kpi_completion'), rate(sum.completion_rate), t('rp_kpi_completion_sub', { n: int(sum.completed), m: int(sum.joined) })),
    kpiCard(t('rp_kpi_score'), scorePct(sum.avg_score_pct), t('rp_kpi_score_sub')),
  );

  const stepName = { joined: t('rp_step_joined'), answered: t('rp_step_answered'), completed: t('rp_step_completed') };
  const funnel = card(t('rp_funnel'), 'h-funnel',
    h('p', { class: 'rp-muted', text: t('rp_funnel_sub') }),
    h('ol', { class: 'rp-funnel' }, sum.funnel.map((s, i) => h('li', { class: 'rp-funnel-row' },
      h('span', { class: 'rp-funnel-label', text: stepName[s.step] || s.step }),
      bar(s.pct, i === 0 ? null : i === 1 ? 'mid' : 'end'),
      h('span', { class: 'rp-funnel-val', text: `${int(s.count)} (${rate(s.pct)})` })))));

  const schools = card(t('rp_schools'), 'h-schools',
    h('div', { class: 'rp-card-actions' }, csvButton('/schools', { ...params, sort: sp.sort, dir: sp.dir }, t('rp_schools')),
      csvButton('/summary', params, t('rp_kpi_totals'))),
    sch.items.length ? tableWrap(t('rp_schools'), schoolsTable(sch)) : h('p', { class: 'rp-muted', text: t('rp_no_data') }),
    pager(sch.total, sch.offset, LIMIT, (off) => { state.schools.offset = off; render({ focusId: 'h-schools' }); }));

  return [
    sectionLabel(t('rp_program_overview')),
    h('h1', { class: 'rp-h1', tabindex: '-1', text: t('rp_program_overview') }),
    h('p', { class: 'rp-muted rp-range' }, h('span', { class: 'rp-label rp-inline', text: t('rp_kpi_range') }), ' ', range),
    kpis, funnel, schools,
  ];
}

const SCHOOL_COLS = [
  ['name', 'rp_school', 'asc'], ['sessions', 'rp_sessions', 'desc'], ['participants', 'rp_participants', 'desc'],
  ['participated', 'rp_participated', 'desc'], ['participation_rate', 'rp_participation_pct', 'desc'],
  ['completion_rate', 'rp_completion_pct', 'desc'], ['avg_score', 'rp_avg_score', 'desc'],
  ['last_session', 'rp_last_session', 'desc'],
];

function schoolsTable(sch) {
  const sp = state.schools;
  const head = h('tr', {}, SCHOOL_COLS.map(([col, key, def], i) => {
    const active = sp.sort === col;
    const th = h('th', { scope: 'col', class: i ? 'rp-num' : null,
      'aria-sort': active ? (sp.dir === 'asc' ? 'ascending' : 'descending') : null });
    th.append(h('button', { type: 'button', class: 'rp-sort', onclick: () => {
      if (sp.sort === col) sp.dir = sp.dir === 'asc' ? 'desc' : 'asc';
      else { sp.sort = col; sp.dir = def; }
      sp.offset = 0;
      render({ focusSelector: `[data-sort="${col}"]` });
    }, 'data-sort': col }, t(key), h('span', { class: 'rp-sort-ico', 'aria-hidden': 'true', text: active ? (sp.dir === 'asc' ? ' ▲' : ' ▼') : ' ↕' })));
    return th;
  }));
  const rows = sch.items.map((s) => h('tr', {},
    h('th', { scope: 'row' }, h('a', { href: schoolHref(s.school_key), text: schoolLabel(s.school) })),
    h('td', { class: 'rp-num', text: int(s.sessions) }),
    h('td', { class: 'rp-num', text: int(s.participants) }),
    h('td', { class: 'rp-num', text: int(s.participated) }),
    h('td', { class: 'rp-num' }, h('span', { class: 'rp-cell-bar' }, bar(s.participation_rate), h('span', { text: rate(s.participation_rate) }))),
    h('td', { class: 'rp-num', text: rate(s.completion_rate) }),
    h('td', { class: 'rp-num', text: scorePct(s.avg_score_pct) }),
    h('td', { class: 'rp-num', text: fmtDate(s.last_session_date) })));
  return h('table', { class: 'rp-table' }, h('caption', { class: 'rp-sr', text: t('rp_schools') }), h('thead', {}, head), h('tbody', {}, rows));
}

function schoolTabs(school, active) {
  const tab = (key, tabName) => h('a', { href: schoolHref(school, tabName), class: `rp-tab${active === tabName ? ' is-active' : ''}`,
    'aria-current': active === tabName ? 'page' : null, text: t(key) });
  return h('nav', { class: 'rp-tabs', 'aria-label': schoolLabel(school) }, tab('rp_tab_sessions', 'sessions'), tab('rp_tab_progress', 'progress'));
}

async function viewSchool(r, seq) {
  const params = filterParams({ withSchool: false });
  const off = state.sessionsOffset;
  const d = await api(`/schools/${encodeURIComponent(r.school)}/sessions`, { ...params, limit: LIMIT, offset: off });
  if (seq !== renderSeq) return null;
  const rows = d.items.map((s) => h('tr', {},
    h('th', { scope: 'row' }, h('a', { href: sessionHref(s.kind, s.id, r.school), text: s.title || typeLabel(s.type) })),
    h('td', {}, h('span', { class: `rp-chip rp-chip-${s.kind}`, text: typeLabel(s.type) + (s.grouping === 'individual' ? ` · ${t('rp_individuals')}` : '') })),
    h('td', { text: fmtDate(s.date) }),
    h('td', { text: s.teacher || '–' }),
    h('td', { class: 'rp-num', text: int(s.participants) }),
    h('td', { class: 'rp-num', text: int(s.participated) }),
    h('td', { class: 'rp-num', text: rate(s.completion_rate) }),
    h('td', { class: 'rp-num', text: scorePct(s.avg_score_pct) }),
    h('td', {}, s.csv_url ? h('a', { href: s.csv_url, download: '', text: t('rp_class_csv') }) : '–')));
  const table = h('table', { class: 'rp-table' },
    h('caption', { class: 'rp-sr', text: t('rp_view_sessions', { name: schoolLabel(d.school) }) }),
    h('thead', {}, h('tr', {}, [['rp_session'], ['rp_type'], ['rp_date'], ['rp_teacher'], ['rp_participants', 1],
      ['rp_participated', 1], ['rp_completion_pct', 1], ['rp_avg_score', 1], ['rp_class_csv']]
      .map(([k, num]) => h('th', { scope: 'col', class: num ? 'rp-num' : null, text: t(k) })))),
    h('tbody', {}, rows));
  return [
    sectionLabel(t('rp_school')),
    h('h1', { class: 'rp-h1', tabindex: '-1', text: schoolLabel(d.school) }),
    schoolTabs(r.school, 'sessions'),
    card(t('rp_tab_sessions'), 'h-sessions',
      h('div', { class: 'rp-card-actions' }, csvButton(`/schools/${encodeURIComponent(r.school)}/sessions`, params)),
      d.items.length ? tableWrap(t('rp_tab_sessions'), table) : h('p', { class: 'rp-muted', text: t('rp_no_data') }),
      pager(d.total, d.offset, LIMIT, (o) => { state.sessionsOffset = o; render({ focusId: 'h-sessions' }); })),
  ];
}

async function viewProgress(r, seq) {
  const params = filterParams({ withSchool: false });
  const off = state.progressOffset;
  const d = await api('/students', { ...params, school: r.school, limit: LIMIT, offset: off });
  if (seq !== renderSeq) return null;
  const rows = d.items.map((s) => {
    const list = h('ol', { class: 'rp-trend' }, s.sessions.map((x) => h('li', {},
      bar((x.score_pct ?? 0) / 100, x.score_pct === null ? 'empty' : null),
      h('span', { class: 'rp-trend-txt', text: `${fmtDate(x.date)} · ${typeLabel(x.type)}: ${x.score_pct === null ? t('rp_not_scored') : scorePct(x.score_pct)}` }))));
    const imp = s.improvement_pct;
    const impTxt = imp === null ? '–' : `${imp > 0 ? '+' : imp < 0 ? '−' : '±'}${nf(Math.abs(imp), 1)} pts`;
    return h('tr', {},
      h('th', { scope: 'row', text: s.name }),
      h('td', { class: 'rp-num', text: int(s.sessions_attended) }),
      h('td', {}, list),
      h('td', { class: 'rp-num', text: scorePct(s.first_score_pct) }),
      h('td', { class: 'rp-num', text: scorePct(s.last_score_pct) }),
      h('td', { class: `rp-num${imp > 0 ? ' rp-up' : imp < 0 ? ' rp-down' : ''}`, text: impTxt }));
  });
  const table = h('table', { class: 'rp-table' },
    h('caption', { class: 'rp-sr', text: t('rp_view_students', { name: schoolLabel(d.school) }) }),
    h('thead', {}, h('tr', {}, [['rp_name'], ['rp_sessions_attended', 1], ['rp_scores'], ['rp_first', 1], ['rp_last', 1], ['rp_improvement', 1]]
      .map(([k, num]) => h('th', { scope: 'col', class: num ? 'rp-num' : null, text: t(k) })))),
    h('tbody', {}, rows));
  return [
    sectionLabel(t('rp_school')),
    h('h1', { class: 'rp-h1', tabindex: '-1', text: schoolLabel(d.school) }),
    schoolTabs(r.school, 'progress'),
    card(t('rp_tab_progress'), 'h-progress',
      h('p', { class: 'rp-note', role: 'note' }, h('strong', { text: '≈ ' }), t('rp_match_note')),
      h('div', { class: 'rp-card-actions' }, csvButton('/students', { ...params, school: r.school })),
      d.items.length ? tableWrap(t('rp_tab_progress'), table) : h('p', { class: 'rp-muted', text: t('rp_no_data') }),
      pager(d.total, d.offset, LIMIT, (o) => { state.progressOffset = o; render({ focusId: 'h-progress' }); })),
  ];
}

async function viewSession(r, seq) {
  const lim = 100;
  const off = state.studentsOffset;
  const d = await api(`/sessions/${encodeURIComponent(r.kind)}/${encodeURIComponent(r.id)}`, { limit: lim, offset: off });
  if (seq !== renderSeq) return null;
  const s = d.session;
  const hw = s.kind === 'homework';
  const cols = [['rp_rank', 1], ['rp_name'], ['rp_present'], ['rp_answered', 1], ['rp_correct', 1], ['rp_accuracy', 1],
    ['rp_score', 1], ['rp_completed']].concat(hw ? [['rp_progress', 1]] : []);
  const rows = d.students.map((p) => h('tr', { class: p.present ? null : 'rp-absent' },
    h('td', { class: 'rp-num', text: p.rank ?? '–' }),
    h('th', { scope: 'row', text: p.name }),
    h('td', { text: p.present ? t('rp_yes') : t('rp_absent') }),
    h('td', { class: 'rp-num', text: int(p.answered) }),
    h('td', { class: 'rp-num', text: int(p.correct) }),
    h('td', { class: 'rp-num', text: scorePct(p.accuracy_pct) }),
    h('td', { class: 'rp-num', text: int(p.score) }),
    h('td', { text: p.completed ? `✓ ${t('rp_yes')}` : t('rp_no') }),
    hw ? h('td', { class: 'rp-num', text: `${p.progress}/${p.total}` }) : null));
  const table = h('table', { class: 'rp-table' },
    h('caption', { class: 'rp-sr', text: `${t('rp_students')}: ${s.title}` }),
    h('thead', {}, h('tr', {}, cols.map(([k, num]) => h('th', { scope: 'col', class: num ? 'rp-num' : null, text: t(k) })))),
    h('tbody', {}, rows));
  const meta = [typeLabel(s.type), fmtDate(s.date), s.teacher, schoolLabel(s.school)]
    .filter(Boolean).join(' · ');
  const school = r.school || s.school;
  return [
    sectionLabel(`${t('rp_session')} · ${typeLabel(s.type)}`),
    h('h1', { class: 'rp-h1', tabindex: '-1', text: s.title || typeLabel(s.type) }),
    h('p', { class: 'rp-muted', text: meta }),
    h('div', { class: 'rp-kpis rp-kpis-sm' },
      kpiCard(t('rp_participants'), int(s.participants)),
      kpiCard(t('rp_kpi_participation'), rate(s.participation_rate), t('rp_kpi_participation_sub', { n: int(s.participated) })),
      kpiCard(t('rp_kpi_completion'), rate(s.completion_rate)),
      kpiCard(t('rp_kpi_score'), scorePct(s.avg_score_pct)),
      kpiCard(t('rp_questions'), int(s.questions))),
    card(t('rp_students'), 'h-students',
      h('div', { class: 'rp-card-actions' },
        csvButton(`/sessions/${encodeURIComponent(r.kind)}/${encodeURIComponent(r.id)}`, {}),
        s.csv_url ? h('a', { class: 'rp-btn rp-btn-ghost rp-btn-sm', href: s.csv_url, download: '', text: t('rp_class_csv') }) : null),
      d.students.length ? tableWrap(t('rp_students'), table) : h('p', { class: 'rp-muted', text: t('rp_no_data') }),
      pager(d.total, d.offset, lim, (o) => { state.studentsOffset = o; render({ focusId: 'h-students' }); })),
    school ? h('p', {}, h('a', { href: schoolHref(school), text: `← ${schoolLabel(school)}` })) : null,
  ];
}

// ------------------------------------------------------------------ render
let lastRouteKey = '';
async function render({ focus = false, focusId = null, focusSelector = null, announce = false } = {}) {
  if (!accessKey) { showGate(); return; }
  $('gate').hidden = true;
  $('app').hidden = false;
  $('signout').hidden = false;
  const r = route();
  const routeKey = JSON.stringify(r);
  if (routeKey !== lastRouteKey) {
    // a new place: page lists from the start
    if (r.view === 'session') state.studentsOffset = 0;
    if (r.view === 'sessions') state.sessionsOffset = 0;
    if (r.view === 'progress') state.progressOffset = 0;
    lastRouteKey = routeKey;
  }
  crumbs(r);
  $('backbar').hidden = r.view === 'overview';
  $('f-school').closest('.rp-f').hidden = r.view !== 'overview'; // school search only lists schools
  const seq = ++renderSeq;
  setStatus(t('rp_loading'));
  $('view').setAttribute('aria-busy', 'true');
  try {
    let nodes;
    if (r.view === 'overview') nodes = await viewOverview(seq);
    else if (r.view === 'progress') nodes = await viewProgress(r, seq);
    else if (r.view === 'session') nodes = await viewSession(r, seq);
    else nodes = await viewSchool(r, seq);
    if (!nodes) return;
    $('view').replaceChildren(...nodes.filter(Boolean));
    setStatus(announce ? t('rp_loaded') : '');
    if (focusSelector) document.querySelector(focusSelector)?.focus();
    else if (focusId) { const e = $(focusId); if (e) { e.setAttribute('tabindex', '-1'); e.focus(); } }
    else if (focus) $('view').querySelector('h1')?.focus();
  } catch (e) {
    if (seq !== renderSeq) return;
    if (e.status === 401 || e.status === 429 || e.status === 503) return; // gate is shown
    $('view').replaceChildren(h('p', { class: 'rp-err', role: 'alert', text: e.status === 404 ? `${e.message}` : t('rp_error') }));
    setStatus('');
  } finally {
    if (seq === renderSeq) $('view').removeAttribute('aria-busy');
  }
}

function init() {
  applyI18n();
  document.title = `${t('rp_title')} · PlayClass`;
  mountLangSwitch($('lang'));
  onLangChange(() => {
    document.title = `${t('rp_title')} · PlayClass`;
    if (notConfigured) showGate('rp_not_configured'); else if (accessKey) render();
  });
  $('gate-form').addEventListener('submit', onGateSubmit);
  $('signout').addEventListener('click', () => signOut());
  $('nav-back').addEventListener('click', () => {
    // one level up: session → its school, school tab → overview
    const r = route();
    location.hash = r.view === 'session' && r.school ? schoolHref(r.school) : r.view === 'progress' ? schoolHref(r.school) : '#/';
  });
  $('filters').addEventListener('submit', (ev) => { ev.preventDefault(); readFilters(); render({ announce: true }); });
  $('f-reset').addEventListener('click', () => {
    for (const id of ['f-mode', 'f-school', 'f-from', 'f-to']) $(id).value = '';
    readFilters();
    render({ announce: true });
  });
  window.addEventListener('hashchange', () => { if (!notConfigured) render({ focus: true }); });
  render();
  checkConfigured();
}

init();
