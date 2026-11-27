<script>
  let { moves = [] } = $props();

  let reversedMoves = $derived([...moves].reverse());

  function strategyLabel(strategy) {
    if (strategy === 'minimax') return 'Alpha-Bêta';
    if (strategy === 'tree') return 'Arbre';
    if (strategy === 'heuristic') return 'Heuristique';
    return 'Secours';
  }
</script>

<div class="flex flex-col rounded-2xl border border-slate-800/90 bg-slate-900/70 backdrop-blur">
  <div class="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
    <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Historique des coups</h2>
    <span class="font-mono text-xs text-slate-500">
      {moves.length} {moves.length <= 1 ? 'coup' : 'coups'}
    </span>
  </div>

  {#if moves.length === 0}
    <p class="px-4 py-6 text-center text-xs text-slate-500">
      Aucun coup joué. Cliquez sur une colonne pour commencer.
    </p>
  {:else}
    <ol class="thin-scroll max-h-56 divide-y divide-slate-800/60 overflow-y-auto px-2 py-1">
      {#each reversedMoves as m (m.ply)}
        <li class="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-slate-800/40">
          <div class="flex min-w-0 items-center gap-2.5">
            <span class="w-6 shrink-0 font-mono text-[11px] text-slate-500">#{m.ply}</span>
            <span
              class="h-2.5 w-2.5 shrink-0 rounded-full {m.player === 1 ? 'bg-rose-500' : 'bg-amber-400'}"
            ></span>
            <span class="truncate font-medium text-slate-200">{m.player_name}</span>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            {#if m.ai_info}
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-medium {m.ai_info.strategy === 'minimax' ||
                m.ai_info.strategy === 'tree'
                  ? 'bg-violet-500/20 text-violet-300'
                  : 'bg-sky-500/15 text-sky-300'}"
              >
                {strategyLabel(m.ai_info.strategy)}
              </span>
            {/if}
            <span class="font-mono text-[11px] text-slate-400">
              C{m.col + 1} · L{m.row + 1}
            </span>
          </div>
        </li>
      {/each}
    </ol>
  {/if}
</div>
