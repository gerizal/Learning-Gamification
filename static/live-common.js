// live-common.js — shared helpers for the live pages (host.js, play.js, home.html).
// DOM helper, JSON API, realtime connection (SSE + 2 s polling fallback), server clock, SFX,
// confetti, option shapes and a polite announcer. Vanilla ES module, no build step.

import { reduceMotion } from './a11y-prefs.js';
import { t, locale } from './i18n.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** h('div', {class:'x', onclick: fn}, 'text', child) */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// ------------------------------------------------------------------ storage + small helpers
/** Log a degraded path once per context (never silently): storage blocked, Web Audio missing, … */
const warned = new Set();
export function warnOnce(context, err) {
  if (warned.has(context)) return;
  warned.add(context);
  console.warn(`[live] ${context}`, err);
}
/** Stored JSON value, or null when nothing is stored. A storage error or unreadable JSON is logged with the key
 *  (the caller then starts fresh, e.g. no remembered player / quiz list). */
export function lsGet(k) {
  let raw;
  try { raw = window.localStorage.getItem(k); } catch (err) { warnOnce(`localStorage read failed (${k})`, err); return null; }
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (err) { warnOnce(`stored value is not JSON (${k})`, err); return null; }
}
export function lsSet(k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (err) { warnOnce(`localStorage write failed (${k})`, err); } }
export function lsDel(k) { try { window.localStorage.removeItem(k); } catch (err) { warnOnce(`localStorage delete failed (${k})`, err); } }
/** A count from the API as a finite number. Missing / non-numeric -> 0, which here means "none yet" (a count
 *  shown to people), never "no limit": nothing uses it as a cap. */
export function n0(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }

// ------------------------------------------------------------------ API
export class ApiError extends Error {
  constructor(message, status, detail) { super(message); this.status = status; this.detail = detail; }
}

export async function api(path, { method = 'GET', json, headers = {}, signal } = {}) {
  const opts = { method, headers: { Accept: 'application/json', ...headers }, signal };
  if (json !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(json); }
  let res;
  try { res = await fetch(path, opts); } catch (e) {
    if (e && e.name === 'AbortError') throw e;
    throw new ApiError(t('offline'), 0);
  }
  let body = null;
  const text = await res.text();
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const detail = body && typeof body === 'object' ? body.detail : body;
    console.warn('API', method, path, res.status, detail);
    throw new ApiError(typeof detail === 'string' ? detail : t('error_generic'), res.status, detail);
  }
  return body;
}

// ------------------------------------------------------------------ server clock
// offset = server − client (ms). Timers use phase_started_at + offset, never the raw client clock.
export const clock = {
  offset: 0,
  /** fresh = an HTTP response read just now. SSE states can come from a shared snapshot taken earlier (stale
   *  server_now), so they may only move the offset forward: a sample is never ahead of the true server time. */
  sync(serverNow, { fresh = true } = {}) {
    const s = Date.parse(serverNow);
    if (Number.isNaN(s)) return;
    const o = s - Date.now();
    if (fresh || !this.synced || o > this.offset) this.offset = o;
    this.synced = true;
  },
  now() { return Date.now() + this.offset; },
  /** ms left in the current question (negative when over). */
  leftMs(state) {
    if (!state || !state.question || !state.phase_started_at) return null;
    const start = Date.parse(state.phase_started_at);
    return start + state.question.time_limit_sec * 1000 - this.now();
  },
};

// ------------------------------------------------------------------ dates (homework deadlines, monitor)
/** "Fri 3 Oct, 23:59" in the UI language ('' for a bad value). */
export function fmtWhen(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return '';
  try { return new Intl.DateTimeFormat(locale(), { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(d); } catch { return d.toLocaleString(); }
}
/** "just now" / "5 minutes ago" on the server clock. */
export function fmtAgo(iso) {
  const d = Date.parse(iso);
  if (Number.isNaN(d)) return '';
  const s = Math.round((clock.now() - d) / 1000);
  if (s < 45) return t('ago_now');
  try {
    const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
    if (s < 3600) return rtf.format(-Math.max(1, Math.round(s / 60)), 'minute');
    if (s < 86400) return rtf.format(-Math.round(s / 3600), 'hour');
    return rtf.format(-Math.round(s / 86400), 'day');
  } catch { return fmtWhen(iso); }
}

// ------------------------------------------------------------------ realtime
/**
 * Connect to a game's state stream. SSE first; while SSE is down, poll /state every 2 s.
 * onState(state) for every state; onStatus('live'|'reconnecting'); onKicked(); onFatal(err) for 403/404.
 * Returns {close(), refresh()}.
 */
export function connectLive({ pin, role, token, onState, onStatus = () => {}, onKicked = () => {}, onFatal = () => {} }) {
  const q = `${role === 'host' ? 'host_token' : 'player_token'}=${encodeURIComponent(token)}`;
  const statePath = `/api/live/games/${encodeURIComponent(pin)}/state?${q}`;
  let es = null; let pollTimer = 0; let closed = false; let lastStatus = ''; let sseFails = 0;
  let lastJson = '';

  const status = (s) => { if (s !== lastStatus) { lastStatus = s; onStatus(s); } };
  const deliver = (st, fresh = true) => {
    if (closed || !st) return;
    clock.sync(st.server_now, { fresh });
    const key = JSON.stringify({ ...st, server_now: 0, time_left_ms: 0 });
    if (key === lastJson) return;
    lastJson = key;
    onState(st);
    if (st.status === 'ended') close();
  };

  async function poll() {
    if (closed) return;
    try {
      const st = await api(statePath);
      deliver(st);
      if (!es || es.readyState !== 1) status(es ? 'reconnecting' : 'live');
    } catch (e) {
      if (e.status === 403 || e.status === 404) { fatal(e); return; }
      status('reconnecting');
    }
  }
  function startPolling() {
    if (pollTimer || closed) return;
    poll();
    pollTimer = setInterval(poll, 2000);
  }
  function stopPolling() { clearInterval(pollTimer); pollTimer = 0; }
  function fatal(e) {
    close();
    if (e.status === 403 && role === 'player') onKicked(e); else onFatal(e);
  }

  function openSse() {
    if (closed || typeof EventSource === 'undefined') { startPolling(); return; }
    es = new EventSource(`/api/live/games/${encodeURIComponent(pin)}/events?${q}`);
    es.addEventListener('open', () => { sseFails = 0; stopPolling(); status('live'); });
    es.addEventListener('state', (ev) => {
      try { deliver(JSON.parse(ev.data), false); } catch (err) { console.warn('bad state event', err); }
    });
    es.addEventListener('kicked', () => { close(); onKicked(); });
    es.addEventListener('error', () => {
      if (closed) return;
      sseFails++;
      status('reconnecting');
      startPolling(); // the poll also detects 403/404 (auth errors close the stream for good)
      if (es.readyState === 2) { // CLOSED: browser won't retry — try again later ourselves
        es = null;
        setTimeout(() => { if (!closed && !es) openSse(); }, Math.min(15000, 2000 * sseFails));
      }
    });
  }

  function close() {
    closed = true;
    stopPolling();
    if (es) { try { es.close(); } catch { /* ignore */ } es = null; }
  }

  // First paint from /state (fast + detects bad tokens), then stream.
  poll().then(() => { if (!closed) openSse(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !closed) poll(); });
  return { close, refresh: poll, get closed() { return closed; } };
}

/** Pill element that shows "Reconnecting…" (role=status). */
export function connectionPill(el) {
  return (s) => {
    el.hidden = s !== 'reconnecting';
    el.textContent = s === 'reconnecting' ? t('reconnecting') : '';
  };
}

// ------------------------------------------------------------------ announcer (polite live region)
export function announce(text) {
  const el = document.getElementById('lv-announcer');
  if (!el) return;
  el.textContent = '';
  setTimeout(() => { el.textContent = text; }, 60);
}

let toastTimer = 0;
export function toast(text, { error = false, ms = 3500 } = {}) {
  let el = document.getElementById('lv-toast');
  if (!el) return;
  el.textContent = text;
  el.className = `lv-toast${error ? ' is-error' : ''}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

// ------------------------------------------------------------------ icons (Lucide sprite) + GAIN mascots
const SVGNS = 'http://www.w3.org/2000/svg';
/** <svg class="ic" aria-hidden="true"><use href="/static/icons.svg#name"/></svg> — sprite built by scripts/build_icons.mjs */
export function icon(name, cls = '') {
  const s = document.createElementNS(SVGNS, 'svg');
  s.setAttribute('class', cls ? `ic ${cls}` : 'ic');
  s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
  const u = document.createElementNS(SVGNS, 'use');
  u.setAttribute('href', `/static/icons.svg#${name}`);
  s.append(u);
  return s;
}
/** Replace an element's content with [icon] + text (keeps a data-i18n span pattern simple). */
export function iconLabel(el, name, text) { el.replaceChildren(...(name ? [icon(name)] : []), h('span', {}, text)); return el; }
export const MASCOTS = ['blue', 'green', 'pink', 'purple', 'red'];
/** Deterministic mascot for a player id / nickname. */
export function mascotFor(seed) {
  let x = 0;
  for (const ch of String(seed ?? '')) x = (Math.imul(x, 31) + ch.codePointAt(0)) >>> 0;
  return MASCOTS[x % MASCOTS.length];
}
/** Mascot on a light rounded "plate" (the .webp art has a light background). Decorative unless alt is given. */
export function mascot(color, { size = 'sm', alt = '' } = {}) {
  const px = size === 'lg' || size === 'xl' ? 512 : 256;
  return h('span', { class: `se-plate se-plate-${size}` },
    h('img', { src: `/static/brand/mascots/${color}-${px}.webp`, alt, width: '256', height: '256', decoding: 'async' }));
}

// ------------------------------------------------------------------ option shapes (colour + shape + text)
const SHAPES = [
  '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><path d="M16 3 30 28H2z"/></svg>',
  '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><path d="M16 1 31 16 16 31 1 16z"/></svg>',
  '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><circle cx="16" cy="16" r="14"/></svg>',
  '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><rect x="3" y="3" width="26" height="26" rx="2"/></svg>',
];
export function shapeIcon(i) { return h('span', { class: 'lv-shape', html: SHAPES[i % 4] }); }
export function shapeName(i) { return t(`shape_${i % 4}`); }

// ------------------------------------------------------------------ SFX (WebAudio synth, no files)
export const sfx = (() => {
  let ctx = null;
  let muted = lsGet('live.muted') === true;
  let music = null;
  function ac() {
    try {
      if (!ctx) { const C = window.AudioContext || window.webkitAudioContext; if (!C) return null; ctx = new C(); }
      if (ctx.state === 'suspended') ctx.resume();
      return ctx;
    } catch (err) { warnOnce('Web Audio unavailable (sound effects off)', err); return null; }
  }
  function tone(freq, { at = 0, dur = 0.12, type = 'sine', vol = 0.16, to = null } = {}) {
    if (muted) return;
    const c = ac(); if (!c) return;
    const t0 = c.currentTime + at;
    const o = c.createOscillator(); const g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(c.destination);
    o.start(t0); o.stop(t0 + dur + 0.02);
  }
  function startMusic() {
    const c = ac(); if (!c || music) return;
    // tiny 8-step arpeggio loop, scheduled every bar
    const notes = [392, 494, 587, 494, 440, 523, 659, 523];
    const step = 0.22; let next = c.currentTime + 0.05; let i = 0;
    const tick = () => {
      while (next < c.currentTime + 0.6) {
        if (!muted) {
          const o = c.createOscillator(); const g = c.createGain();
          o.type = 'triangle'; o.frequency.value = notes[i % notes.length];
          g.gain.setValueAtTime(0.0001, next);
          g.gain.exponentialRampToValueAtTime(0.05, next + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, next + step * 0.9);
          o.connect(g).connect(c.destination); o.start(next); o.stop(next + step);
        }
        next += step; i++;
      }
    };
    tick();
    music = setInterval(tick, 200);
  }
  function stopMusic() { clearInterval(music); music = null; }
  return {
    get muted() { return muted; },
    setMuted(v) { muted = !!v; lsSet('live.muted', muted); },
    unlock() { ac(); },
    get musicOn() { return !!music; },
    startMusic, stopMusic,
    click() { tone(880, { dur: 0.05, type: 'square', vol: 0.05 }); },
    join() { tone(660, { dur: 0.08, type: 'triangle' }); tone(990, { at: 0.08, dur: 0.12, type: 'triangle' }); },
    start() { [523, 659, 784, 1047].forEach((f, i) => tone(f, { at: i * 0.09, dur: 0.14, type: 'triangle' })); },
    tick() { tone(1200, { dur: 0.04, type: 'square', vol: 0.04 }); },
    timeUp() { tone(440, { dur: 0.25, type: 'sawtooth', to: 220, vol: 0.08 }); },
    correct() { tone(988, { dur: 0.08, type: 'square', vol: 0.07 }); tone(1319, { at: 0.08, dur: 0.22, type: 'square', vol: 0.07 }); },
    wrong() { tone(330, { dur: 0.18, type: 'sawtooth', to: 220, vol: 0.06 }); },
    reveal() { [659, 880].forEach((f, i) => tone(f, { at: i * 0.1, dur: 0.16, type: 'triangle' })); },
    fanfare() { [784, 988, 1175, 1568].forEach((f, i) => tone(f, { at: i * 0.14, dur: i === 3 ? 0.5 : 0.18, type: 'square', vol: 0.06 })); },
  };
})();

// ------------------------------------------------------------------ confetti (canvas; off under reduced motion)
export function confetti(canvas, n = 160) {
  if (reduceMotion() || !canvas) return;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr;
  const c2 = canvas.getContext('2d'); c2.setTransform(dpr, 0, 0, dpr, 0, 0);
  // brand confetti colours come from theme-se.css (--se-confetti)
  const colors = (getComputedStyle(document.documentElement).getPropertyValue('--se-confetti') || '').split(',').map((x) => x.trim()).filter(Boolean);
  if (!colors.length) colors.push('currentColor');
  let parts = [];
  for (let i = 0; i < n; i++) {
    const fromLeft = i % 2 === 0;
    parts.push({
      x: fromLeft ? -10 : innerWidth + 10, y: innerHeight * (0.4 + Math.random() * 0.3),
      vx: (fromLeft ? 1 : -1) * (4 + Math.random() * 8), vy: -(9 + Math.random() * 10),
      w: 7 + Math.random() * 7, h: 9 + Math.random() * 9, r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
      c: colors[i % colors.length], life: 0,
    });
  }
  const step = () => {
    c2.clearRect(0, 0, innerWidth, innerHeight);
    parts = parts.filter((p) => p.life < 240 && p.y < innerHeight + 40);
    for (const p of parts) {
      p.life++; p.vy += 0.3; p.vx *= 0.985; p.x += p.vx; p.y += p.vy; p.r += p.vr;
      c2.save(); c2.translate(p.x, p.y); c2.rotate(p.r); c2.fillStyle = p.c;
      c2.globalAlpha = Math.max(0, 1 - p.life / 240);
      c2.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.r * 2)) + 2);
      c2.restore();
    }
    if (parts.length) requestAnimationFrame(step); else c2.clearRect(0, 0, innerWidth, innerHeight);
  };
  requestAnimationFrame(step);
}

/** Show exactly one [data-screen] section; move focus to its heading (screen reader + keyboard users). */
export function showScreen(name, { focus = true } = {}) {
  let target = null;
  $$('main [data-screen]').forEach((s) => {
    const on = s.dataset.screen === name;
    s.hidden = !on;
    if (on) target = s;
  });
  if (document.body.dataset.screen !== name) window.scrollTo(0, 0);
  document.body.dataset.screen = name;
  if (focus && target) {
    const hd = target.querySelector('h1, h2');
    if (hd) { hd.setAttribute('tabindex', '-1'); hd.focus({ preventScroll: true }); }
  }
  return target;
}

export const isMC = (q) => !!q && q.game_mode === 'multiple_choice';
