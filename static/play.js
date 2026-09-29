// play.js — student device for the live quiz. PIN → nickname → wait → answer tiles → result → final.
// Never touches the microphone (quiz MVP). Survives refresh: {pin, token} in localStorage.
import { t, applyI18n, mountLangSwitch, onLangChange, fmtInt, BRAND } from './i18n.js';
import { applyPrefs } from './a11y-prefs.js';
import {
  $, h, api, lsGet, lsSet, lsDel, clock, connectLive, connectionPill, announce, toast,
  shapeIcon, shapeName, showScreen as showScreenRaw, isMC, sfx, icon, iconLabel, mascot, mascotFor, fmtWhen,
} from './live-common.js';

const LS_PLAYER = 'live.player';
const GRACE_MS = 3000;

const S = {
  pin: '', token: '', nickname: '', conn: null, state: null,
  view: '',            // current rendered view key, so a state update doesn't re-render (and steal focus)
  sending: false, warned: false, timerRaf: 0, lastRankPill: '',
};

applyPrefs();
applyI18n();
try { const m = document.createElement('meta'); m.name = 'theme-color'; m.content = getComputedStyle(document.documentElement).getPropertyValue('--se-bg').trim(); document.head.append(m); } catch { /* ignore */ }
mountLangSwitch($('#lang'));
onLangChange(() => { S.view = ''; if (S.state) render(S.state); else rerenderStatic(); syncNav(S.screen); });
document.title = `${t('play_title')} · ${BRAND.name}`;

// ------------------------------------------------------------------ back navigation + browser history
// pin (Back → home) · nick (Back → PIN) · in a game: "Leave game" (confirm; token kept, so the same PIN rejoins)
// · final / gone: Back → home. Browser Back mirrors the on-screen button (pushState per step, popstate).
const IN_GAME = new Set(['wait', 'question', 'sent', 'result', 'intro', 'paused']);
function showScreen(name, opts) {
  const prev = S.screen;
  const r = showScreenRaw(name, opts);
  S.screen = name;
  try {
    if (name === 'nick' && prev !== 'nick') history.pushState({ play: 'nick' }, '');
    else if (IN_GAME.has(name) && !S.guarded) { history.pushState({ play: 'game' }, ''); S.guarded = true; }
  } catch { /* ignore */ }
  syncNav(name);
  return r;
}
function syncNav(name) {
  const bar = $('#backbar'); const b = $('#nav-back');
  if (!name) { bar.hidden = true; return; }
  bar.hidden = false;
  if (IN_GAME.has(name)) iconLabel(b, 'log-out', t('leave_game'));
  else iconLabel(b, 'arrow-left', name === 'pin' || name === 'final' || name === 'gone' ? t('back_home') : t('back'));
}
async function goBack(fromHistory = false) {
  const name = S.screen;
  if (name === 'nick') {
    if (history.state && history.state.play === 'nick') { history.back(); return; } // popstate shows the PIN screen
    S.pin = ''; showScreen('pin'); $('#pin').focus(); return;
  }
  if (IN_GAME.has(name)) {
    if (fromHistory) { try { history.pushState({ play: 'game' }, ''); } catch { /* ignore */ } } // stay unless confirmed
    const d = $('#dlg-leave'); d.returnValue = '';
    $('#lv-sub').textContent = isSP(S.state) ? t('hw_leave_sub') : t('leave_sub');
    const yes = await new Promise((res) => { d.addEventListener('close', () => res(d.returnValue === 'yes'), { once: true }); d.showModal(); $('#lv-yes').focus(); });
    if (!yes) { $('#nav-back').focus(); return; }
    if (S.conn) S.conn.close();
    location.href = '/';
    return;
  }
  location.href = '/';
}
$('#nav-back').addEventListener('click', () => goBack(false));
window.addEventListener('popstate', () => {
  if (document.querySelector('dialog[open]')) { document.querySelectorAll('dialog[open]').forEach((d) => d.close()); }
  if (S.screen === 'nick') { S.pin = ''; showScreenRaw('pin'); S.screen = 'pin'; syncNav('pin'); $('#pin').focus(); return; }
  if (IN_GAME.has(S.screen)) { goBack(true); return; }
  if (S.screen === 'final' || S.screen === 'gone') location.href = '/';
});

function rerenderStatic() { $('#nick-pin').textContent = t('game_pin', { pin: S.pin }); }

// ------------------------------------------------------------------ boot
const params = new URLSearchParams(location.search);
const urlPin = (params.get('pin') || '').replace(/\D/g, '').slice(0, 6);
const saved = lsGet(LS_PLAYER);
if (saved && saved.pin && saved.token && (!urlPin || urlPin === saved.pin)) {
  S.pin = saved.pin; S.token = saved.token; S.nickname = saved.nickname || '';
  connect();
} else if (urlPin.length === 6) {
  $('#pin').value = urlPin;
  checkPin(urlPin);
} else {
  showScreen('pin');
  $('#pin').focus();
}

// ------------------------------------------------------------------ PIN + nickname
$('#pin').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6); setErr('#pin', ''); });
$('#pin-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const pin = $('#pin').value.trim();
  if (!/^\d{6}$/.test(pin)) { setErr('#pin', t('pin_invalid')); $('#pin').focus(); return; }
  checkPin(pin);
});

function setErr(inputSel, msg) {
  const inp = $(inputSel);
  const err = $(`${inputSel}-err`) || $(`#${inp.id}-err`);
  err.textContent = msg;
  if (msg) inp.setAttribute('aria-invalid', 'true'); else inp.removeAttribute('aria-invalid');
}

async function checkPin(pin) {
  try {
    const g = await api(`/api/live/games/${pin}`);
    if (g && g.mode === 'self_paced' && g.paused && g.status !== 'ended') {
      showScreen('pin'); setErr('#pin', t('pin_paused')); $('#pin').focus(); return;
    }
    if (g && (g.joinable === false || g.status === 'ended')) {
      showScreen('pin'); setErr('#pin', t('pin_ended')); $('#pin').focus(); return;
    }
    S.pin = pin;
    rerenderStatic();
    showScreen('nick');
    $('#nick').focus();
  } catch (err) {
    showScreen('pin');
    setErr('#pin', err.status === 404 ? t('pin_notfound') : err.status === 429 ? t('too_many') : err.message);
    $('#pin').focus();
  }
}

$('#nick').addEventListener('input', () => setErr('#nick', ''));
$('#nick-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const nickname = $('#nick').value.replace(/\s+/g, ' ').trim();
  if (!nickname) { setErr('#nick', t('nick_empty')); $('#nick').focus(); return; }
  const btn = e.submitter || $('#nick-form button');
  if (btn.getAttribute('aria-disabled') === 'true') return;
  btn.setAttribute('aria-disabled', 'true');
  sfx.unlock();
  try {
    const r = await api(`/api/live/games/${S.pin}/join`, { method: 'POST', json: { nickname } });
    S.token = r.player_token; S.nickname = r.nickname || nickname;
    lsSet(LS_PLAYER, { pin: S.pin, token: S.token, nickname: S.nickname, id: r.player_id });
    connect();
  } catch (err) {
    const msg = err.status === 409 && /taken/i.test(err.message) ? t('nick_taken')
      : err.status === 409 && /paus/i.test(err.message) ? t('pin_paused')
      : err.status === 409 ? t('pin_ended') : err.status === 429 ? t('too_many')
        : err.status === 404 ? t('pin_notfound') : err.message;
    setErr('#nick', msg);
    $('#nick').focus();
  } finally { btn.removeAttribute('aria-disabled'); }
});

// ------------------------------------------------------------------ realtime
function connect() {
  if (S.conn) S.conn.close();
  S.view = '';
  S.conn = connectLive({
    pin: S.pin, role: 'player', token: S.token,
    onState: render,
    onStatus: connectionPill($('#conn')),
    onKicked: () => gone(t('kicked_title'), t('kicked_sub')),
    onFatal: (e) => gone(t('game_gone'), e.status === 404 ? '' : e.message),
  });
}

function gone(title, sub) {
  lsDel(LS_PLAYER);
  stopTimer();
  $('#bar').hidden = true;
  $('#sp-prog').hidden = true;
  $('#conn').hidden = true;
  $('#gone-title').textContent = title;
  $('#gone-sub').textContent = sub || '';
  S.view = 'gone';
  showScreen('gone');
}

const settingOf = (st, key, dflt) => {
  if (st && typeof st[key] === 'boolean') return st[key];
  if (st && st.settings && typeof st.settings[key] === 'boolean') return st.settings[key];
  return dflt;
};

// ------------------------------------------------------------------ render
function render(st) {
  S.state = st;
  const me = st.me || {};
  if (me.nickname && me.nickname !== S.nickname) {
    S.nickname = me.nickname;
    const sv = lsGet(LS_PLAYER); if (sv) lsSet(LS_PLAYER, { ...sv, nickname: S.nickname });
  }
  renderBar(st);
  if (isSP(st)) { renderSP(st); return; }
  $('#sp-prog').hidden = true;
  const q = st.question;
  let view;
  if (st.status === 'lobby') view = 'lobby';
  else if (st.status === 'ended') view = 'final';
  else if (st.status === 'question' && q) {
    if (me.answered_current) view = me.last_result ? `res:${q.idx}` : `sent:${q.idx}`;
    else {
      const left = clock.leftMs(st);
      view = left !== null && left < -GRACE_MS ? `late:${q.idx}` : `q:${q.idx}`;
    }
  } else if (q) view = `res:${q.idx}`; // reveal / leaderboard
  else view = 'lobby';

  if (view !== S.view) {
    S.view = view;
    const [kind] = view.split(':');
    stopTimer();
    if (kind === 'lobby') showWait(t('in_title'), t('in_sub'));
    else if (kind === 'q') showQuestion(st);
    else if (kind === 'sent') { showScreen('sent'); announce(t('answer_sent')); }
    else if (kind === 'late') showWait(t('time_up'), t('too_late'));
    else if (kind === 'res') showResult(st);
    else if (kind === 'final') showFinal(st);
  } else if (view.startsWith('res:')) {
    updateResultRank(st); // rank moves while the others answer
  }
  if ($('#dlg-lb').open) renderLeaderboard(st);
}

function renderBar(st) {
  const me = st.me || {};
  $('#bar').hidden = false;
  $('#me-name').textContent = me.nickname || S.nickname;
  const canRename = settingOf(st, 'allow_rename', true) && st.status !== 'ended';
  $('#btn-rename').setAttribute('aria-disabled', String(!canRename));
  $('#btn-rename').hidden = st.status === 'ended';
  const pill = me.rank ? `${t('rank_n', { n: me.rank })} · ${fmtInt(me.score)} ${t('pts')}` : t('leaderboard');
  const btn = $('#btn-rank');
  iconLabel(btn, 'trophy', pill);
  const av = $('#me-avatar'); const seed = me.id ?? (lsGet(LS_PLAYER) || {}).id ?? (me.nickname || S.nickname);
  if (av && av.dataset.seed !== String(seed)) { av.dataset.seed = String(seed); av.replaceChildren(mascot(mascotFor(seed), { size: 'xs' })); }
  btn.setAttribute('aria-label', me.rank ? t('lb_open', { rank: me.rank, score: fmtInt(me.score) }) : t('lb_title'));
}

function showWait(title, sub) {
  $('#wait-title').textContent = title;
  $('#wait-sub').textContent = sub;
  showScreen('wait');
}

// ---------- question
function showQuestion(st) {
  const q = st.question;
  S.warned = false; S.sending = false;
  $('#q-count').textContent = t('q_of', { n: q.idx + 1, m: st.total });
  $('#q-prompt').textContent = q.prompt || '';
  $('#q-err').textContent = '';
  const box = $('#q-answers');
  if (isMC(q) && Array.isArray(q.options)) {
    $('#q-help').textContent = t('choose');
    const tiles = h('div', { class: `lv-tiles${q.options.length === 2 ? ' is-two' : ''}`, role: 'group', 'aria-labelledby': 'q-prompt' },
      q.options.map((text, i) => h('button', {
        type: 'button', class: 'lv-tile', 'data-i': String(i), lang: 'en',
        'aria-label': t('option_label', { shape: shapeName(i), text }),
        onclick: () => answer(i),
      }, shapeIcon(i), h('span', {}, text))));
    box.replaceChildren(tiles);
  } else {
    // Only multiple_choice is served (quiz-only MVP); a legacy question of another type cannot be answered here.
    $('#q-help').textContent = '';
    box.replaceChildren(h('p', { class: 'lv-card', style: 'font-weight:800' }, t('q_unsupported')));
  }
  showScreen('question');
  startTimer();
}

async function answer(choice) {
  if (isSP(S.state)) { spAnswer(choice); return; }
  if (S.sending) return;
  const st = S.state; const q = st && st.question;
  if (!q) return;
  S.sending = true;
  $('#q-answers').querySelectorAll('button.lv-tile').forEach((b, i) => {
    b.setAttribute('aria-disabled', 'true');
    if (i !== choice) b.classList.add('is-dim');
  });
  sfx.unlock(); sfx.click();
  try {
    await api(`/api/live/games/${S.pin}/answer`, {
      method: 'POST', json: { choice, idx: q.idx }, headers: { 'X-Player-Token': S.token },
    });
    S.myChoice = { idx: q.idx, choice };
    if (S.view === `q:${q.idx}`) { S.view = `sent:${q.idx}`; stopTimer(); showScreen('sent'); announce(t('answer_sent')); }
    S.conn && S.conn.refresh();
  } catch (err) {
    S.sending = false;
    if (err.status === 409) { S.conn && S.conn.refresh(); if (/answered/i.test(err.message)) return; showWait(t('time_up'), t('too_late')); S.view = `late:${q.idx}`; return; }
    if (err.status === 403) { gone(t('kicked_title'), t('kicked_sub')); return; }
    $('#q-answers').querySelectorAll('button.lv-tile').forEach((b) => { b.removeAttribute('aria-disabled'); b.classList.remove('is-dim'); });
    $('#q-err').textContent = err.message || t('error_generic');
  }
}

function startTimer() {
  const el = $('#q-timer');
  const loop = () => {
    const left = clock.leftMs(S.state);
    if (left === null) { el.textContent = ''; return; }
    const sec = Math.max(0, Math.ceil(left / 1000));
    el.textContent = left > 0 ? String(sec) : t('time_up');
    el.classList.toggle('is-low', left <= 5000);
    if (!S.warned && left <= 5000 && left > 0) { S.warned = true; announce(t('sec_left', { n: 5 })); }
    if (left < -GRACE_MS && S.view.startsWith('q:') && !S.sending) {
      if (!isSP(S.state)) { render(S.state); return; }
      // homework: the server records the timed-out question on the next /state read — ask for it (retry every 2 s)
      if (!S.expiring || Date.now() - S.expiring > 2000) { S.expiring = Date.now(); if (S.conn) S.conn.refresh(); }
    }
    S.timerRaf = setTimeout(loop, 250);
  };
  loop();
}
function stopTimer() { clearTimeout(S.timerRaf); S.timerRaf = 0; }

// ---------- result
function showResult(st) {
  const r = st.me && st.me.last_result;
  const q = st.question;
  const card = $('#res-card');
  const detail = $('#res-detail');
  detail.replaceChildren();
  $('#res-go').hidden = true;
  if (!r) {
    card.className = 'lv-result is-none';
    $('#res-icon').replaceChildren(mascot('blue', { size: 'md' }));
    $('#res-title').textContent = t('no_answer');
    $('#res-pts').textContent = '';
    $('#res-streak').textContent = t('no_answer_sub');
  } else {
    const ok = !!r.passed;
    card.className = `lv-result ${ok ? 'is-ok' : 'is-bad'}`;
    $('#res-icon').replaceChildren(mascot(ok ? 'pink' : 'purple', { size: 'md' }));
    $('#res-title').textContent = ok ? t('correct') : t('incorrect');
    $('#res-pts').textContent = t('result_points', { n: fmtInt(r.points) });
    $('#res-streak').textContent = r.streak > 1 && ok ? t('streak_n', { n: r.streak }) : '';
    if (ok) sfx.correct(); else sfx.wrong();
  }
  // show the correct option (and mine) for MC
  if (isMC(q) && Array.isArray(q.options)) {
    const fb = (r && r.feedback) || {};
    const rc = (r && r.correct) || (st.reveal && st.reveal.correct) || {};
    const correct = Number.isInteger(rc.option) ? rc.option : Number.isInteger(fb.correct) ? fb.correct : null;
    const mine = r && Number.isInteger(r.choice) ? r.choice : null;
    if (correct !== null || mine !== null) {
      const rows = [];
      if (mine !== null) rows.push(optionLine(t('your_answer'), q.options, mine));
      if (correct !== null && correct !== mine) rows.push(optionLine(t('correct_answer'), q.options, correct));
      detail.replaceChildren(...rows);
    }
  }
  detail.hidden = !detail.childNodes.length;
  updateResultRank(st);
  showScreen('result');
  announce([$('#res-title').textContent, $('#res-pts').textContent, $('#res-rank').textContent].filter(Boolean).join('. '));
}

function optionLine(label, options, i) {
  return h('div', { class: 'lv-field', style: 'margin-bottom:8px' },
    h('span', { class: 'lv-label' }, label),
    h('div', { class: 'lv-tile', 'data-i': String(i), style: 'cursor:default;min-height:60px', lang: 'en' },
      shapeIcon(i), h('span', {}, h('span', { class: 'sr-only' }, `${shapeName(i)}: `), options[i])));
}

function updateResultRank(st) {
  const me = st.me || {};
  $('#res-rank').textContent = me.rank ? t('result_now', { rank: me.rank, score: fmtInt(me.score) }) : '';
  $('#res-next').textContent = st.status === 'question' || st.status === 'leaderboard' || st.status === 'reveal' ? t('wait_next') : '';
}

// ---------- final
function showFinal(st) {
  const me = st.me || {};
  $('#final-title').textContent = t('final_title');
  $('#final-sub').hidden = true;
  $('#final-emoji').replaceChildren(icon(me.rank && me.rank <= 3 ? 'trophy' : 'flag'));
  $('#final-rank').textContent = me.rank ? t('final_rank', { rank: me.rank }) : '';
  $('#final-score').textContent = t('final_score', { score: fmtInt(me.score) });
  lsDel(LS_PLAYER);
  showScreen('final');
  sfx.fanfare();
}

// ------------------------------------------------------------------ leaderboard dialog
$('#btn-rank').addEventListener('click', () => {
  renderLeaderboard(S.state || {});
  $('#dlg-lb').showModal();
  $('#lb-close').focus();
});
$('#lb-close').addEventListener('click', () => $('#dlg-lb').close());

function renderLeaderboard(st) {
  const me = st.me || {};
  const lb = st.leaderboard;
  const rows = (Array.isArray(lb) ? lb : (lb && Array.isArray(lb.top) ? lb.top : [])).slice(0, 10);
  const lbMe = (lb && !Array.isArray(lb) && lb.me) || null;
  const list = $('#lb-list');
  const isMe = (r) => (r.player_id !== undefined && r.player_id === me.id) || r.nickname === me.nickname;
  const items = rows.map((r) => lbItem(r, isMe(r)));
  if (me.rank && !rows.some(isMe)) items.push(lbItem({ rank: me.rank, nickname: me.nickname, score: me.score }, true));
  list.replaceChildren(...(items.length ? items : [h('li', {}, t('lb_none'))]));
  // gap to the player above
  let gap = '';
  if (me.rank === 1) gap = t('lb_top');
  else if (me.rank) {
    const above = lbMe && lbMe.above ? { score: me.score + Number(lbMe.above.score_gap || 0), rank: rows.filter((r) => r.rank < me.rank).reduce((m, r) => Math.max(m, r.rank), 0) || me.rank - 1, nickname: lbMe.above.nickname }
      : rows.filter((r) => r.rank < me.rank).sort((a, b) => b.rank - a.rank)[0];
    if (above) gap = t('lb_gap', { n: fmtInt(Math.max(0, above.score - me.score)), name: above.nickname || `#${above.rank}` });
  }
  $('#lb-gap').textContent = gap;
}
function lbItem(r, mine) {
  const d = Number(r.delta_rank || 0);
  return h('li', { class: mine ? 'is-me' : '' },
    h('span', { class: 'lv-lb-rank' }, `#${r.rank}`), mascot(mascotFor(r.player_id ?? r.id ?? r.nickname), { size: 'xs' }),
    h('span', { class: 'lv-lb-name' }, r.nickname, mine ? h('span', { class: 'sr-only' }, ` (${t('you')})`) : null),
    d ? h('span', { class: `lv-delta ${d > 0 ? 'up' : 'down'}` }, d > 0 ? `▲ ${t('rank_up', { n: d })}` : `▼ ${t('rank_down', { n: -d })}`) : null,
    h('span', {}, fmtInt(r.score)));
}

// ------------------------------------------------------------------ rename (any time)
$('#btn-rename').addEventListener('click', () => {
  if ($('#btn-rename').getAttribute('aria-disabled') === 'true') { toast(t('rename_locked')); return; }
  $('#rn-input').value = S.nickname;
  $('#rn-err').textContent = '';
  $('#rn-input').removeAttribute('aria-invalid');
  $('#dlg-rename').showModal();
  $('#rn-input').select();
});
$('#rn-cancel').addEventListener('click', () => $('#dlg-rename').close());
$('#rn-input').addEventListener('input', () => { $('#rn-err').textContent = ''; $('#rn-input').removeAttribute('aria-invalid'); });
$('#rename-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const nickname = $('#rn-input').value.replace(/\s+/g, ' ').trim();
  const fail = (msg) => { $('#rn-err').textContent = msg; $('#rn-input').setAttribute('aria-invalid', 'true'); $('#rn-input').focus(); };
  if (!nickname) { fail(t('nick_empty')); return; }
  if (nickname === S.nickname) { $('#dlg-rename').close(); return; }
  try {
    const r = await api(`/api/live/games/${S.pin}/me`, { method: 'PATCH', json: { nickname }, headers: { 'X-Player-Token': S.token } });
    S.nickname = (r && (r.nickname || (r.me && r.me.nickname))) || nickname;
    const sv = lsGet(LS_PLAYER); if (sv) lsSet(LS_PLAYER, { ...sv, nickname: S.nickname });
    $('#me-name').textContent = S.nickname;
    $('#dlg-rename').close();
    $('#btn-rename').focus();
    toast(t('renamed', { name: S.nickname }));
    S.conn && S.conn.refresh();
  } catch (err) {
    if (err.status === 409) fail(t('nick_taken'));
    else if (err.status === 429) fail(t('too_many'));
    else if (err.status === 403) fail(/remov|kick/i.test(err.message) ? t('kicked_sub') : t('rename_locked'));
    else fail(err.message || t('error_generic'));
  }
});

// ================================================================== HOMEWORK (self-paced) — CONTRACT "SELF-PACED / HOMEWORK MODE"
// intro → [POST /me/start] question (server clock) → answer → instant result → Next → … → done.
// The tab may close between questions: state (current_idx) resumes it. A question started and left running
// times out on the server; we show "Time ran out on that one — moving on" (the position is remembered in LS).
function isSP(st) { return !!st && st.mode === 'self_paced'; }
const SP = { res: null, ack: -1, starting: false };   // res = {pos, result, q}: my answer just sent (state has no question then)
const spStarted = () => { const v = (lsGet(LS_PLAYER) || {}).started; return Number.isInteger(v) ? v : null; };
function spRemember(patch) { const sv = lsGet(LS_PLAYER); if (sv) lsSet(LS_PLAYER, { ...sv, ...patch }); }

function spView(st) {
  const me = st.me || {};
  const cur = me.current_idx ?? 0;
  const q = st.question;
  if (st.status === 'ended') return 'spend';
  if (SP.res && SP.res.pos === cur - 1 && SP.ack !== SP.res.pos) return `res:${SP.res.pos}`;
  const started = spStarted();
  if (!q && started !== null && started === cur - 1 && !me.last_result && SP.ack !== started) return `timeout:${started}`;
  if (me.finished_at) return 'spdone';
  if (st.paused) return 'paused';
  if (q) return `q:${q.idx}`;
  return `intro:${cur}`;
}

function renderSP(st) {
  if (S.sending) { renderProg(st, S.view); return; } // my answer is in flight: its response decides the next view
  const view = spView(st);
  renderProg(st, view);
  if (view !== S.view) {
    S.view = view;
    stopTimer();
    const [kind] = view.split(':');
    if (kind === 'intro') showIntro(st);
    else if (kind === 'q') showQuestion(st);
    else if (kind === 'res') showSpResult(st);
    else if (kind === 'timeout') showSpTimeout(st);
    else if (kind === 'paused') { showScreen('paused'); announce(t('hw_paused_title')); }
    else showSpFinal(st, kind);
  } else if (view === 'spdone' || view === 'spend') updateSpFinal(st);
  else if (view.startsWith('res:') || view.startsWith('timeout:')) updateResultRank(st);
  if ($('#dlg-lb').open) renderLeaderboard(st);
}

function renderProg(st, view) {
  const me = st.me || {};
  const m = st.total || me.total || 0;
  const cur = Math.min(me.current_idx ?? 0, m);
  const [kind, n] = String(view || '').split(':');
  let label;
  if (me.finished_at && kind !== 'res' && kind !== 'timeout') label = t('hw_prog_done', { m });
  else if (kind === 'res' || kind === 'timeout') label = t('hw_prog', { n: Number(n) + 1, m });
  else label = t('hw_prog', { n: Math.min(cur + 1, Math.max(m, 1)), m });
  const done = me.finished_at ? m : cur;
  $('#sp-prog').hidden = false;
  $('#sp-prog-label').textContent = label;
  const bar = $('#sp-prog-bar');
  bar.setAttribute('aria-valuemax', String(m));
  bar.setAttribute('aria-valuenow', String(done));
  bar.setAttribute('aria-valuetext', `${done} / ${m}`);
  bar.firstElementChild.style.width = `${m ? (100 * done) / m : 0}%`;
}

function showIntro(st) {
  const me = st.me || {};
  const cur = me.current_idx ?? 0;
  $('#in-title').textContent = st.title || '';
  $('#in-count').textContent = t('hw_intro_q', { n: st.total });
  $('#in-due').textContent = st.closes_at ? t('hw_due', { when: fmtWhen(st.closes_at) }) : t('hw_no_due');
  $('#in-back').hidden = cur === 0;
  $('#in-back').textContent = cur > 0 ? t('hw_welcome_back', { n: cur + 1, m: st.total }) : '';
  iconLabel($('#in-start'), 'play', cur > 0 ? t('hw_continue') : t('hw_start'));
  $('#in-start').removeAttribute('aria-disabled');
  $('#in-err').textContent = '';
  showScreen('intro');
}
$('#in-start').addEventListener('click', () => spStart($('#in-start')));
$('#res-go').addEventListener('click', () => {
  const st = S.state || {};
  const v = S.view;
  if (v.startsWith('res:')) SP.ack = Number(v.split(':')[1]);
  if (v.startsWith('timeout:')) { SP.ack = Number(v.split(':')[1]); spRemember({ started: null }); }
  const me = st.me || {};
  if (me.finished_at || st.status === 'ended' || st.paused) { S.view = ''; render(st); return; }
  spStart($('#res-go'));
});

async function spStart(btn) {
  if (SP.starting) return;
  if (btn && btn.getAttribute('aria-disabled') === 'true') return;
  SP.starting = true;
  if (btn) btn.setAttribute('aria-disabled', 'true');
  sfx.unlock();
  const expect = ((S.state || {}).me || {}).current_idx;
  try {
    const st = await api(`/api/live/games/${S.pin}/me/start`, { method: 'POST', headers: { 'X-Player-Token': S.token } });
    clock.sync(st.server_now);
    if (st.question) {
      spRemember({ started: st.question.idx });
      if (Number.isInteger(expect) && st.question.idx > expect) toast(t('hw_timeout'));
    }
    render(st);
  } catch (err) {
    if (err.status === 403) { gone(t('kicked_title'), t('kicked_sub')); return; }
    if (err.status === 409) { S.view = ''; if (S.conn) S.conn.refresh(); return; } // paused / ended / finished: the state shows it
    const box = S.screen === 'intro' ? $('#in-err') : null;
    if (box) box.textContent = err.message || t('error_generic'); else toast(err.message || t('error_generic'), { error: true });
  } finally {
    SP.starting = false;
    if (btn) btn.removeAttribute('aria-disabled');
  }
}

async function spAnswer(choice) {
  if (S.sending) return;
  const st = S.state; const q = st && st.question;
  if (!q) return;
  S.sending = true;
  const tiles = $('#q-answers').querySelectorAll('button.lv-tile');
  tiles.forEach((b, i) => { b.setAttribute('aria-disabled', 'true'); if (i !== choice) b.classList.add('is-dim'); });
  sfx.unlock(); sfx.click();
  try {
    const r = await api(`/api/live/games/${S.pin}/answer`, {
      method: 'POST', json: { choice, idx: q.idx }, headers: { 'X-Player-Token': S.token },
    });
    SP.res = { pos: q.idx, result: r.result, q };
    spRemember({ started: null });
    const me = { ...(st.me || {}), current_idx: r.current_idx ?? q.idx + 1, finished_at: r.finished ? (st.me.finished_at || new Date().toISOString()) : null };
    S.sending = false;
    stopTimer();
    render({ ...st, question: null, me });
    if (S.conn) S.conn.refresh();
  } catch (err) {
    S.sending = false;
    tiles.forEach((b) => { b.removeAttribute('aria-disabled'); b.classList.remove('is-dim'); });
    if (err.status === 403) { gone(t('kicked_title'), t('kicked_sub')); return; }
    if (err.status === 409) { S.view = ''; if (S.conn) S.conn.refresh(); return; } // time up / paused / ended
    $('#q-err').textContent = err.message || t('error_generic');
  }
}

function showSpResult(st) {
  const res = SP.res;
  showResult({ ...st, question: res.q, me: { ...(st.me || {}), last_result: res.result } });
  spNextButton(st);
}
function showSpTimeout(st) {
  $('#res-card').className = 'lv-result is-none';
  $('#res-icon').replaceChildren(mascot('blue', { size: 'md' }));
  $('#res-title').textContent = t('hw_timeout');
  $('#res-pts').textContent = '';
  $('#res-streak').textContent = t('hw_timeout_sub');
  $('#res-detail').replaceChildren(); $('#res-detail').hidden = true;
  updateResultRank(st);
  showScreen('result');
  spNextButton(st);
  announce(`${t('hw_timeout')}. ${t('hw_timeout_sub')}`);
}
function spNextButton(st) {
  const me = st.me || {};
  const last = !!me.finished_at || (me.current_idx ?? 0) >= (st.total || 0);
  $('#res-next').textContent = '';
  const b = $('#res-go');
  b.hidden = false;
  iconLabel(b, last ? 'flag' : 'arrow-right', last ? t('hw_see_result') : t('hw_next'));
}

function showSpFinal(st, kind) {
  const me = st.me || {};
  const done = !!me.finished_at;
  $('#final-emoji').replaceChildren(icon(done ? (me.rank && me.rank <= 3 ? 'trophy' : 'flag') : 'lock'));
  $('#final-title').textContent = done ? t('hw_done_title') : t('hw_closed_title');
  $('#final-sub').hidden = false;
  $('#final-sub').textContent = kind === 'spend' && !done ? t('hw_closed_sub') : t('hw_close_page');
  updateSpFinal(st);
  if (kind === 'spend') lsDel(LS_PLAYER); // closed for good; a finished-but-open game keeps the token (rank may still move)
  showScreen('final');
  if (done) sfx.fanfare();
}
function updateSpFinal(st) {
  const me = st.me || {};
  $('#final-rank').textContent = me.rank ? t('final_rank', { rank: me.rank }) : '';
  $('#final-score').textContent = t('final_score', { score: fmtInt(me.score) });
}
