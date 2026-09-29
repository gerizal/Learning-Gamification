// a11y-prefs.js — learner accessibility preferences, shared by the live pages (/host, /play, /classroom).
// Vanilla ES module, no build.
//
//   import { reduceMotion, applyPrefs } from './a11y-prefs.js';
//   reduceMotion()   // OS prefers-reduced-motion OR a stored "reduce motion" choice on this device
//
// applyPrefs() sets <html data-motion="reduce"> so CSS can reuse the reduced-motion rules
// (live.css / classroom.css: `html[data-motion="reduce"] …`).

const KEY = 'speakingGame.prefs'; // key name kept so a choice stored on this device keeps working

/** The stored reduce-motion choice. A storage failure is logged and treated as "no stored choice" (the OS
 *  setting still applies), never as a silent default. */
function storedReduceMotion() {
  let raw;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch (err) {
    console.warn('[a11y-prefs] localStorage unreadable; using the OS motion setting only', err);
    return false;
  }
  if (!raw) return false;
  try {
    const obj = JSON.parse(raw);
    return !!(obj && typeof obj === 'object' && obj.reduceMotion);
  } catch (err) {
    console.warn(`[a11y-prefs] stored value is not JSON (${KEY}); ignoring it`, err);
    return false;
  }
}

const stored = storedReduceMotion();
const mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
export function osReducedMotion() { return !!(mq && mq.matches); }
export function reduceMotion() { return osReducedMotion() || stored; }

export function applyPrefs(root = document.documentElement) {
  if (!root) return;
  if (reduceMotion()) root.dataset.motion = 'reduce'; else delete root.dataset.motion;
}

if (mq && mq.addEventListener) mq.addEventListener('change', () => applyPrefs());
applyPrefs();
