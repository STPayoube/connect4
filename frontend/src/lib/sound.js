const SOUND_KEY = 'connect4_sound_enabled';

let audioCtx = null;

function getCtx() {
  if (typeof window === 'undefined') return null;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  if (!audioCtx) {
    audioCtx = new Ctx();
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

export function isSoundEnabled() {
  if (typeof localStorage === 'undefined') return true;
  const saved = localStorage.getItem(SOUND_KEY);
  return saved === null ? true : saved === 'true';
}

export function setSoundEnabled(enabled) {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(SOUND_KEY, String(Boolean(enabled)));
  }
}

export function playDropSound(row = 5) {
  if (!isSoundEnabled()) return;
  const ctx = getCtx();
  if (!ctx) return;

  try {
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    const baseFreq = 210 + (6 - Math.min(row, 6)) * 22;
    osc.frequency.setValueAtTime(baseFreq, now);
    osc.frequency.exponentialRampToValueAtTime(95, now + 0.085);

    gain.gain.setValueAtTime(0.14, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.095);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.1);
  } catch {
    // ignore audio errors
  }
}

export function playWinSound() {
  if (!isSoundEnabled()) return;
  const ctx = getCtx();
  if (!ctx) return;

  try {
    const notes = [523.25, 659.25, 783.99, 1046.5];
    const now = ctx.currentTime;
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      const t = now + idx * 0.085;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(0.11, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.28);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.3);
    });
  } catch {
    // ignore audio errors
  }
}
