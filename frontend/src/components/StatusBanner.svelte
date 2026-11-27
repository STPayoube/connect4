<script>
  import { onDestroy, onMount } from 'svelte';
  import { formatLevel, LEVEL_MAP } from '../lib/levels.js';

  let {
    game = null,
    isThinking = false,
    error = null,
    hideAiLevel = false,
    onDismissError = () => {},
  } = $props();

  let nowSec = $state(Date.now() / 1000);
  let timerId = null;

  onMount(() => {
    timerId = setInterval(() => {
      nowSec = Date.now() / 1000;
    }, 1000);
  });

  onDestroy(() => {
    if (timerId) clearInterval(timerId);
  });

  let p1 = $derived(game?.players?.['1'] || null);
  let p2 = $derived(game?.players?.['2'] || null);
  let activePlayer = $derived(game?.players?.[String(game.current_player)] || null);
  let winnerPlayer = $derived(game?.winner ? game?.players?.[String(game.winner)] : null);

  let elapsedFormatted = $derived.by(() => {
    if (!game?.created_at) return '';
    const endTs = game.status === 'playing' ? nowSec : game.updated_at || nowSec;
    const secs = Math.max(0, Math.floor(endTs - game.created_at));
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return `${String(mins).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
  });

  function forfeitLabel(reason) {
    if (reason === 'accidental_exit') return 'Forfait (Sortie involontaire)';
    if (reason === 'abandon_restart') return 'Forfait (Abandon)';
    return 'Partie terminée';
  }
</script>

<div class="space-y-3">
  {#if error}
    <div
      class="flex items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-4 py-2.5 text-sm text-rose-200 backdrop-blur"
      role="alert"
    >
      <span>{error}</span>
      <button
        type="button"
        onclick={onDismissError}
        class="rounded-md px-2 py-0.5 text-xs font-medium text-rose-300 hover:bg-rose-500/20"
      >
        Fermer
      </button>
    </div>
  {/if}

  {#if game}
    <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
      <!-- Carte Joueur 1 -->
      <div
        class="flex items-center gap-3 rounded-xl border px-3.5 py-2.5 transition-all {game.status ===
          'playing' && game.current_player === 1
          ? 'border-rose-400/60 bg-rose-950/35 shadow-[0_0_24px_-6px_rgba(244,63,94,0.45)]'
          : game.winner === 1
            ? 'border-emerald-400/70 bg-emerald-950/35'
            : 'border-slate-800 bg-slate-900/60 opacity-75'}"
      >
        <span
          class="h-6 w-6 shrink-0 rounded-full bg-gradient-to-br from-rose-400 via-rose-500 to-red-700 shadow-md ring-2 ring-rose-300/40"
        ></span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="truncate text-sm font-semibold text-slate-100">{p1?.name}</span>
            {#if p1?.type === 'ai'}
              {#if !hideAiLevel && p1.level}
                <span
                  class="rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide {LEVEL_MAP[
                    p1.level
                  ]?.pill || 'border-slate-700 bg-slate-800 text-slate-300'}"
                >
                  {formatLevel(p1.level)}
                </span>
              {:else}
                <span
                  class="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300"
                >
                  IA
                </span>
              {/if}
            {:else}
              <span
                class="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300"
              >
                Joueur 1
              </span>
            {/if}
          </div>
        </div>
        {#if game.status === 'playing' && game.current_player === 1}
          <span class="h-2.5 w-2.5 animate-pulse rounded-full bg-rose-400"></span>
        {/if}
      </div>

      <!-- Pastille centrale de statut -->
      <div class="flex flex-col items-center justify-center gap-1">
        {#if game.status === 'win'}
          <div
            class="inline-flex items-center gap-2 rounded-full border border-emerald-400/50 bg-emerald-500/15 px-4 py-1.5 text-sm font-semibold text-emerald-200 shadow-[0_0_24px_-4px_rgba(52,211,153,0.45)]"
          >
            <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
            {winnerPlayer?.name} a gagné !
          </div>
        {:else if game.status === 'draw'}
          <div
            class="inline-flex items-center gap-2 rounded-full border border-slate-500/50 bg-slate-800/80 px-4 py-1.5 text-sm font-semibold text-slate-200"
          >
            Match nul !
          </div>
        {:else if game.status === 'forfeit'}
          <div
            class="inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold {game.end_reason ===
            'manual_end'
              ? 'border-amber-400/50 bg-amber-500/15 text-amber-200'
              : 'border-rose-400/50 bg-rose-500/15 text-rose-200'}"
          >
            <span
              class="h-2 w-2 rounded-full {game.end_reason === 'manual_end'
                ? 'bg-amber-400'
                : 'bg-rose-400'}"
            ></span>
            {forfeitLabel(game.end_reason)}
          </div>
        {:else if isThinking}
          <div
            class="inline-flex items-center gap-2 rounded-full border border-indigo-400/40 bg-indigo-500/15 px-4 py-1.5 text-sm font-medium text-indigo-200"
          >
            <span
              class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-indigo-300 border-t-transparent"
            ></span>
            {activePlayer?.name} réfléchit…
          </div>
        {:else}
          <div
            class="inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/80 px-4 py-1.5 text-sm font-medium text-slate-200"
          >
            <span
              class="h-2.5 w-2.5 rounded-full {game.current_player === 1
                ? 'bg-rose-400'
                : 'bg-amber-400'}"
            ></span>
            Au tour de {activePlayer?.name}
          </div>
        {/if}

        {#if game.config?.random_start && game.move_history?.length === 0}
          <span class="text-[11px] font-medium text-indigo-300">
            Tirage au sort : {activePlayer?.name} commence
          </span>
        {:else if elapsedFormatted && game.move_history?.length > 0}
          <span class="font-mono text-[10px] text-slate-500">
            ⏱ {elapsedFormatted} · {game.move_history.length} {game.move_history.length > 1 ? 'coups' : 'coup'}
          </span>
        {/if}
      </div>

      <!-- Carte Joueur 2 -->
      <div
        class="flex items-center gap-3 rounded-xl border px-3.5 py-2.5 transition-all {game.status ===
          'playing' && game.current_player === 2
          ? 'border-amber-400/60 bg-amber-950/30 shadow-[0_0_24px_-6px_rgba(251,191,36,0.4)]'
          : game.winner === 2
            ? 'border-emerald-400/70 bg-emerald-950/35'
            : 'border-slate-800 bg-slate-900/60 opacity-75'}"
      >
        <span
          class="h-6 w-6 shrink-0 rounded-full bg-gradient-to-br from-amber-300 via-amber-400 to-amber-600 shadow-md ring-2 ring-amber-200/40"
        ></span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="truncate text-sm font-semibold text-slate-100">{p2?.name}</span>
            {#if p2?.type === 'ai'}
              {#if !hideAiLevel && p2.level}
                <span
                  class="rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide {LEVEL_MAP[
                    p2.level
                  ]?.pill || 'border-slate-700 bg-slate-800 text-slate-300'}"
                >
                  {formatLevel(p2.level)}
                </span>
              {:else}
                <span
                  class="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300"
                >
                  IA
                </span>
              {/if}
            {:else}
              <span
                class="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300"
              >
                Joueur 2
              </span>
            {/if}
          </div>
        </div>
        {#if game.status === 'playing' && game.current_player === 2}
          <span class="h-2.5 w-2.5 animate-pulse rounded-full bg-amber-400"></span>
        {/if}
      </div>
    </div>
  {/if}
</div>
