// host.js — teacher / projector side of the live quiz.
// create (ready-made packs + "My quizzes" with an editor) → lobby → question → reveal → leaderboard → podium.
// Phases are driven only by this page (POST …/next with {status, index} so a double-click can't skip).
import { t, applyI18n, mountLangSwitch, onLangChange, fmtInt, BRAND } from './i18n.js';
import { applyPrefs } from './a11y-prefs.js';
import {
  $, $$, h, api, lsGet, lsSet, lsDel, n0, clock, connectLive, connectionPill, announce, toast,
  shapeIcon, shapeName, showScreen as showScreenRaw, isMC, sfx, confetti, icon, iconLabel, mascot, mascotFor,
  fmtWhen, fmtAgo,
} from './live-common.js';

const LS_HOST = 'live.host';          // {pin, host_token}
const LS_QUIZZES = 'live.myQuizzes';  // [{pack_id, edit_key, name}]
const LS_SCHOOL = 'playclass.school';   // {school} — shared with /classroom
const LS_SCHOOLS = 'playclass.schools'; // [school names used on this device]
const LS_MODE = 'playclass.hostMode';   // 'live' | 'hw' | 'present' — last "How will students play?" choice
const LS_GAMES = 'playclass.myGames';   // [{pin, host_token, title, closes_at, mode, join_url, created_at}] — "My games"
const LS_HW = 'live.hostHw';            // {pin, host_token, join_url, view: 'share'|'monitor'} — open homework screen
const GRACE_MS = 3000;
const COUNTS = [5, 10, 15];
const TIMES = [10, 20, 30, 60];
const POINTS = [{ v: 100, k: 'standard' }, { v: 200, k: 'double' }];

const S = {
  packs: [], selected: null,  // {kind:'pack'|'mine', pack_id, name, available}
  pin: '', token: '', conn: null, state: null, view: '', busy: false,
  timer: 0, ticked: -1, autoNextFor: '', names: new Map(), sideRows: new Map(),
  quiz: null,                  // editor: {pack_id, edit_key, name, questions:[]}
  editIdx: -1,                 // question being edited (-1 = new)
  form: null,                  // {prompt, options, correct, time, points}
};

applyPrefs();
applyI18n();
mountLangSwitch($('#lang'));
document.title = `${t('host_title')} · ${BRAND.name}`;
try { const m = document.createElement('meta'); m.name = 'theme-color'; m.content = getComputedStyle(document.documentElement).getPropertyValue('--se-bg').trim(); document.head.append(m); } catch { /* ignore */ }
onLangChange(() => {
  renderCounts(); renderPacks(); renderMine(); renderMuteBtns(); renderSelected(); renderSchoolCard();
  applyMode(); DL.create.render(); DL.dialog.render(); if (S.screen === 'create') renderMyGames();
  if (S.quiz) renderEditor();
  if (S.state) { S.view = ''; render(S.state); }
  syncNav(S.screen);
});

// ================================================================== top-bar controls
function renderMuteBtns() {
  const m = $('#btn-mute');
  m.setAttribute('aria-pressed', String(sfx.muted));
  m.setAttribute('aria-label', sfx.muted ? t('unmute') : t('mute'));
  m.title = m.getAttribute('aria-label');
  m.replaceChildren(icon(sfx.muted ? 'volume-x' : 'volume-2'));
  const mu = $('#btn-music');
  mu.setAttribute('aria-pressed', String(sfx.musicOn));
  mu.setAttribute('aria-label', sfx.musicOn ? t('music_off') : t('music_on'));
  mu.title = mu.getAttribute('aria-label');
}
$('#btn-mute').addEventListener('click', () => { sfx.setMuted(!sfx.muted); sfx.unlock(); renderMuteBtns(); });
$('#btn-music').addEventListener('click', () => { sfx.unlock(); if (sfx.musicOn) sfx.stopMusic(); else sfx.startMusic(); renderMuteBtns(); });
$('#btn-fs').addEventListener('click', toggleFullscreen);
renderMuteBtns();

function toggleFullscreen() {
  try {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  } catch { /* not allowed */ }
}

// Space / Enter = Next only when focus is on the page itself (buttons keep their own keys); F = full screen.
document.addEventListener('keydown', (e) => {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
  const tg = e.target;
  const typing = tg && (tg.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(tg.tagName));
  if (typing || document.querySelector('dialog[open]')) return;
  if ((e.key === 'f' || e.key === 'F') && !e.repeat) { e.preventDefault(); toggleFullscreen(); return; }
  if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
    const onPage = tg === document.body || tg === document.documentElement || tg === $('#main') || (tg && tg.matches && tg.matches('h1[tabindex="-1"], h2[tabindex="-1"]'));
    if (!onPage || !S.state || !['lobby', 'question', 'reveal', 'leaderboard'].includes(S.state.status)) return;
    e.preventDefault();
    if (S.state.status === 'lobby') start(); else next();
  }
});

// ================================================================== back navigation + browser history
// create → home · editor → create (its own Back button) · question form → editor (warns on unsaved changes)
// · lobby → create (confirm: ends the game) · running game: no Back, only "End game" (confirm) · podium → create.
// Browser Back mirrors this (pushState per step, popstate), so it never ends a game without confirmation.
const IN_GAME = new Set(['question', 'reveal', 'leaderboard']);
function showScreen(name, opts) {
  const prev = S.screen;
  const r = showScreenRaw(name, opts);
  S.screen = name;
  try {
    if (name === 'editor' && prev !== 'editor') history.pushState({ host: 'editor' }, '');
    else if ((name === 'lobby' || IN_GAME.has(name)) && !S.guarded) { history.pushState({ host: 'game' }, ''); S.guarded = true; }
    else if (name === 'create') S.guarded = false;
  } catch { /* ignore */ }
  syncNav(name);
  return r;
}
function syncNav(name) {
  const bar = $('#backbar');
  const show = name === 'create' || name === 'lobby' || name === 'podium' || name === 'share' || name === 'monitor';
  bar.hidden = !show;
  if (show) iconLabel($('#nav-back'), 'arrow-left', name === 'create' ? t('back_home') : t('back'));
}
async function endAndLeave() {
  try { await api(`/api/live/games/${S.pin}/end`, { method: 'POST', headers: { 'X-Host-Token': S.token } }); } catch (e) { if (e.status !== 404 && e.status !== 409) toast(e.message, { error: true }); }
  forgetGame(S.pin, S.token); lsDel(LS_HOST); leaveGame();
}
async function goBack(fromHistory = false) {
  const name = S.screen;
  if (name === 'create') { location.href = '/'; return; }
  if (name === 'editor') { $('#ed-back').click(); return; }
  if (name === 'podium') { lsDel(LS_HOST); leaveGame(); return; }
  if (name === 'share' || name === 'monitor') {
    if (!fromHistory && history.state && history.state.host === name) { history.back(); return; } // popstate does the rest
    leaveHw(); return;
  }
  if (name === 'lobby' || IN_GAME.has(name)) {
    if (fromHistory) { try { history.pushState({ host: 'game' }, ''); } catch { /* ignore */ } }
    const ok = await confirmDialog(name === 'lobby' ? t('lobby_leave_title') : t('end_confirm'), t('end_game'));
    if (!ok) return;
    if (name === 'lobby') await endAndLeave();
    else { try { render(await api(`/api/live/games/${S.pin}/end`, { method: 'POST', headers: { 'X-Host-Token': S.token } })); } catch (e) { toast(e.message, { error: true }); } }
  }
}
$('#nav-back').addEventListener('click', () => goBack(false));
window.addEventListener('popstate', async () => {
  const qd = $('#dlg-question');
  if (qd.open) { try { history.pushState({ host: 'editor' }, ''); } catch { /* ignore */ } closeQuestionForm(); return; }
  document.querySelectorAll('dialog[open]').forEach((d) => d.close());
  if (S.screen === 'share' || S.screen === 'monitor') {
    const hs = history.state && history.state.host;
    if ((hs === 'share' || hs === 'monitor') && S.pin) hwShow(hs, { push: false }); else leaveHw();
    return;
  }
  if (S.screen === 'editor') { S.quiz = null; renderMine(); selectTab('mine'); showScreen('create'); return; }
  goBack(true);
});

// ================================================================== CREATE: tabs
function selectTab(which) {
  const ready = which === 'ready';
  $('#tab-ready').setAttribute('aria-selected', String(ready));
  $('#tab-mine').setAttribute('aria-selected', String(!ready));
  $('#tab-ready').tabIndex = ready ? 0 : -1;
  $('#tab-mine').tabIndex = ready ? -1 : 0;
  $('#panel-ready').hidden = !ready;
  $('#panel-mine').hidden = ready;
}
$('#tab-ready').addEventListener('click', () => selectTab('ready'));
$('#tab-mine').addEventListener('click', () => selectTab('mine'));
$('.lv-tabs').addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const toMine = $('#tab-ready').getAttribute('aria-selected') === 'true';
  selectTab(toMine ? 'mine' : 'ready');
  (toMine ? $('#tab-mine') : $('#tab-ready')).focus();
});

// ---------- ready-made packs
async function loadPacks() {
  try {
    const keys = myQuizzes().map((q) => q.edit_key).filter(Boolean).join(',');
    const packs = await api('/api/live/packs', { headers: keys ? { 'X-Edit-Key': keys } : {} });
    const all = Array.isArray(packs) ? packs : [];
    S.packs = all.filter((p) => !p.teacher_owned && mcCount(p) > 0 && !/^\[pytest\]/.test(p.name));
    // refresh names / playable counts of "My quizzes" from the server
    const mine = new Map(all.filter((p) => p.teacher_owned).map((p) => [p.id, p]));
    if (mine.size) {
      lsSet(LS_QUIZZES, myQuizzes().map((q) => (mine.has(q.pack_id) ? { ...q, name: mine.get(q.pack_id).name, count: mcCount(mine.get(q.pack_id)) } : q)));
      renderMine();
    }
  } catch (e) { S.packs = []; toast(e.message, { error: true }); }
  renderPacks();
}
const mcCount = (p) => n0((p.question_counts || {}).multiple_choice); // playable quiz questions in the pack

function splitLang(text) {
  // Seed texts are "EN … — BM — …" or "EN / BM": show the part for the current language when we can.
  const s = String(text || '');
  const m = s.split(/\n+\s*—\s*BM\s*—\s*\n+/);
  if (m.length === 2) return document.documentElement.lang === 'ms' ? m[1] : m[0];
  return s;
}
function packName(p) {
  const parts = String(p.name || '').split(' / ');
  return parts.length === 2 ? (document.documentElement.lang === 'ms' ? parts[1] : parts[0]) : p.name;
}

function renderPacks() {
  const box = $('#packs');
  if (!S.packs.length) { box.replaceChildren(h('p', { class: 'lv-hint' }, '…')); return; }
  box.replaceChildren(...S.packs.map((p) => {
    const sel = S.selected && S.selected.kind === 'pack' && S.selected.pack_id === p.id;
    const desc = splitLang(p.description).split(' / ')[0];
    return h('article', { class: `lv-card lv-pack${sel ? ' is-selected' : ''}`, 'aria-labelledby': `pk-${p.id}` },
      h('span', { class: `lv-tag${p.topic === 'ai' ? '' : ' lv-tag-general'}` }, p.topic === 'ai' ? t('topic_ai') : t('topic_general')),
      h('h2', { id: `pk-${p.id}` }, packName(p)),
      h('p', {}, desc),
      h('p', { class: 'lv-pack-count' }, t('n_questions', { n: mcCount(p) })),
      p.why_it_matters ? h('details', { class: 'lv-details' }, h('summary', {}, t('why_teach')), h('p', {}, splitLang(p.why_it_matters))) : null,
      h('div', { class: 'lv-row' },
        h('button', { type: 'button', class: `lv-btn ${sel ? 'lv-btn-dark' : 'lv-btn-primary'}`, 'aria-pressed': String(!!sel),
          'aria-label': `${t('use')}: ${packName(p)}`,
          onclick: () => choose({ kind: 'pack', pack_id: p.id, name: packName(p), available: mcCount(p) }) },
        icon(sel ? 'check' : 'play'), sel ? t('selected') : t('use')),
        h('button', { type: 'button', class: 'lv-btn', 'aria-label': `${t('duplicate_edit')}: ${packName(p)}`, onclick: () => duplicatePack(p) },
          icon('copy'), t('duplicate_edit'))));
  }));
}

// ---------- my quizzes (localStorage)
const myQuizzes = () => { const v = lsGet(LS_QUIZZES); return Array.isArray(v) ? v : []; };
function rememberQuiz(q) {
  const list = myQuizzes().filter((x) => x.pack_id !== q.pack_id);
  list.unshift({ pack_id: q.pack_id, edit_key: q.edit_key, name: q.name, count: q.count ?? (q.questions || []).length });
  lsSet(LS_QUIZZES, list.slice(0, 50));
}
function renderMine() {
  const list = myQuizzes();
  const box = $('#myquizzes');
  if (!list.length) { box.replaceChildren(h('div', { class: 'lv-card se-empty' }, mascot('purple', { size: 'md' }), h('p', { class: 'lv-hint' }, t('mine_empty')))); return; }
  box.replaceChildren(...list.map((q) => {
    const sel = S.selected && S.selected.kind === 'mine' && S.selected.pack_id === q.pack_id;
    return h('article', { class: `lv-card lv-pack${sel ? ' is-selected' : ''}`, 'aria-labelledby': `mq-${q.pack_id}` },
      h('span', { class: 'lv-tag' }, t('tab_mine')),
      h('h2', { id: `mq-${q.pack_id}` }, q.name || t('untitled')),
      typeof q.count === 'number' ? h('p', { class: 'lv-pack-count' }, t('q_count_n', { n: q.count })) : null,
      h('div', { class: 'lv-row' },
        h('button', { type: 'button', class: `lv-btn ${sel ? 'lv-btn-dark' : 'lv-btn-primary'}`, 'aria-pressed': String(!!sel),
          'aria-label': `${t('use')}: ${q.name}`,
          onclick: () => {
            if (!q.count) { toast(t('need_questions'), { error: true }); return; }
            choose({ kind: 'mine', pack_id: q.pack_id, name: q.name, available: q.count });
          } }, icon(sel ? 'check' : 'play'), sel ? t('selected') : t('use')),
        h('button', { type: 'button', class: 'lv-btn', 'aria-label': `${t('edit')}: ${q.name}`, onclick: () => openEditor(q.pack_id, q.edit_key) }, `✎ ${t('edit')}`)));
  }));
}

// ---------- setup
function renderCounts() {
  const box = $('#g-count');
  const avail = S.selected ? S.selected.available : 99;
  const cur = Number((box.querySelector('input:checked') || {}).value || 10);
  const opts = COUNTS.filter((n) => n < avail);
  const values = [...opts.map((n) => ({ v: n, label: String(n) })), ...(avail <= 30 ? [{ v: avail, label: t('all_n', { n: avail }) }] : [])];
  if (!values.length) values.push({ v: 10, label: '10' });
  const pick = values.some((o) => o.v === cur) ? cur : (S.selected && S.selected.kind === 'mine' ? avail : (values.find((o) => o.v === 10) || values[values.length - 1]).v);
  box.replaceChildren(...values.flatMap((o) => [
    h('input', { type: 'radio', name: 'count', id: `cnt-${o.v}`, value: String(o.v), checked: o.v === pick }),
    h('label', { for: `cnt-${o.v}` }, o.label)]));
}
function renderSelected() {
  $('#setup-quiz').textContent = S.selected ? t('playing_quiz', { name: S.selected.name }) : t('ready_hint');
}
function choose(sel) {
  S.selected = sel;
  renderPacks(); renderMine(); renderCounts(); renderSelected();
  $('#create-err').textContent = '';
  $('#setup').scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('#setup').focus({ preventScroll: true });
}

$('#create-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#btn-create');
  if (btn.getAttribute('aria-disabled') === 'true') return;
  if (!S.selected) { $('#create-err').textContent = t('ready_hint'); selectTab('ready'); $('#packs button').focus(); return; }
  const where = validateSchool();
  if (!where) return;
  if (S.mode === 'present') { openPresenter(where.school); return; }
  if (S.mode === 'hw') { createHomework(where.school); return; }
  sfx.unlock();
  const body = {
    pack_id: S.selected.pack_id, game_modes: ['multiple_choice'],
    question_count: Number(($('#g-count input:checked') || {}).value || 10),
    title: $('#g-title').value.trim() || S.selected.name,
    teacher_name: $('#g-teacher').value.trim(), school: where.school, program: '',
    instant_feedback: $('#g-instant-on').checked, allow_rename: $('#g-rename').checked,
  };
  btn.setAttribute('aria-disabled', 'true'); btn.textContent = t('creating');
  try {
    const r = await api('/api/live/games', { method: 'POST', json: body });
    S.pin = r.pin; S.token = r.host_token; S.joinUrl = r.join_url;
    lsSet(LS_HOST, { pin: S.pin, host_token: S.token, join_url: r.join_url });
    rememberGame({ pin: r.pin, host_token: r.host_token, title: r.title || body.title, closes_at: null, mode: 'live', join_url: r.join_url });
    connect();
  } catch (err) {
    $('#create-err').textContent = err.status === 422 && /enough/i.test(err.message) ? t('not_enough') : err.message;
  } finally { btn.removeAttribute('aria-disabled'); btn.textContent = createLabel(); }
});

// ---------- "Your school" card: School is required and remembered on this device (shared with /classroom)
const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
function savedSchool() { const v = lsGet(LS_SCHOOL); return norm(v && typeof v === 'object' ? v.school : ''); }
function savedSchools() { const v = lsGet(LS_SCHOOLS); return Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()) : []; }
function fillSchoolFields() {
  if (!$('#g-school').value) $('#g-school').value = savedSchool();
  $('#dl-schools').replaceChildren(...savedSchools().map((x) => h('option', { value: x })));
}
function renderSchoolCard(editing) {
  const school = savedSchool();
  const card = $('#school-card');
  if (editing === undefined) editing = card.dataset.editing === '1' || !school;
  card.dataset.editing = editing ? '1' : '0';
  $('#school-fields').hidden = !editing;
  $('#school-summary').hidden = editing;
  const ch = $('#school-change');
  ch.hidden = editing || !school;
  ch.setAttribute('aria-expanded', String(!!editing));
  ch.setAttribute('aria-label', `${t('change')}: ${t('your_school')}`);
  if (school) $('#school-summary').replaceChildren(icon('school'), h('strong', {}, school));
}
function rememberSchool(school) {
  lsSet(LS_SCHOOL, { school });
  lsSet(LS_SCHOOLS, [school, ...savedSchools().filter((x) => x.toLowerCase() !== school.toLowerCase())].slice(0, 20));
}
/** Returns {school} or null (error shown, card opened, field focused). */
function validateSchool() {
  const school = norm($('#g-school').value);
  if (!school) {
    renderSchoolCard(true);
    $('#g-school-err').textContent = t('err_school');
    $('#g-school').setAttribute('aria-invalid', 'true');
    $('#create-err').textContent = t('err_school_card');
    $('#g-school').focus();
    return null;
  }
  rememberSchool(school);
  $('#school-card').dataset.editing = '0';
  return { school };
}
$('#g-school').addEventListener('input', () => { $('#g-school-err').textContent = ''; $('#g-school').removeAttribute('aria-invalid'); });
$('#school-change').addEventListener('click', () => { renderSchoolCard(true); $('#g-school').focus(); });

// resume a running game after a refresh
function initCreate() {
  showScreen('create', { focus: false });
  fillSchoolFields();
  renderSchoolCard();
  const saved = lsGet(LS_HOST);
  const rb = $('#btn-resume');
  if (saved && saved.pin && saved.host_token) {
    rb.hidden = false;
    iconLabel(rb, 'play', t('resume', { pin: saved.pin }));
    rb.onclick = () => { S.pin = saved.pin; S.token = saved.host_token; S.joinUrl = saved.join_url; connect(); };
  } else rb.hidden = true;
  renderMyGames();
}

// ================================================================== QUIZ EDITOR
function quizPath(id, rest = '') { return `/api/live/quizzes/${encodeURIComponent(id)}${rest}`; }
const editHeaders = () => ({ 'X-Edit-Key': S.quiz.edit_key });
const quizId = (q) => q.pack_id ?? q.id;
const qId = (q) => q.id ?? q.question_id;
const qPoints = (q) => Number(q.points ?? q.base_points ?? 100);

async function duplicatePack(p) {
  try {
    const r = await api(quizPath(p.id, '/duplicate'), { method: 'POST', json: {} });
    const pid = quizId(r);
    rememberQuiz({ pack_id: pid, edit_key: r.edit_key, name: r.name || `${packName(p)} (copy)`, count: r.question_count });
    renderMine();
    await openEditor(pid, r.edit_key);
  } catch (err) { toast(err.status === 404 || err.status === 405 ? t('quizzes_unavailable') : err.message, { error: true }); }
}
$('#btn-new-quiz').addEventListener('click', async () => {
  try {
    const r = await api('/api/live/quizzes', { method: 'POST', json: { name: t('untitled') } });
    const pid = quizId(r);
    rememberQuiz({ pack_id: pid, edit_key: r.edit_key, name: r.name || t('untitled'), questions: [] });
    renderMine();
    await openEditor(pid, r.edit_key, { focusName: true });
  } catch (err) { toast(err.status === 404 || err.status === 405 ? t('quizzes_unavailable') : err.message, { error: true }); }
});

async function openEditor(pid, key, { focusName = false } = {}) {
  try {
    const r = await api(quizPath(pid), { headers: { 'X-Edit-Key': key } });
    S.quiz = { ...r, pack_id: quizId(r) ?? pid, edit_key: key, questions: sortQs(r.questions || []) };
    rememberQuiz({ pack_id: S.quiz.pack_id, edit_key: key, name: S.quiz.name, questions: S.quiz.questions });
    renderEditor();
    showScreen('editor', { focus: !focusName });
    history.replaceState(null, '', '/host');
    if (focusName) { $('#ed-name').focus(); $('#ed-name').select(); }
  } catch (err) {
    toast(err.status === 403 || err.status === 404 ? t('edit_link_bad') : err.message, { error: true });
  }
}
const sortQs = (qs) => [...qs].sort((a, b) => (a.sort_order ?? a.position ?? 0) - (b.sort_order ?? b.position ?? 0));

function renderEditor() {
  const q = S.quiz;
  $('#ed-name').value = q.name || '';
  const qs = q.questions;
  $('#ed-count').textContent = t('q_count_n', { n: qs.length });
  $('#ed-empty').hidden = qs.length > 0;
  $('#ed-list').replaceChildren(...qs.map((x, i) => {
    const n = i + 1;
    const opts = Array.isArray(x.options) ? x.options : [];
    return h('li', { class: 'lv-card lv-qcard' },
      h('span', { class: 'lv-qnum', 'aria-hidden': 'true' }, String(n)),
      h('div', {},
        h('div', { class: 'lv-qtext', lang: 'en' }, h('span', { class: 'sr-only' }, `${n}. `), x.prompt),
        h('div', { class: 'lv-qopts' }, opts.map((o, j) => h('span', { class: `lv-qopt${j === x.correct_option ? ' is-correct' : ''}`, lang: 'en' },
          h('span', { style: `color:var(--se-opt-${j + 1}-hi)`, class: 'lv-shape' }, shapeIcon(j)), o,
          j === x.correct_option ? h('span', {}, ' ✓', h('span', { class: 'sr-only' }, ` (${t('correct_label')})`)) : null))),
        h('div', { class: 'lv-hint' }, icon('timer'), ` ${t('seconds_n', { n: x.time_limit_sec })} · ${qPoints(x) >= 200 ? t('double') : t('standard')}`)),
      h('div', { class: 'lv-qactions' },
        h('button', { type: 'button', class: 'lv-btn lv-btn-sm', 'aria-label': t('move_up', { n }), 'aria-disabled': String(i === 0), onclick: () => move(i, -1) }, icon('arrow-up')),
        h('button', { type: 'button', class: 'lv-btn lv-btn-sm', 'aria-label': t('move_down', { n }), 'aria-disabled': String(i === qs.length - 1), onclick: () => move(i, 1) }, icon('arrow-down')),
        h('button', { type: 'button', class: 'lv-btn lv-btn-sm', 'aria-label': t('edit_n', { n }), onclick: () => openQuestion(i) }, icon('pencil'), t('edit')),
        h('button', { type: 'button', class: 'lv-btn lv-btn-sm lv-btn-danger', 'aria-label': t('delete_n', { n }), onclick: () => deleteQuestion(i) }, icon('trash-2'), t('delete'))));
  }));
}

$('#ed-back').addEventListener('click', () => {
  if (history.state && history.state.host === 'editor') { history.back(); return; } // popstate returns to create
  S.quiz = null; renderMine(); selectTab('mine'); showScreen('create');
});
$('#ed-use').addEventListener('click', () => {
  const q = S.quiz;
  if (!q.questions.length) { toast(t('need_questions'), { error: true }); return; }
  const sel = { kind: 'mine', pack_id: q.pack_id, name: q.name, available: q.questions.length };
  S.quiz = null;
  renderMine(); selectTab('mine'); showScreen('create', { focus: false });
  choose(sel);
});
$('#ed-copy').addEventListener('click', async () => {
  const url = `${location.origin}/host?edit=${encodeURIComponent(S.quiz.pack_id)}.${encodeURIComponent(S.quiz.edit_key)}`;
  try { await navigator.clipboard.writeText(url); toast(t('copied')); } catch { toast(t('copy_fail', { url }), { ms: 12000 }); }
});
$('#ed-name-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = $('#ed-name').value.replace(/\s+/g, ' ').trim();
  const err = $('#ed-name-err');
  if (!name) { err.textContent = t('err_name'); $('#ed-name').setAttribute('aria-invalid', 'true'); $('#ed-name').focus(); return; }
  err.textContent = ''; $('#ed-name').removeAttribute('aria-invalid');
  try {
    const q = S.quiz;
    const r = await api(quizPath(q.pack_id), { method: 'PUT', json: { name, description: q.description || '', topic: q.topic || 'general', owner_label: q.owner_label || '' }, headers: editHeaders() });
    S.quiz.name = (r && r.name) || name;
    rememberQuiz({ ...S.quiz });
    toast(t('quiz_saved'));
  } catch (er) { err.textContent = er.message; }
});

async function move(i, dir) {
  const qs = S.quiz.questions; const j = i + dir;
  if (j < 0 || j >= qs.length) return;
  const reordered = [...qs]; [reordered[i], reordered[j]] = [reordered[j], reordered[i]];
  try {
    await api(quizPath(S.quiz.pack_id, '/order'), { method: 'PUT', json: { question_ids: reordered.map(qId) }, headers: editHeaders() });
    S.quiz.questions = reordered;
    renderEditor();
    const n = j + 1;
    const btn = $(`#ed-list li:nth-child(${n}) button[aria-label="${CSS.escape(t(dir < 0 ? 'move_up' : 'move_down', { n }))}"]`);
    (btn && btn.getAttribute('aria-disabled') !== 'true' ? btn : $(`#ed-list li:nth-child(${n}) button`)).focus();
    announce(`${reordered[j].prompt} → ${n}`);
  } catch (err) { toast(err.message, { error: true }); }
}

async function deleteQuestion(i) {
  const n = i + 1;
  if (!(await confirmDialog(t('delete_confirm', { n }), t('delete')))) return;
  const q = S.quiz.questions[i];
  try {
    const r = await api(quizPath(S.quiz.pack_id, `/questions/${qId(q)}`), { method: 'DELETE', headers: editHeaders() });
    S.quiz.questions.splice(i, 1);
    rememberQuiz({ ...S.quiz });
    renderEditor();
    toast(r && (r.archived || r.status === 'archived') ? t('archived') : t('deleted'));
    const target = $(`#ed-list li:nth-child(${Math.min(n, S.quiz.questions.length)}) button`) || $('#ed-add');
    target.focus();
  } catch (err) { toast(err.message, { error: true }); }
}

// ---------- question form (dialog)
$('#ed-add').addEventListener('click', () => openQuestion(-1));
function openQuestion(i) {
  S.editIdx = i;
  const q = i >= 0 ? S.quiz.questions[i] : null;
  S.form = q ? { prompt: q.prompt || '', options: [...(q.options || [])], correct: q.correct_option ?? null, time: q.time_limit_sec || 20, points: qPoints(q) >= 200 ? 200 : 100 }
    : { prompt: '', options: ['', '', '', ''], correct: null, time: 20, points: 100 };
  $('#qf-title').textContent = q ? t('edit_question', { n: i + 1 }) : t('new_question');
  $('#qf-prompt').value = S.form.prompt;
  ['#qf-prompt-err', '#qf-opts-err', '#qf-err'].forEach((s) => { $(s).textContent = ''; });
  $('#qf-prompt').removeAttribute('aria-invalid');
  renderSeg('#qf-time', 'qf-time', TIMES.map((v) => ({ v, label: t('seconds_n', { n: v }) })), S.form.time, (v) => { S.form.time = v; });
  renderSeg('#qf-points', 'qf-pts', POINTS.map((p) => ({ v: p.v, label: t(p.k) })), S.form.points, (v) => { S.form.points = v; });
  renderOptions();
  S.formSnap = formSnapshot();
  $('#dlg-question').showModal();
  $('#qf-prompt').focus();
}
function formSnapshot() { return JSON.stringify({ ...S.form, prompt: $('#qf-prompt').value, opts: $$('#qf-opts input.lv-input').map((i) => i.value) }); }
async function closeQuestionForm() {
  if (S.form && formSnapshot() !== S.formSnap && !(await confirmDialog(t('discard_title'), t('discard')))) return;
  $('#dlg-question').close();
}
$('#qf-back').addEventListener('click', closeQuestionForm);
function renderSeg(sel, name, values, cur, onChange) {
  $(sel).replaceChildren(...values.flatMap((o) => {
    const inp = h('input', { type: 'radio', name, id: `${name}-${o.v}`, value: String(o.v), checked: o.v === cur });
    inp.addEventListener('change', () => onChange(o.v));
    return [inp, h('label', { for: `${name}-${o.v}` }, o.label)];
  }));
}
function renderOptions({ focus = -1 } = {}) {
  const f = S.form;
  $('#qf-opts').replaceChildren(...f.options.map((val, i) => {
    const inp = h('input', { class: 'lv-input', id: `qf-opt-${i}`, maxlength: '200', value: val, lang: 'en',
      'aria-label': t('answer_n', { n: i + 1, shape: shapeName(i) }) });
    inp.addEventListener('input', () => { f.options[i] = inp.value; $('#qf-opts-err').textContent = ''; renderPreview(); });
    const radio = h('input', { type: 'radio', name: 'qf-correct', value: String(i), checked: f.correct === i, 'aria-label': t('correct_for', { n: i + 1 }) });
    radio.addEventListener('change', () => { f.correct = i; $('#qf-opts-err').textContent = ''; renderPreview(); });
    return h('div', { class: 'lv-ans', 'data-i': String(i) },
      shapeIcon(i), inp,
      h('div', { class: 'lv-row', style: 'gap:2px;flex-wrap:nowrap' },
        h('label', { class: 'lv-correct' }, radio, h('span', { 'aria-hidden': 'true' }, t('correct_label'))),
        f.options.length > 2 ? h('button', { type: 'button', class: 'lv-icon-btn', style: 'min-width:44px;min-height:44px', 'aria-label': t('remove_answer', { n: i + 1 }), onclick: () => removeOption(i) }, '✕') : null));
  }));
  $('#qf-add-opt').hidden = f.options.length >= 4;
  renderPreview();
  if (focus >= 0) { const el = $(`#qf-opt-${focus}`); if (el) el.focus(); }
}
function removeOption(i) {
  const f = S.form;
  f.options.splice(i, 1);
  if (f.correct === i) f.correct = null; else if (f.correct !== null && f.correct > i) f.correct--;
  renderOptions({ focus: Math.min(i, f.options.length - 1) });
}
$('#qf-add-opt').addEventListener('click', () => { if (S.form.options.length < 4) { S.form.options.push(''); renderOptions({ focus: S.form.options.length - 1 }); } });
$('#qf-tf').addEventListener('click', () => {
  S.form.options = ['True', 'False']; // quiz content is English; the teacher can still edit the text
  if (S.form.correct !== null && S.form.correct > 1) S.form.correct = null;
  renderOptions({ focus: 0 });
});
$('#qf-prompt').addEventListener('input', () => { S.form.prompt = $('#qf-prompt').value; $('#qf-prompt-err').textContent = ''; $('#qf-prompt').removeAttribute('aria-invalid'); renderPreview(); });
function renderPreview() {
  const f = S.form;
  $('#qf-prev-q').textContent = f.prompt || '…';
  const opts = f.options;
  $('#qf-prev-tiles').replaceChildren(h('div', { class: 'lv-tiles', 'aria-hidden': 'true' }, opts.map((o, i) =>
    h('div', { class: `lv-tile${f.correct === i ? ' is-correct' : ''}`, 'data-i': String(i) }, shapeIcon(i), h('span', {}, o || '…')))));
}
/** Mirrors the server rules: 2–4 non-empty options ≤ 200 chars, no case-insensitive duplicates, valid correct index. */
function validateForm() {
  const f = S.form;
  const prompt = f.prompt.replace(/\s+/g, ' ').trim();
  const options = f.options.map((o) => o.replace(/\s+/g, ' ').trim());
  const errs = {};
  if (!prompt) errs.prompt = t('err_prompt');
  const filled = options.filter(Boolean);
  if (filled.length < 2) errs.opts = t('err_opts_min');
  else if (filled.length !== options.length) errs.opts = t('err_opt_empty');
  else if (new Set(options.map((o) => o.toLocaleLowerCase())).size !== options.length) errs.opts = t('err_opt_dup');
  else if (!(Number.isInteger(f.correct) && f.correct >= 0 && f.correct < options.length)) errs.opts = t('err_correct');
  return { errs, payload: { prompt, options, correct_option: f.correct, time_limit_sec: f.time, points: f.points } };
}
$$('#dlg-question [data-close], #dlg-player [data-close], #dlg-settings [data-close], #dlg-deadline [data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
$('#qf-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const { errs, payload } = validateForm();
  $('#qf-prompt-err').textContent = errs.prompt || '';
  $('#qf-opts-err').textContent = errs.opts || '';
  if (errs.prompt) $('#qf-prompt').setAttribute('aria-invalid', 'true');
  if (errs.prompt) { $('#qf-prompt').focus(); return; }
  if (errs.opts) {
    const empty = S.form.options.findIndex((o) => !o.trim());
    (empty >= 0 ? $(`#qf-opt-${empty}`) : S.form.correct === null ? $('#qf-opts input[type=radio]') : $('#qf-opt-0')).focus();
    return;
  }
  const btn = $('#qf-save');
  if (btn.getAttribute('aria-disabled') === 'true') return;
  btn.setAttribute('aria-disabled', 'true');
  try {
    const editing = S.editIdx >= 0;
    const path = editing ? quizPath(S.quiz.pack_id, `/questions/${qId(S.quiz.questions[S.editIdx])}`) : quizPath(S.quiz.pack_id, '/questions');
    const r = await api(path, { method: editing ? 'PUT' : 'POST', json: payload, headers: editHeaders() });
    const saved = { ...payload, ...(r && typeof r === 'object' ? (r.question || r) : {}) };
    if (editing) S.quiz.questions[S.editIdx] = saved; else S.quiz.questions.push(saved);
    rememberQuiz({ ...S.quiz });
    $('#dlg-question').close();
    renderEditor();
    toast(t('quiz_saved'));
    const n = editing ? S.editIdx + 1 : S.quiz.questions.length;
    const b = $(`#ed-list li:nth-child(${n}) button[aria-label="${CSS.escape(t('edit_n', { n }))}"]`);
    (b || $('#ed-add')).focus();
  } catch (err) {
    $('#qf-err').textContent = err.message;
  } finally { btn.removeAttribute('aria-disabled'); }
});

function confirmDialog(title, yes) {
  return new Promise((resolve) => {
    const d = $('#dlg-confirm');
    $('#cf-title').textContent = title;
    $('#cf-yes').textContent = yes;
    d.returnValue = '';
    d.addEventListener('close', () => resolve(d.returnValue === 'yes'), { once: true });
    d.showModal();
    $('#cf-yes').focus();
  });
}

// ================================================================== GAME: realtime
function connect() {
  if (S.conn) S.conn.close();
  S.view = ''; S.names.clear(); S.sideRows.clear();
  $('#names').replaceChildren(); $('#side-list').replaceChildren();
  S.conn = connectLive({
    pin: S.pin, role: 'host', token: S.token,
    onState: render,
    onStatus: connectionPill($('#conn')),
    onFatal: (e) => { lsDel(LS_HOST); toast(e.message || t('game_gone'), { error: true }); leaveGame(); },
  });
}
function leaveGame() {
  if (S.conn) S.conn.close();
  S.conn = null; S.state = null; S.view = '';
  stopTimer(); sfx.stopMusic(); renderMuteBtns();
  $('#controls').hidden = true; $('#top-pin').hidden = true; $('#btn-settings').hidden = true; $('#btn-music').hidden = true;
  initCreate();
  $('#create-title').focus();
}

const settingOf = (st, key, dflt) => {
  if (st && typeof st[key] === 'boolean') return st[key];
  if (st && st.settings && typeof st.settings[key] === 'boolean') return st.settings[key];
  return dflt;
};

function render(st) {
  if (st && st.mode === 'self_paced') { renderHw(st); return; }
  S.state = st;
  const q = st.question;
  const view = st.status === 'ended' ? 'podium' : st.status === 'lobby' ? 'lobby' : `${st.status}:${q ? q.idx : -1}`;
  $('#top-pin').hidden = st.status === 'ended';
  $('#top-pin').textContent = t('game_pin', { pin: st.pin });
  $('#btn-settings').hidden = st.status === 'ended';
  $('#btn-music').hidden = st.status !== 'lobby';
  if (st.status !== 'lobby' && sfx.musicOn) { sfx.stopMusic(); renderMuteBtns(); }

  if (view !== S.view) {
    const first = !S.view;
    S.view = view;
    S.viewAt = Date.now();
    stopTimer();
    const [kind] = view.split(':');
    if (kind === 'lobby') showLobby(st);
    else if (kind === 'question') showQuestion(st, first);
    else if (kind === 'reveal') showReveal(st);
    else if (kind === 'leaderboard') showLeaderboard(st);
    else if (kind === 'podium') showPodium(st);
    renderControls(st);
  }
  // live updates within a view
  if (st.status === 'lobby') updateNames(st);
  if (st.status === 'question') updateAnswered(st);
  if (st.status === 'question') updateSide(st);
}

function renderControls(st) {
  const c = $('#controls');
  const btn = $('#btn-next');
  c.hidden = st.status === 'ended' || st.status === 'lobby';
  const last = st.index >= st.total - 1;
  const label = st.status === 'question' ? t('skip_timer') : st.status === 'reveal' ? t('see_leaderboard')
    : st.status === 'leaderboard' ? (last ? t('finish') : t('next_question')) : t('next');
  btn.replaceChildren(h('span', {}, label), icon('arrow-right'));
  $('#tips-text').textContent = t({ lobby: 'tip_lobby', question: 'tip_question', reveal: 'tip_reveal', leaderboard: 'tip_leaderboard' }[st.status] || 'tip_podium');
  // the lobby has its own Start button, tips live in the controls bar for all game phases
  if (st.status === 'lobby') {
    c.hidden = false; btn.hidden = true;
  } else btn.hidden = false;
}
$('#btn-next').addEventListener('click', () => next());
$('#btn-start').addEventListener('click', () => start());
$('#btn-end').addEventListener('click', async () => {
  if (!(await confirmDialog(t('end_confirm'), t('end_game')))) return;
  try { render(await api(`/api/live/games/${S.pin}/end`, { method: 'POST', headers: { 'X-Host-Token': S.token } })); } catch (e) { toast(e.message, { error: true }); }
});

async function start() {
  if (S.busy) return;
  S.busy = true; sfx.unlock();
  try {
    const st = await api(`/api/live/games/${S.pin}/start`, { method: 'POST', headers: { 'X-Host-Token': S.token } });
    sfx.start();
    render(st);
  } catch (e) { if (e.status !== 409) toast(e.message, { error: true }); S.conn && S.conn.refresh(); } finally { S.busy = false; }
}
async function next() {
  const st = S.state;
  if (S.busy || !st) return;
  // A double-click must not skip the screen that just appeared (server also rejects stale {status,index}).
  if (Date.now() - (S.viewAt || 0) < 800) return;
  S.busy = true; sfx.unlock();
  try {
    const ns = await api(`/api/live/games/${S.pin}/next`, { method: 'POST', json: { status: st.status, index: st.index }, headers: { 'X-Host-Token': S.token } });
    render(ns);
  } catch (e) {
    if (e.status !== 409) toast(e.message, { error: true }); // 409 = stale click, state will catch up
    S.conn && S.conn.refresh();
  } finally { S.busy = false; }
}

// ---------- lobby
function showLobby(st) {
  showScreen('lobby', { focus: false });
  const url = (S.joinUrl || `${location.origin}/play`).replace(/^https?:\/\//, '').replace(/\?pin=\d+$/, '');
  $('#join-url').textContent = url;
  $('#lobby-pin').textContent = st.pin;
  $('#lobby-title').textContent = `${t('game_pin', { pin: st.pin })} — ${url}`;
  $('#lobby-title').setAttribute('tabindex', '-1');
  $('#lobby-title').focus({ preventScroll: true });
}
function updateNames(st) {
  const players = st.players || [];
  $('#lobby-count').textContent = t('players_n', { n: players.length });
  $('#lobby-waiting').hidden = players.length > 0;
  const list = $('#names');
  const seen = new Set();
  let joined = 0;
  for (const p of players) {
    seen.add(p.id);
    let li = S.names.get(p.id);
    if (!li) {
      li = h('li', { class: 'lv-name' }, mascot(mascotFor(p.id), { size: 'xs' }),
        h('span', { class: 'nm' }),
        h('button', { type: 'button', class: 'rn', onclick: () => renamePlayer(p.id) }, icon('pencil')),
        h('button', { type: 'button', class: 'kk', onclick: () => kick(p.id) }, icon('x')));
      S.names.set(p.id, li); list.append(li); joined++;
    }
    li.querySelector('.nm').textContent = p.nickname;
    li.querySelector('.rn').setAttribute('aria-label', t('rename', { name: p.nickname }));
    li.querySelector('.kk').setAttribute('aria-label', t('kick', { name: p.nickname }));
    li.dataset.name = p.nickname;
  }
  for (const [id, li] of S.names) if (!seen.has(id)) { li.remove(); S.names.delete(id); }
  if (joined && S.namesPrimed) { sfx.join(); announce(t('players_n', { n: players.length })); }
  S.namesPrimed = true;
}
async function kick(id) {
  const li = S.names.get(id);
  const name = li ? li.dataset.name : '';
  try {
    const st = await api(`/api/live/games/${S.pin}/players/${id}/kick`, { method: 'POST', headers: { 'X-Host-Token': S.token } });
    toast(t('removed', { name }));
    render(st);
    $('#btn-start').focus();
  } catch (e) { toast(e.message, { error: true }); }
}
function renamePlayer(id) {
  const li = S.names.get(id);
  const d = $('#dlg-player');
  $('#pl-input').value = li ? li.dataset.name : '';
  $('#pl-err').textContent = '';
  d.dataset.id = String(id);
  d.showModal();
  $('#pl-input').select();
}
$('#pl-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const d = $('#dlg-player'); const id = d.dataset.id;
  const nickname = $('#pl-input').value.replace(/\s+/g, ' ').trim();
  if (!nickname) { $('#pl-err').textContent = t('nick_empty'); return; }
  try {
    const st = await api(`/api/live/games/${S.pin}/players/${id}`, { method: 'PATCH', json: { nickname }, headers: { 'X-Host-Token': S.token } });
    d.close();
    if (st && st.status) render(st);
    const li = S.names.get(Number(id)); if (li) li.querySelector('.rn').focus();
    const rb = document.querySelector(`[data-fk="rn-${id}"]`); if (rb) rb.focus();
  } catch (err) { $('#pl-err').textContent = err.status === 409 ? t('nick_taken') : err.message; $('#pl-input').focus(); }
});

// ---------- settings (allow rename / instant feedback), any phase
$('#btn-settings').addEventListener('click', () => {
  const st = S.state || {};
  const instant = settingOf(st, 'instant_feedback', true);
  $('#st-instant-on').checked = instant; $('#st-instant-off').checked = !instant;
  $('#st-rename').checked = settingOf(st, 'allow_rename', true);
  $('#st-err').textContent = '';
  $('#dlg-settings').showModal();
});
$('#st-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = { instant_feedback: $('#st-instant-on').checked, allow_rename: $('#st-rename').checked };
  try {
    const st = await api(`/api/live/games/${S.pin}/settings`, { method: 'PATCH', json: body, headers: { 'X-Host-Token': S.token } });
    $('#dlg-settings').close();
    if (st && st.status) render(st);
    toast(t('settings_saved'));
  } catch (err) { $('#st-err').textContent = err.status === 404 || err.status === 405 ? t('settings_unavailable') : err.message; }
});

// ---------- question
function showQuestion(st) {
  const q = st.question;
  S.ticked = -1;
  showScreen('question', { focus: false });
  $('#hq-count').textContent = t('q_of', { n: q.idx + 1, m: st.total });
  const txt = $('#hq-text');
  txt.textContent = q.prompt || '';
  txt.classList.toggle('is-long', (q.prompt || '').length > 90);
  $('#hq-sub').textContent = isMC(q) ? '' : t('q_unsupported_host'); // quiz-only MVP: legacy non-MC question
  const tiles = $('#hq-tiles');
  if (isMC(q) && Array.isArray(q.options)) {
    tiles.replaceChildren(h('div', { class: 'lv-tiles', role: 'list' }, q.options.map((o, i) =>
      h('div', { class: 'lv-tile', 'data-i': String(i), role: 'listitem', lang: 'en' }, shapeIcon(i), h('span', {}, h('span', { class: 'sr-only' }, `${shapeName(i)}: `), o)))));
  } else tiles.replaceChildren();
  txt.setAttribute('tabindex', '-1'); txt.focus({ preventScroll: true });
  announce(`${t('q_of', { n: q.idx + 1, m: st.total })}. ${q.prompt}`);
  startTimer();
}
function updateAnswered(st) {
  const n = n0(st.answered_count); const m = n0(st.players_count);
  $('#hq-answered').textContent = t('answered_n', { n, m });
  // Everyone answered → reveal (short pause so the last answer registers visually).
  const key = `${st.index}`;
  if (m > 0 && n >= m && S.autoNextFor !== key) { S.autoNextFor = key; setTimeout(() => { if (S.state && S.state.status === 'question' && S.state.index === st.index) next(); }, 1200); }
}
function startTimer() {
  const ring = $('#hq-ring'); const fg = ring.querySelector('.fg'); const C = 2 * Math.PI * 52;
  fg.style.strokeDasharray = String(C);
  const loop = () => {
    const st = S.state; if (!st || st.status !== 'question') return;
    const left = clock.leftMs(st); const total = st.question.time_limit_sec * 1000;
    const sec = Math.max(0, Math.ceil(left / 1000));
    $('#hq-sec').textContent = String(sec);
    ring.setAttribute('aria-label', t('sec_left', { n: sec }));
    fg.style.strokeDashoffset = String(C * (1 - Math.max(0, Math.min(1, left / total))));
    ring.classList.toggle('is-low', left <= 5000);
    if (left <= 5000 && left > 0 && sec !== S.ticked) { S.ticked = sec; sfx.tick(); if (sec === 5) announce(t('sec_left', { n: 5 })); }
    if (left <= 0 && S.ticked !== 0) { S.ticked = 0; sfx.timeUp(); announce(t('time_up')); }
    // after the server's grace window, close the question automatically
    if (left < -GRACE_MS) { const key = `${st.index}`; if (S.autoNextFor !== key) { S.autoNextFor = key; next(); } return; }
    S.timer = setTimeout(loop, 200);
  };
  loop();
}
function stopTimer() { clearTimeout(S.timer); S.timer = 0; }

/** Live ranking side panel: rows keyed by player, moved with transform so rank changes animate. */
function updateSide(st) {
  const instant = settingOf(st, 'instant_feedback', true);
  const rows = lbTop(st) || [...(st.players || [])].sort((a, b) => (b.score - a.score) || String(a.nickname).localeCompare(b.nickname)).map((p) => ({ ...p, player_id: p.id }));
  $('#side-note').textContent = instant ? '' : t('lb_after');
  const list = $('#side-list');
  const top = rows.slice(0, 8);
  const rowH = (list.firstElementChild && list.firstElementChild.offsetHeight) || 44;
  const seen = new Set();
  top.forEach((r, i) => {
    const id = r.player_id ?? r.id ?? r.nickname;
    seen.add(id);
    let li = S.sideRows.get(id);
    if (!li) { li = h('li', {}, h('span', { class: 'lv-lb-rank' }), mascot(mascotFor(id), { size: 'xs' }), h('span', { class: 'lv-lb-name' }), h('span', { class: 'sc' })); S.sideRows.set(id, li); list.append(li); li.style.transform = `translateY(${(i + 1) * (rowH + 6)}px)`; }
    li.querySelector('.lv-lb-rank').textContent = `#${r.rank ?? i + 1}`;
    li.querySelector('.lv-lb-name').textContent = r.nickname;
    li.querySelector('.sc').textContent = fmtInt(r.score);
    requestAnimationFrame(() => { li.style.transform = `translateY(${i * (rowH + 6)}px)`; });
  });
  for (const [id, li] of S.sideRows) if (!seen.has(id)) { li.remove(); S.sideRows.delete(id); }
}

// ---------- reveal
function showReveal(st) {
  const q = st.question; const rv = st.reveal || {}; const corr = rv.correct || {}; const dist = rv.distribution || {};
  showScreen('reveal', { focus: false });
  sfx.reveal();
  $('#rv-q').textContent = q.prompt || '';
  let answer = '';
  if (isMC(q)) answer = corr.option_text || (Number.isInteger(corr.option) ? q.options[corr.option] : '');
  const title = $('#rv-title');
  title.replaceChildren(isMC(q) && Number.isInteger(corr.option) ? h('span', { class: 'lv-shape', style: `color:var(--se-opt-${corr.option + 1}-hi);vertical-align:-0.2em` }, shapeIcon(corr.option)) : '',
    ' ', h('span', { class: 'sr-only' }, `${t('correct_answer')}: `), h('span', { lang: 'en' }, answer), ' ✓');
  const top = Array.isArray(rv.top) ? rv.top : [];
  $('#rv-top').textContent = top.length ? `${t('top3')}: ${top.map((x) => `${x.nickname} (+${fmtInt(x.points)})`).join(' · ')}` : t('nobody_correct');
  const bars = $('#rv-bars');
  let items;
  if (isMC(q) && Array.isArray(dist.options)) {
    items = dist.options.map((n, i) => ({ n, label: q.options[i], i, correct: i === corr.option }));
  } else {
    items = [{ n: (dist.great || 0) + (dist.ok || 0), label: t('dist_great'), color: 'var(--se-success)', correct: true }, { n: dist.retry || 0, label: t('dist_retry'), color: 'var(--se-danger)' }];
  }
  items.push({ n: dist.no_answer || 0, label: t('dist_no'), color: 'var(--se-surface-3)' });
  const max = Math.max(1, ...items.map((x) => x.n));
  bars.replaceChildren(...items.map((x) => h('div', { class: `lv-bar${x.correct ? ' is-correct' : ''}` },
    h('span', { class: 'num' }, String(x.n)),
    h('div', { class: 'fill', style: `height:${Math.max(4, (x.n / max) * 70)}%;background:${x.i !== undefined ? `var(--se-opt-${x.i + 1})` : x.color};color:${x.i !== undefined ? `var(--se-opt-${x.i + 1}-ink)` : 'var(--se-on-fill)'}` },
      null),
    h('span', { lang: x.i !== undefined ? 'en' : null, style: 'text-align:center;overflow-wrap:anywhere;display:flex;gap:6px;align-items:center;justify-content:center' },
      x.i !== undefined ? h('span', { class: 'lv-shape', style: `color:var(--se-opt-${x.i + 1}-hi)` }, shapeIcon(x.i)) : null, x.label, x.correct ? h('span', { class: 'sr-only' }, ` (${t('correct_label')})`) : null))));
  title.setAttribute('tabindex', '-1'); title.focus({ preventScroll: true });
  announce(`${t('correct_answer')}: ${answer}`);
}

// ---------- leaderboard
/** leaderboard is {top:[…], rank_changes} (older builds: a plain array). */
const lbTop = (st) => { const lb = st && st.leaderboard; return Array.isArray(lb) ? lb : (lb && Array.isArray(lb.top) ? lb.top : null); };
function lbRows(st, n) { return (lbTop(st) || []).slice(0, n); }
function showLeaderboard(st) {
  showScreen('leaderboard');
  const rows = lbRows(st, 5);
  $('#lb-rows').replaceChildren(...(rows.length ? rows : [{ rank: '–', nickname: t('lb_none'), score: 0 }]).map((r, i) => {
    const d = Number(r.delta_rank || 0);
    const li = h('li', { class: 'lv-lb-row', style: `animation-delay:${i * 90}ms` },
      h('span', { class: 'lv-lb-rank' }, `#${r.rank}`),
      r.player_id !== undefined || r.nickname ? mascot(mascotFor(r.player_id ?? r.nickname), { size: 'sm' }) : null,
      h('span', { class: 'lv-lb-name' }, r.nickname),
      d ? h('span', { class: `lv-delta ${d > 0 ? 'up' : 'down'}` }, d > 0 ? `▲ ${t('rank_up', { n: d })}` : `▼ ${t('rank_down', { n: -d })}`) : null,
      h('span', {}, fmtInt(r.score)));
    return li;
  }));
}

// ---------- podium
function showPodium(st) {
  showScreen('podium');
  lsDel(LS_HOST); forgetGame(S.pin, S.token);
  const rows = lbRows(st, 3);
  const order = [1, 0, 2].filter((i) => rows[i]);
  $('#podium').replaceChildren(...order.map((i) => {
    const r = rows[i];
    const place = Math.min(3, Math.max(1, Number(r.rank) || i + 1));
    return h('li', { class: `lv-step p${i + 1}` },
      mascot(mascotFor(r.player_id ?? r.nickname), { size: i === 0 ? 'lg' : 'md' }),
      h('span', { class: 'who' }, r.nickname),
      h('div', { class: 'blk' }, h('span', { class: 'lv-place', 'aria-hidden': 'true' }, place === 1 ? icon('trophy') : null, String(place)), h('span', { class: 'sr-only' }, t('rank_n', { n: r.rank })),
        h('small', {}, `${fmtInt(r.score)} ${t('pts')}`)));
  }));
  const sm = st.summary || {};
  $('#pd-summary').textContent = t('summary_line', { j: n0(sm.joined ?? st.players_count), a: n0(sm.answered_any) });
  $('#pd-csv').href = `/api/live/games/${S.pin}/report.csv?host_token=${encodeURIComponent(S.token)}`;
  sfx.fanfare();
  confetti($('#fx-canvas'));
  if (S.conn) S.conn.close();
}
$('#pd-new').addEventListener('click', () => { lsDel(LS_HOST); leaveGame(); });

// ================================================================== "How will students play?" (live · homework · presenter)
const MODES = ['live', 'hw', 'present'];
S.mode = MODES.includes(lsGet(LS_MODE)) ? lsGet(LS_MODE) : 'live';
function createLabel() { return t(S.mode === 'hw' ? 'create_hw' : S.mode === 'present' ? 'open_presenter' : 'create'); }
function applyMode() {
  const m = S.mode;
  const r = $(`#mode-${m}`); if (r) r.checked = true;
  $$('#create-form [data-modes]').forEach((el) => { el.hidden = !el.dataset.modes.split(' ').includes(m); });
  $('#setup-title').textContent = t(m === 'hw' ? 'setup_title_hw' : m === 'present' ? 'setup_title_present' : 'setup_title');
  if ($('#btn-create').getAttribute('aria-disabled') !== 'true') $('#btn-create').textContent = createLabel();
}
$$('input[name="mode"]').forEach((inp) => inp.addEventListener('change', () => {
  if (!inp.checked) return;
  S.mode = inp.value; lsSet(LS_MODE, S.mode);
  $('#create-err').textContent = '';
  applyMode();
}));

function openPresenter(school) {
  const grouping = $('#g-grp-teams').checked ? 'teams' : 'individual';
  const q = new URLSearchParams({ pack: String(S.selected.pack_id), grouping, school });
  location.href = `/classroom?${q}`;
}

// ---------- deadline picker (create form + "Change deadline" dialog): chips + date + time, local time → ISO
const DAY = 86400000;
const DL_CHIPS = [{ k: 'tomorrow', d: 1, l: 'dl_tomorrow' }, { k: '3d', d: 3, l: 'dl_3d' }, { k: '1w', d: 7, l: 'dl_1w' }, { k: 'none', l: 'dl_none' }];
const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
function deadlinePicker(p) {
  const P = { chip: '1w' };
  const date = $(`#${p}-dl-date`); const time = $(`#${p}-dl-time`); const err = $(`#${p}-dl-err`);
  const clearErr = () => { err.textContent = ''; date.removeAttribute('aria-invalid'); time.removeAttribute('aria-invalid'); };
  function render() {
    $(`#${p}-dl-chips`).replaceChildren(...DL_CHIPS.flatMap((c) => {
      const inp = h('input', { type: 'radio', name: `${p}-dl`, id: `${p}-dl-${c.k}`, value: c.k, checked: P.chip === c.k });
      inp.addEventListener('change', () => { if (inp.checked) pick(c.k); });
      return [inp, h('label', { for: `${p}-dl-${c.k}` }, t(c.l))];
    }));
    $(`#${p}-dl-fields`).hidden = P.chip === 'none';
  }
  function pick(k) {
    P.chip = k; clearErr();
    const c = DL_CHIPS.find((x) => x.k === k);
    if (c && c.d) { const d = new Date(Date.now() + c.d * DAY); date.value = ymd(d); time.value = '23:59'; }
    $(`#${p}-dl-fields`).hidden = k === 'none';
    $$(`#${p}-dl-chips input`).forEach((i) => { i.checked = i.value === k; });
  }
  const custom = () => { P.chip = 'custom'; clearErr(); $$(`#${p}-dl-chips input`).forEach((i) => { i.checked = false; }); };
  date.addEventListener('input', custom); time.addEventListener('input', custom);
  function set(iso) {
    if (!iso) { pick('none'); return; }
    const d = new Date(iso);
    P.chip = 'custom'; render();
    date.value = ymd(d); time.value = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }
  /** {closes_at: ISO|null} or {error} (shown next to the fields). */
  function value() {
    if (P.chip === 'none') return { closes_at: null };
    let msg = '';
    const d = date.value && time.value ? new Date(`${date.value}T${time.value}`) : null;
    if (!d || Number.isNaN(d.getTime())) msg = t('err_deadline_empty');
    else if (d.getTime() <= Date.now() + 60000) msg = t('err_deadline_past');
    else if (d.getTime() > Date.now() + 30 * DAY) msg = t('err_deadline_far');
    if (msg) {
      err.textContent = msg; date.setAttribute('aria-invalid', 'true'); time.setAttribute('aria-invalid', 'true');
      date.focus();
      return { error: msg };
    }
    return { closes_at: d.toISOString() };
  }
  render(); pick('1w');
  return { render, pick, set, value, clearErr };
}
const DL = { create: deadlinePicker('g'), dialog: deadlinePicker('dd') };
applyMode();

// ---------- create homework
async function createHomework(school) {
  const dl = DL.create.value();
  if (dl.error) { $('#create-err').textContent = dl.error; return; }
  const btn = $('#btn-create');
  const body = {
    pack_id: S.selected.pack_id, game_modes: ['multiple_choice'],
    question_count: Number(($('#g-count input:checked') || {}).value || 10),
    title: $('#g-title').value.trim() || S.selected.name,
    teacher_name: $('#g-teacher').value.trim(), school, program: '',
    mode: 'self_paced', closes_at: dl.closes_at,
    speed_bonus: $('#g-speed').checked, shuffle_per_player: $('#g-shuffle').checked, allow_rename: $('#g-rename').checked,
  };
  btn.setAttribute('aria-disabled', 'true'); btn.textContent = t('creating');
  try {
    const r = await api('/api/live/games', { method: 'POST', json: body });
    rememberGame({ pin: r.pin, host_token: r.host_token, title: r.title || body.title, closes_at: r.closes_at ?? body.closes_at, mode: 'self_paced', join_url: r.join_url });
    openHw({ pin: r.pin, host_token: r.host_token, join_url: r.join_url }, 'share');
  } catch (err) {
    $('#create-err').textContent = err.status === 422 && /enough/i.test(err.message) ? t('not_enough') : err.message;
  } finally { btn.removeAttribute('aria-disabled'); btn.textContent = createLabel(); }
}

// ================================================================== "My games" (this device; localStorage)
const gameKey = (g) => `${g.pin}.${String(g.host_token).slice(0, 10)}`;
const myGames = () => { const v = lsGet(LS_GAMES); return Array.isArray(v) ? v.filter((g) => g && /^\d{6}$/.test(String(g.pin)) && g.host_token) : []; };
function rememberGame(g) {
  const list = myGames().filter((x) => gameKey(x) !== gameKey(g));
  list.unshift({ ...g, created_at: g.created_at || new Date().toISOString() });
  lsSet(LS_GAMES, list.slice(0, 20));
}
function patchGame(g, patch) { lsSet(LS_GAMES, myGames().map((x) => (gameKey(x) === gameKey(g) ? { ...x, ...patch } : x))); }
function forgetGame(pin, token) { if (pin && token) lsSet(LS_GAMES, myGames().filter((x) => gameKey(x) !== gameKey({ pin, host_token: token }))); }

function mgStatus(g, st) {
  if (!st) return t('mg_loading');
  if (st.mode === 'self_paced') {
    if (st.status === 'ended') return t('hw_status_closed');
    const pr = st.progress || {};
    const due = st.closes_at ? t('closes_at', { when: fmtWhen(st.closes_at) }) : t('no_deadline');
    return `${st.paused ? `${t('hw_status_paused')} · ` : ''}${t('mg_progress', { f: pr.finished || 0, j: pr.joined || 0 })} · ${due}`;
  }
  return st.status === 'lobby' ? t('mg_lobby') : t('mg_running');
}
function mgRow(g, st) {
  const hw = g.mode === 'self_paced';
  const ended = st && st.status === 'ended';
  const title = (st && st.title) || g.title || t('untitled');
  const id = `mg-${gameKey(g).replace(/[^\w-]/g, '_')}`;
  return h('li', { class: 'hw-mg-row', 'data-key': gameKey(g), 'aria-labelledby': id },
    h('span', { class: `lv-tag${hw ? '' : ' lv-tag-general'}` }, icon(hw ? 'calendar-clock' : 'play'), hw ? t('mg_hw') : t('mg_live')),
    h('div', { class: 'hw-mg-main' },
      h('strong', { id }, title),
      h('span', { class: 'lv-hint' }, `${t('game_pin', { pin: g.pin })} · ${mgStatus(g, st)}`)),
    h('div', { class: 'lv-row hw-mg-actions' },
      h('button', { type: 'button', class: `lv-btn lv-btn-sm ${ended ? '' : 'lv-btn-dark'}`, 'aria-label': `${hw ? (ended ? t('mg_results') : t('mg_monitor')) : t('mg_continue')}: ${title}`,
        onclick: () => (hw ? openHw(g, 'monitor') : (S.pin = g.pin, S.token = g.host_token, S.joinUrl = g.join_url, connect())) },
      icon(hw ? 'chart-column' : 'play'), hw ? (ended ? t('mg_results') : t('mg_monitor')) : t('mg_continue')),
      h('button', { type: 'button', class: 'lv-icon-btn hw-mg-x', 'aria-label': t('mg_forget', { title }), 'data-fk': `mgx-${gameKey(g)}`,
        onclick: (e) => { forgetGame(g.pin, g.host_token); const li = e.currentTarget.closest('li'); const nxt = li.nextElementSibling || li.previousElementSibling; li.remove(); if (nxt) nxt.querySelector('button').focus(); else { $('#mygames').hidden = true; $('#create-title').focus(); } } },
      icon('x'))));
}
async function renderMyGames() {
  const list = myGames();
  const box = $('#mygames');
  box.hidden = !list.length;
  if (!list.length) return;
  const ul = $('#mg-list');
  ul.replaceChildren(...list.map((g) => mgRow(g, null)));
  const seq = (S.mgSeq = (S.mgSeq || 0) + 1);
  await Promise.all(list.map(async (g) => {
    const row = () => [...ul.children].find((li) => li.dataset.key === gameKey(g));
    try {
      const st = await api(`/api/live/games/${g.pin}/state?host_token=${encodeURIComponent(g.host_token)}`);
      if (seq !== S.mgSeq || !row()) return;
      if (st.mode !== 'self_paced' && st.status === 'ended') { forgetGame(g.pin, g.host_token); row().remove(); return; }
      patchGame(g, { title: st.title, closes_at: st.closes_at ?? null, status: st.status, mode: st.mode === 'self_paced' ? 'self_paced' : 'live' });
      const fk = document.activeElement && row().contains(document.activeElement) ? [...row().querySelectorAll('button')].indexOf(document.activeElement) : -1;
      const nr = mgRow({ ...g, mode: st.mode === 'self_paced' ? 'self_paced' : 'live' }, st);
      row().replaceWith(nr);
      if (fk >= 0) nr.querySelectorAll('button')[fk].focus();
    } catch (e) {
      if ((e.status === 403 || e.status === 404) && seq === S.mgSeq) { forgetGame(g.pin, g.host_token); const r = row(); if (r) r.remove(); }
    }
  }));
  if (seq === S.mgSeq) box.hidden = !ul.children.length;
}

// ================================================================== HOMEWORK: share + monitor (SSE)
function openHw(g, view) {
  if (S.conn) S.conn.close();
  S.conn = null; S.state = null; S.view = '';
  S.pin = String(g.pin); S.token = g.host_token; S.joinUrl = g.join_url || `${location.origin}/play?pin=${g.pin}`;
  S.conn = connectLive({
    pin: S.pin, role: 'host', token: S.token,
    onState: render,
    onStatus: connectionPill($('#conn')),
    onFatal: (e) => { forgetGame(S.pin, S.token); lsDel(LS_HW); toast(e.message || t('game_gone'), { error: true }); leaveHw(true); },
  });
  hwShow(view);
}
function hwShow(name, { push = true } = {}) {
  S.hwView = name;
  lsSet(LS_HW, { pin: S.pin, host_token: S.token, join_url: S.joinUrl, view: name });
  if (push && !(history.state && history.state.host === name)) { try { history.pushState({ host: name }, ''); } catch { /* ignore */ } }
  $('#top-pin').hidden = false; $('#top-pin').textContent = t('game_pin', { pin: S.pin });
  $('#btn-settings').hidden = true; $('#btn-music').hidden = true; $('#controls').hidden = true;
  showScreen(name);
  if (name === 'share') fillShare(S.state); else fillMonitor(S.state);
}
function leaveHw(silent = false) {
  const open = S.state && S.state.status !== 'ended';
  if (S.conn) S.conn.close();
  S.conn = null; S.state = null; S.view = ''; S.pin = ''; S.token = '';
  lsDel(LS_HW);
  $('#top-pin').hidden = true; $('#conn').hidden = true;
  initCreate();
  $('#create-title').setAttribute('tabindex', '-1'); $('#create-title').focus();
  if (open && !silent) toast(t('hw_keeps_running'), { ms: 5000 });
}
function renderHw(st) {
  S.state = st;
  if (!S.pin) return;
  patchGame({ pin: S.pin, host_token: S.token }, { title: st.title, closes_at: st.closes_at ?? null, status: st.status, mode: 'self_paced' });
  if (S.screen === 'share') fillShare(st);
  else if (S.screen === 'monitor') fillMonitor(st);
}
const hwApi = (path, opts = {}) => api(`/api/live/games/${S.pin}${path}`, { ...opts, headers: { 'X-Host-Token': S.token, ...(opts.headers || {}) } });

// ---------- share
const shortUrl = (u) => String(u || '').replace(/^https?:\/\//, '').replace(/\?pin=\d+$/, '');
function boardText(st) {
  const due = st && st.closes_at;
  return due ? t('hw_board_text', { url: shortUrl(S.joinUrl), pin: S.pin, when: fmtWhen(due) }) : t('hw_board_text_nodl', { url: shortUrl(S.joinUrl), pin: S.pin });
}
function fillShare(st) {
  $('#sh-pin').textContent = S.pin;
  $('#sh-url').value = S.joinUrl;
  $('#sh-game').textContent = (st && st.title) || '';
  $('#sh-due span').textContent = st ? (st.status === 'ended' ? t('hw_status_closed') : st.closes_at ? t('closes_at', { when: fmtWhen(st.closes_at) }) : t('no_deadline')) : '…';
  $('#sh-board').textContent = boardText(st);
}
async function copyText(text, okMsg) {
  try { await navigator.clipboard.writeText(text); toast(okMsg); } catch { toast(t('copy_fail', { url: text }), { ms: 12000 }); }
}
$('#sh-copy').addEventListener('click', () => { $('#sh-url').select(); copyText(S.joinUrl, t('link_copied')); });
$('#sh-copy-text').addEventListener('click', () => copyText(boardText(S.state), t('text_copied')));
$('#sh-print').addEventListener('click', () => { try { window.print(); } catch { /* ignore */ } });
$('#sh-monitor').addEventListener('click', () => hwShow('monitor'));
$('#mo-share').addEventListener('click', () => hwShow('share'));

// ---------- monitor
function td(...c) { return h('td', {}, ...c); }
function miniBar(frac) { return h('span', { class: 'hw-mini', 'aria-hidden': 'true' }, h('span', { style: `width:${Math.round(Math.max(0, Math.min(1, frac)) * 100)}%` })); }
function fillMonitor(st) {
  if (!st) { $('#mo-title').textContent = '…'; return; }
  const ended = st.status === 'ended';
  const fk = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.fk : '';
  $('#mo-title').textContent = st.title || '';
  const stat = $('#mo-status');
  stat.className = `lv-pill ${ended ? '' : st.paused ? 'lv-pill-warn' : 'hw-pill-ok'}`;
  stat.replaceChildren(icon(ended ? 'lock' : st.paused ? 'pause' : 'circle-check'), h('span', {}, ended ? t('hw_status_closed') : st.paused ? t('hw_status_paused') : t('hw_status_open')));
  $('#mo-pin').textContent = t('game_pin', { pin: st.pin });
  $('#mo-due').replaceChildren(icon('calendar-clock'), h('span', {}, st.closes_at ? (ended ? fmtWhen(st.closes_at) : t('closes_at', { when: fmtWhen(st.closes_at) })) : t('no_deadline')));
  $('#mo-csv').href = `/api/live/games/${S.pin}/report.csv?host_token=${encodeURIComponent(S.token)}`;
  const pb = $('#mo-pause');
  iconLabel(pb, st.paused ? 'play' : 'pause', st.paused ? t('resume_game') : t('pause'));
  for (const b of [pb, $('#mo-deadline'), $('#mo-end')]) { if (ended) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled'); }
  $('#mo-pause-warn').hidden = ended;
  $('#mo-rename').checked = !!(st.settings && st.settings.allow_rename);

  // progress summary + stacked bar (finished | in progress | not started)
  const pr = st.progress || { joined: 0, in_progress: 0, finished: 0 };
  const j = pr.joined || 0; const f = pr.finished || 0; const p = pr.in_progress || 0;
  $('#mo-joined').textContent = fmtInt(j); $('#mo-inprog').textContent = fmtInt(p); $('#mo-fin').textContent = fmtInt(f);
  const bar = $('#mo-bar');
  bar.setAttribute('aria-valuemax', String(Math.max(j, 1))); bar.setAttribute('aria-valuenow', String(f));
  bar.setAttribute('aria-valuetext', t('prog_bar', { f, j, p }));
  bar.querySelector('.is-fin').style.width = `${j ? (100 * f) / j : 0}%`;
  bar.querySelector('.is-prog').style.width = `${j ? (100 * p) / j : 0}%`;
  $('#mo-bar-text').replaceChildren(
    h('span', { class: 'hw-key is-fin' }), `${t('prog_finished')} ${f}`,
    h('span', { class: 'hw-key is-prog' }), `${t('prog_in_progress')} ${p}`,
    h('span', { class: 'hw-key' }), `${t('prog_not_started')} ${Math.max(0, j - f - p)}`);

  // students
  const players = st.players || [];
  $('#mo-empty').hidden = players.length > 0;
  $('#mo-students').hidden = !players.length;
  $('#mo-students').replaceChildren(
    h('caption', { class: 'sr-only' }, t('students')),
    h('thead', {}, h('tr', {}, ...['col_name', 'col_progress', 'col_score', 'col_finished', 'col_last', 'col_actions'].map((k) => h('th', { scope: 'col' }, t(k))))),
    h('tbody', {}, players.map((pl) => {
      const n = Math.min(pl.current_idx || 0, pl.total || st.total || 0); const m = pl.total || st.total || 0;
      const done = !!pl.finished_at;
      return h('tr', { class: done ? 'is-done' : '' },
        h('th', { scope: 'row' }, h('span', { class: 'hw-name' }, mascot(mascotFor(pl.id), { size: 'xs' }), h('span', {}, pl.nickname))),
        td(h('span', { class: 'hw-prog-cell' }, `${n}/${m}`, miniBar(m ? n / m : 0))),
        td(fmtInt(pl.score)),
        td(done ? h('span', { class: 'hw-done' }, icon('circle-check'), fmtWhen(pl.finished_at)) : '—'),
        td(h('span', { title: fmtWhen(pl.last_active_at) }, fmtAgo(pl.last_active_at))),
        td(h('span', { class: 'hw-acts' },
          h('button', { type: 'button', class: 'lv-icon-btn', 'data-fk': `rn-${pl.id}`, 'aria-label': t('rename', { name: pl.nickname }), title: t('rename', { name: pl.nickname }), onclick: () => hwRename(pl) }, icon('pencil')),
          h('button', { type: 'button', class: 'lv-icon-btn hw-kick', 'data-fk': `kk-${pl.id}`, 'aria-label': t('kick', { name: pl.nickname }), title: t('kick', { name: pl.nickname }), onclick: () => hwKick(pl) }, icon('x')))));
    })));

  // per question
  $('#mo-questions').replaceChildren(
    h('caption', { class: 'sr-only' }, t('per_question')),
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, '#'), ...['col_q', 'col_answered', 'col_correct'].map((k) => h('th', { scope: 'col' }, t(k))))),
    h('tbody', {}, (st.per_question || []).map((q) => h('tr', {},
      td(String(q.idx + 1)),
      h('th', { scope: 'row', class: 'hw-qtext', lang: 'en' }, q.prompt),
      td(fmtInt(q.answered)),
      td(q.correct_pct === null || q.correct_pct === undefined ? '—' : h('span', { class: 'hw-prog-cell' }, `${Math.round(q.correct_pct)}%`, miniBar(q.correct_pct / 100)))))));

  // leaderboard
  const top = (st.leaderboard && Array.isArray(st.leaderboard.top)) ? st.leaderboard.top : [];
  $('#mo-lb').replaceChildren(...(top.length ? top.map((r) => h('li', {},
    h('span', { class: 'lv-lb-rank' }, `#${r.rank}`), mascot(mascotFor(r.player_id ?? r.nickname), { size: 'xs' }),
    h('span', { class: 'lv-lb-name' }, r.nickname), h('span', {}, fmtInt(r.score)))) : [h('li', {}, t('lb_none'))]));
  if (fk) { const el = document.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (el && el !== document.activeElement) el.focus(); }
}
// "last active" is relative: refresh it while the monitor is open
setInterval(() => { if (S.screen === 'monitor' && S.state && S.state.mode === 'self_paced') fillMonitor(S.state); }, 30000);

const disabled = (b) => b.getAttribute('aria-disabled') === 'true';
$('#mo-pause').addEventListener('click', async (e) => {
  const st = S.state; if (!st || disabled(e.currentTarget)) return;
  try {
    const ns = await hwApi('/settings', { method: 'PATCH', json: { paused: !st.paused } });
    render(ns); toast(ns.paused ? t('paused_toast') : t('resumed_toast'));
  } catch (err) { toast(err.message, { error: true }); }
});
$('#mo-rename').addEventListener('change', async (e) => {
  const want = e.currentTarget.checked;
  try { render(await hwApi('/settings', { method: 'PATCH', json: { allow_rename: want } })); toast(t('settings_saved')); } catch (err) { e.currentTarget.checked = !want; toast(err.message, { error: true }); }
});
$('#mo-end').addEventListener('click', async (e) => {
  if (disabled(e.currentTarget)) return;
  if (!(await confirmDialog(t('hw_end_confirm'), t('end_now')))) { $('#mo-end').focus(); return; }
  try { render(await hwApi('/end', { method: 'POST' })); toast(t('hw_ended_toast')); $('#mo-title').focus(); } catch (err) { toast(err.message, { error: true }); }
});
$('#mo-deadline').addEventListener('click', (e) => {
  if (disabled(e.currentTarget)) return;
  DL.dialog.render(); DL.dialog.set(S.state && S.state.closes_at); DL.dialog.clearErr();
  $('#dd-err').textContent = '';
  $('#dlg-deadline').showModal();
  ($('#dd-dl-chips input:checked') || $('#dd-dl-date')).focus();
});
$('#dlg-deadline').addEventListener('close', () => { if (S.screen === 'monitor') $('#mo-deadline').focus(); });
$('#dd-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const v = DL.dialog.value();
  if (v.error) return;
  try {
    render(await hwApi('/settings', { method: 'PATCH', json: { closes_at: v.closes_at } }));
    $('#dlg-deadline').close(); toast(t('deadline_saved'));
  } catch (err) { $('#dd-err').textContent = err.message; }
});
async function hwKick(pl) {
  if (!(await confirmDialog(t('remove_confirm', { name: pl.nickname }), t('remove')))) { const b = document.querySelector(`[data-fk="kk-${pl.id}"]`); if (b) b.focus(); return; }
  try {
    render(await hwApi(`/players/${pl.id}/kick`, { method: 'POST' }));
    toast(t('removed', { name: pl.nickname }));
    const b = document.querySelector('#mo-students [data-fk^="rn-"]') || $('#mo-title'); b.focus();
  } catch (err) { toast(err.message, { error: true }); }
}
function hwRename(pl) {
  const d = $('#dlg-player');
  $('#pl-input').value = pl.nickname; $('#pl-err').textContent = '';
  d.dataset.id = String(pl.id);
  d.showModal(); $('#pl-input').select();
}

// ================================================================== boot
renderCounts(); renderSelected(); renderMine();
loadPacks();
const editParam = new URLSearchParams(location.search).get('edit');
if (editParam && /^[^.]+\.[^.]+$/.test(editParam)) {
  const [pid, key] = editParam.split('.');
  initCreate();
  openEditor(/^\d+$/.test(pid) ? Number(pid) : pid, key);
} else {
  const saved = lsGet(LS_HOST);
  const hw = lsGet(LS_HW);
  if (saved && saved.pin && saved.host_token) { S.pin = saved.pin; S.token = saved.host_token; S.joinUrl = saved.join_url; initCreate(); connect(); }
  else if (hw && hw.pin && hw.host_token) { initCreate(); openHw(hw, hw.view === 'share' ? 'share' : 'monitor'); }
  else initCreate();
}
