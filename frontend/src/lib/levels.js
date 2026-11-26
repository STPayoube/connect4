export const LEVELS = [
  {
    id: 'easy',
    label: 'Easy',
    desc: 'Relaxed heuristic',
    pill: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300',
    active: 'border-emerald-400 bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-400/40',
  },
  {
    id: 'medium',
    label: 'Medium',
    desc: 'Classic WeakC4',
    pill: 'border-sky-500/40 bg-sky-500/15 text-sky-300',
    active: 'border-sky-400 bg-sky-500/20 text-sky-200 ring-1 ring-sky-400/40',
  },
  {
    id: 'hard',
    label: 'Hard',
    desc: 'Tactical lookahead',
    pill: 'border-amber-500/40 bg-amber-500/15 text-amber-300',
    active: 'border-amber-400 bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/40',
  },
  {
    id: 'impossible',
    label: 'Impossible',
    desc: 'Deep Alpha-Beta',
    pill: 'border-rose-500/40 bg-rose-500/15 text-rose-300',
    active: 'border-rose-400 bg-rose-500/20 text-rose-200 ring-1 ring-rose-400/40',
  },
];

export const LEVEL_MAP = Object.fromEntries(LEVELS.map((l) => [l.id, l]));

export function formatLevel(level) {
  return LEVEL_MAP[level]?.label || 'Medium';
}
