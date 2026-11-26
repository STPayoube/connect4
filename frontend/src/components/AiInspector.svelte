<script>
  import { formatLevel } from '../lib/levels.js';

  let { aiInfo = null, config = null } = $props();

  function formatScore(score) {
    if (score >= 999999) return 'WIN';
    if (score >= 999998) return 'BLOCK';
    if (score >= 100000) return '+WIN';
    if (score <= -100000) return '-LOSS';
    return Number.isInteger(score) ? String(score) : score.toFixed(1);
  }
</script>

<div class="rounded-2xl border border-slate-800/90 bg-slate-900/70 backdrop-blur">
  <div class="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
    <div class="flex items-center gap-2">
      <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-300">
        WeakC4 AI Inspector
      </h2>
      {#if config}
        <span class="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
          {config.rows}×{config.cols} · align {config.align}
        </span>
      {/if}
    </div>
    {#if aiInfo}
      <span class="font-mono text-[11px] text-slate-400">{aiInfo.elapsed_ms} ms</span>
    {/if}
  </div>

  {#if !aiInfo}
    <p class="px-4 py-5 text-center text-xs text-slate-500">
      Waiting for the first AI move to inspect heuristic scores or search tree data.
    </p>
  {:else}
    <div class="space-y-3 p-3.5 text-xs">
      <div class="grid grid-cols-3 gap-2">
        <div class="rounded-lg bg-slate-950/70 px-2.5 py-2">
          <div class="text-[10px] uppercase text-slate-500">Strategy</div>
          <div class="mt-0.5 font-semibold capitalize text-indigo-300">{aiInfo.strategy}</div>
        </div>
        <div class="rounded-lg bg-slate-950/70 px-2.5 py-2">
          <div class="text-[10px] uppercase text-slate-500">Level</div>
          <div class="mt-0.5 font-semibold text-slate-200">{formatLevel(aiInfo.level)}</div>
        </div>
        <div class="rounded-lg bg-slate-950/70 px-2.5 py-2">
          <div class="text-[10px] uppercase text-slate-500">Best Score</div>
          <div class="mt-0.5 truncate font-mono font-semibold text-emerald-300">
            {formatScore(aiInfo.chosen_score)}
          </div>
        </div>
      </div>

      {#if aiInfo.tree_info}
        <div class="space-y-2">
          <div class="flex items-center justify-between text-[11px] text-slate-400">
            <span>Search Evaluation</span>
            <span class="font-mono text-violet-300">
              {aiInfo.tree_info.nodes_evaluated.toLocaleString()} nodes
            </span>
          </div>
          <div class="grid grid-cols-2 gap-1.5">
            {#each aiInfo.tree_info.child_scores as ch}
              <div
                class="flex items-center justify-between rounded-lg bg-slate-950/60 px-2.5 py-1"
              >
                <span class="font-mono text-slate-300">Col {ch.col + 1}</span>
                <span class="font-mono font-semibold text-violet-300">
                  {formatScore(ch.score)}
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      {#if aiInfo.heuristic_candidates && aiInfo.heuristic_candidates.length > 0}
        <div>
          <div class="mb-1.5 text-[11px] font-medium text-slate-400">
            WeakC4 Heuristic Candidates
          </div>
          <div class="thin-scroll max-h-36 space-y-1 overflow-y-auto pr-1">
            {#each aiInfo.heuristic_candidates as cand}
              <div
                class="flex items-center justify-between gap-2 rounded-lg bg-slate-950/60 px-2.5 py-1.5"
              >
                <div class="flex min-w-0 items-center gap-2">
                  <span class="font-mono font-semibold text-slate-200">
                    C{cand.col + 1}·R{cand.row + 1}
                  </span>
                  <span class="truncate text-[11px] text-slate-400">
                    {cand.reasons.join(', ')}
                  </span>
                </div>
                <span class="shrink-0 font-mono text-[11px] font-semibold text-sky-300">
                  {formatScore(cand.score)}
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>
