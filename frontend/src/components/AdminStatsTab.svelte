<script>
  import { onMount } from 'svelte';
  import {
    adminDeleteHistoryRecord,
    adminGetHistoryRecord,
    adminGetStats,
    adminListHistory,
  } from '../lib/api.js';
  import { formatLevel, LEVEL_MAP } from '../lib/levels.js';
  import Board from './Board.svelte';

  let { token = '', refreshTrigger = 0 } = $props();

  let stats = $state(null);
  let history = $state({ total: 0, records: [] });
  let loading = $state(true);
  let error = $state(null);

  let channelFilter = $state('all');
  let outcomeFilter = $state('all');
  let searchQuery = $state('');

  let replayRecord = $state(null);
  let replayPly = $state(0);

  let replayGrid = $derived.by(() => {
    if (!replayRecord) return [];
    const g = Array.from({ length: replayRecord.rows }, () => Array(replayRecord.cols).fill(0));
    const slice = (replayRecord.move_history || []).slice(0, replayPly);
    for (const m of slice) {
      if (m.row >= 0 && m.row < replayRecord.rows && m.col >= 0 && m.col < replayRecord.cols) {
        g[m.row][m.col] = m.player;
      }
    }
    return g;
  });

  let replayLastMove = $derived(
    replayRecord && replayPly > 0 ? replayRecord.move_history[replayPly - 1] : null
  );

  let replayWinCells = $derived(
    replayRecord && replayPly === (replayRecord.move_history?.length || 0)
      ? replayRecord.winning_cells || []
      : []
  );

  async function loadAll() {
    if (!token) return;
    loading = true;
    error = null;
    try {
      const [s, h] = await Promise.all([
        adminGetStats(token),
        adminListHistory(token, {
          channel: channelFilter,
          outcome: outcomeFilter,
          search: searchQuery.trim(),
          limit: 60,
        }),
      ]);
      stats = s;
      history = h;
    } catch (err) {
      error = err.message || 'Impossible de charger les statistiques.';
    } finally {
      loading = false;
    }
  }

  async function loadHistoryOnly() {
    if (!token) return;
    try {
      history = await adminListHistory(token, {
        channel: channelFilter,
        outcome: outcomeFilter,
        search: searchQuery.trim(),
        limit: 60,
      });
    } catch (err) {
      error = err.message || "Impossible de charger l'historique.";
    }
  }

  async function openReplay(recordId) {
    try {
      const rec = await adminGetHistoryRecord(token, recordId);
      replayRecord = rec;
      replayPly = rec.move_history?.length || 0;
    } catch (err) {
      error = err.message || 'Impossible de charger le replay.';
    }
  }

  async function removeRecord(recordId) {
    try {
      await adminDeleteHistoryRecord(token, recordId);
      await loadAll();
    } catch (err) {
      error = err.message || 'Impossible de supprimer cette archive.';
    }
  }

  function formatDate(ts) {
    return new Date(ts * 1000).toLocaleString('fr-FR');
  }

  function channelBadge(ch) {
    if (ch === 'winaprize') return 'border-amber-400/50 bg-amber-500/15 text-amber-200';
    if (ch === 'online_pvp') return 'border-emerald-400/50 bg-emerald-500/15 text-emerald-200';
    return 'border-slate-700 bg-slate-800 text-slate-300';
  }

  function channelLabel(ch) {
    if (ch === 'winaprize') return 'Défi Prix';
    if (ch === 'online_pvp') return 'Ami en ligne';
    return 'Normal';
  }

  function formatOutcomeLabel(rec) {
    if (rec.status === 'draw') return 'Match nul';
    if (rec.status === 'forfeit') {
      if (rec.human_outcome === 'forfeit_exit' || rec.end_reason === 'accidental_exit') {
        return 'Forfait (Sortie involontaire)';
      }
      if (rec.human_outcome === 'forfeit_abandon' || rec.end_reason === 'abandon_restart') {
        return 'Forfait (Abandon / Relance)';
      }
      return 'Fin manuelle';
    }
    return `${rec.winner_name} a gagné`;
  }

  function outcomeColorClass(rec) {
    if (rec.status === 'draw') return 'text-slate-400';
    if (rec.status === 'forfeit') {
      if (rec.human_outcome === 'forfeit_exit' || rec.end_reason === 'accidental_exit') {
        return 'text-orange-300 font-semibold';
      }
      if (rec.human_outcome === 'forfeit_abandon' || rec.end_reason === 'abandon_restart') {
        return 'text-rose-300 font-semibold';
      }
      return 'text-amber-300 font-semibold';
    }
    if (rec.human_outcome === 'win') return 'text-emerald-300 font-semibold';
    if (rec.human_outcome === 'loss') return 'text-rose-300 font-semibold';
    return 'text-indigo-300 font-semibold';
  }

  $effect(() => {
    refreshTrigger;
    if (token) loadAll();
  });

  onMount(() => {
    loadAll();
  });
</script>

<div class="space-y-6">
  {#if error}
    <div class="rounded-xl border border-rose-500/40 bg-rose-950/60 px-4 py-2.5 text-xs text-rose-200">
      {error}
    </div>
  {/if}

  {#if loading && !stats}
    <div class="py-12 text-center text-sm text-slate-400">Chargement des statistiques…</div>
  {:else if stats}
    <!-- Résumé global -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
        <div class="text-xs text-slate-400">Parties archivées</div>
        <div class="mt-1 font-mono text-2xl font-bold text-white">{stats.overall.total_games}</div>
      </div>
      <div class="rounded-2xl border border-amber-500/35 bg-amber-950/20 p-4">
        <div class="text-xs text-amber-300">Gagnants (/winaprize)</div>
        <div class="mt-1 font-mono text-2xl font-bold text-amber-300">
          {stats.winaprize.human_wins}
          <span class="text-xs font-normal text-amber-200/70">
            / {stats.winaprize.total_games} ({stats.winaprize.win_rate_pct}%)
          </span>
        </div>
      </div>
      <div class="rounded-2xl border border-sky-500/30 bg-sky-950/20 p-4">
        <div class="text-xs text-sky-300">Victoires (Mode Normal)</div>
        <div class="mt-1 font-mono text-2xl font-bold text-sky-300">
          {stats.normal.human_wins}
          <span class="text-xs font-normal text-sky-200/70">
            / {stats.normal.total_games} ({stats.normal.win_rate_pct}%)
          </span>
        </div>
      </div>
      <div class="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4">
        <div class="text-xs text-emerald-300">Parties entre amis</div>
        <div class="mt-1 font-mono text-2xl font-bold text-emerald-300">
          {stats.online_pvp.total_games}
        </div>
      </div>
    </div>

    <!-- Comparatif Défi /winaprize vs Mode Normal -->
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <!-- Stats /winaprize -->
      <section class="rounded-2xl border border-amber-500/30 bg-slate-900/80 p-5 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-sm font-bold text-amber-200">Statistiques /winaprize</h2>
            <p class="text-xs text-slate-400">
              {stats.winaprize.unique_players} joueurs uniques · moy. {stats.winaprize.avg_plies} coups
            </p>
          </div>
          <span class="rounded-full bg-amber-500/20 px-2.5 py-1 font-mono text-xs font-bold text-amber-300">
            {stats.winaprize.win_rate_pct}% de victoires
          </span>
        </div>

        <div class="grid grid-cols-3 gap-2 text-center text-xs">
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Victoires joueur</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-emerald-300">
              {stats.winaprize.human_wins}
            </div>
          </div>
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Victoires IA</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-rose-300">
              {stats.winaprize.ai_wins}
            </div>
          </div>
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Matchs nuls</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-slate-300">
              {stats.winaprize.draws}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div class="rounded-xl border border-rose-500/20 bg-rose-950/20 p-2">
            <div class="text-rose-300/80">Abandons / Relances</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-rose-300">
              {stats.winaprize.forfeit_abandon || 0}
            </div>
          </div>
          <div class="rounded-xl border border-orange-500/20 bg-orange-950/20 p-2">
            <div class="text-orange-300/80">Sorties involontaires</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-orange-300">
              {stats.winaprize.forfeit_exit || 0}
            </div>
          </div>
          <div class="rounded-xl border border-amber-500/20 bg-amber-950/20 p-2">
            <div class="text-amber-300/80">Fins manuelles</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-amber-300">
              {stats.winaprize.forfeit_manual || 0}
            </div>
          </div>
        </div>

        {#if stats.winaprize.by_level.length > 0}
          <div class="space-y-1.5">
            <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Par niveau de l'IA
            </div>
            {#each stats.winaprize.by_level as row}
              <div class="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-1.5 text-xs">
                <span class="font-semibold text-slate-200">{formatLevel(row.level)}</span>
                <span class="font-mono text-slate-400">
                  <span class="text-emerald-300">{row.human_wins}V</span> ·
                  <span class="text-rose-300">{row.ai_wins}D</span> ·
                  {row.draws}N ({row.win_rate_pct}%)
                </span>
              </div>
            {/each}
          </div>
        {/if}

        <div>
          <div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300/90">
            Derniers gagnants du défi
          </div>
          {#if stats.winaprize.recent_winners.length === 0}
            <p class="rounded-lg bg-slate-950/50 p-3 text-center text-xs text-slate-500">
              Aucun gagnant enregistré pour le moment.
            </p>
          {:else}
            <div class="thin-scroll max-h-44 space-y-1 overflow-y-auto pr-1">
              {#each stats.winaprize.recent_winners as w}
                <div class="flex items-center justify-between gap-2 rounded-lg bg-slate-950/70 px-3 py-1.5 text-xs">
                  <div class="min-w-0">
                    <span class="font-semibold text-white">{w.username}</span>
                    <span class="ml-2 text-[10px] text-slate-400">
                      vs {formatLevel(w.ai_level)} · {w.total_plies} coups
                    </span>
                  </div>
                  <button
                    type="button"
                    onclick={() => openReplay(w.id)}
                    class="shrink-0 rounded bg-amber-500/20 px-2 py-0.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/30"
                  >
                    Revoir
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </section>

      <!-- Stats Mode Normal & Classement -->
      <section class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-sm font-bold text-white">Mode normal & Classement</h2>
            <p class="text-xs text-slate-400">
              JvJ local : {stats.normal.local_pvp_total} · IA vs IA : {stats.normal.ai_vs_ai_total}
            </p>
          </div>
          <span class="rounded-full bg-sky-500/20 px-2.5 py-1 font-mono text-xs font-bold text-sky-300">
            {stats.normal.win_rate_pct}% contre l'IA
          </span>
        </div>

        <div class="grid grid-cols-3 gap-2 text-center text-xs">
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Victoires humain</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-emerald-300">
              {stats.normal.human_wins}
            </div>
          </div>
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Victoires IA</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-rose-300">
              {stats.normal.ai_wins}
            </div>
          </div>
          <div class="rounded-xl bg-slate-950/70 p-2.5">
            <div class="text-slate-400">Matchs nuls</div>
            <div class="mt-0.5 font-mono text-lg font-bold text-slate-300">
              {stats.normal.draws}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div class="rounded-xl border border-rose-500/20 bg-rose-950/20 p-2">
            <div class="text-rose-300/80">Abandons / Relances</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-rose-300">
              {stats.normal.forfeit_abandon || 0}
            </div>
          </div>
          <div class="rounded-xl border border-orange-500/20 bg-orange-950/20 p-2">
            <div class="text-orange-300/80">Sorties involontaires</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-orange-300">
              {stats.normal.forfeit_exit || 0}
            </div>
          </div>
          <div class="rounded-xl border border-amber-500/20 bg-amber-950/20 p-2">
            <div class="text-amber-300/80">Fins manuelles</div>
            <div class="mt-0.5 font-mono text-sm font-bold text-amber-300">
              {stats.normal.forfeit_manual || 0}
            </div>
          </div>
        </div>

        {#if stats.normal.by_level.length > 0}
          <div class="space-y-1.5">
            <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Mode normal par niveau IA
            </div>
            {#each stats.normal.by_level as row}
              <div class="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-1.5 text-xs">
                <span class="font-semibold text-slate-200">{formatLevel(row.level)}</span>
                <span class="font-mono text-slate-400">
                  <span class="text-emerald-300">{row.human_wins}V</span> ·
                  <span class="text-rose-300">{row.ai_wins}D</span> ·
                  {row.draws}N ({row.win_rate_pct}%)
                </span>
              </div>
            {/each}
          </div>
        {/if}

        <div>
          <div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Meilleurs joueurs
          </div>
          {#if stats.top_players.length === 0}
            <p class="rounded-lg bg-slate-950/50 p-3 text-center text-xs text-slate-500">
              Aucune partie contre l'IA terminée pour le moment.
            </p>
          {:else}
            <div class="thin-scroll max-h-44 space-y-1 overflow-y-auto pr-1">
              {#each stats.top_players as tp, i}
                <div class="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-1.5 text-xs">
                  <div class="flex items-center gap-2">
                    <span class="w-5 font-mono text-slate-500">#{i + 1}</span>
                    <span class="font-semibold text-slate-100">{tp.username}</span>
                  </div>
                  <div class="flex items-center gap-2 font-mono text-[11px]">
                    {#if tp.prize_wins > 0}
                      <span class="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-300">
                        {tp.prize_wins} Prix
                      </span>
                    {/if}
                    <span class="text-emerald-300">{tp.ai_wins_beaten}V</span>
                    <span class="text-slate-500">/ {tp.games_played}P</span>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </section>
    </div>

    <!-- Historique archivé -->
    <section class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-white">Historique enregistré ({history.total})</h2>
          <p class="text-xs text-slate-400">Stocké dans SQLite de façon persistante sur votre VPS</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <select
            bind:value={channelFilter}
            onchange={loadHistoryOnly}
            class="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200"
          >
            <option value="all">Tous les canaux</option>
            <option value="winaprize">Défi /winaprize</option>
            <option value="normal">Mode normal</option>
            <option value="online_pvp">Amis en ligne</option>
          </select>

          <select
            bind:value={outcomeFilter}
            onchange={loadHistoryOnly}
            class="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200"
          >
            <option value="all">Tous les résultats</option>
            <option value="win">Victoire humain</option>
            <option value="loss">Défaite humain</option>
            <option value="draw">Match nul</option>
            <option value="forfeit_any">Tous les forfaits / fins</option>
            <option value="forfeit_abandon">Forfait (Abandon / Relance)</option>
            <option value="forfeit_exit">Forfait (Sortie involontaire)</option>
            <option value="forfeit_manual">Fin manuelle</option>
          </select>

          <input
            type="search"
            bind:value={searchQuery}
            oninput={loadHistoryOnly}
            placeholder="Rechercher un pseudo ou #salon…"
            class="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />

          <button
            type="button"
            onclick={loadAll}
            class="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            Actualiser
          </button>
        </div>
      </div>

      {#if history.records.length === 0}
        <p class="py-8 text-center text-xs text-slate-500">Aucune partie terminée enregistrée.</p>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="border-b border-slate-800 text-[11px] uppercase text-slate-400">
              <tr>
                <th class="py-2 pr-3">Canal</th>
                <th class="py-2 pr-3">Joueurs</th>
                <th class="py-2 pr-3">Grille / Niveau</th>
                <th class="py-2 pr-3">Résultat</th>
                <th class="py-2 pr-3">Coups</th>
                <th class="py-2 pr-3">Terminée le</th>
                <th class="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/70">
              {#each history.records as rec (rec.id)}
                <tr class="hover:bg-slate-800/30">
                  <td class="py-2.5 pr-3">
                    <span class="rounded border px-1.5 py-0.5 text-[10px] font-semibold {channelBadge(rec.channel)}">
                      {channelLabel(rec.channel)}
                    </span>
                    {#if rec.room_code}
                      <span class="ml-1 font-mono text-[10px] text-slate-400">#{rec.room_code}</span>
                    {/if}
                  </td>
                  <td class="py-2.5 pr-3 font-medium text-slate-200">
                    {rec.username} <span class="text-slate-500">vs</span> {rec.player2_name}
                  </td>
                  <td class="py-2.5 pr-3 font-mono text-[11px] text-slate-400">
                    {rec.rows}×{rec.cols}
                    {#if rec.ai_level}
                      <span
                        class="ml-1 rounded border px-1 py-0.5 text-[10px] {LEVEL_MAP[rec.ai_level]
                          ?.pill || 'border-slate-700'}"
                      >
                        {formatLevel(rec.ai_level)}
                      </span>
                    {/if}
                  </td>
                  <td class="py-2.5 pr-3">
                    <span class={outcomeColorClass(rec)}>
                      {formatOutcomeLabel(rec)}
                    </span>
                  </td>
                  <td class="py-2.5 pr-3 font-mono text-slate-400">{rec.total_plies}</td>
                  <td class="py-2.5 pr-3 text-[11px] text-slate-400">{formatDate(rec.finished_at)}</td>
                  <td class="py-2.5 text-right">
                    <button
                      type="button"
                      onclick={() => openReplay(rec.id)}
                      class="rounded bg-indigo-600/85 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500"
                    >
                      Revoir
                    </button>
                    <button
                      type="button"
                      onclick={() => removeRecord(rec.id)}
                      class="ml-1 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-400 hover:border-rose-500/50 hover:text-rose-300"
                    >
                      Suppr.
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>
  {/if}
</div>

<!-- Modale Replay coup par coup -->
{#if replayRecord}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
  >
    <div
      class="thin-scroll max-h-[94vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl space-y-4"
    >
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h3 class="text-base font-bold text-white">
            Replay : {replayRecord.username} vs {replayRecord.player2_name}
          </h3>
          <p class="text-xs text-slate-400">
            {channelLabel(replayRecord.channel)} · {replayRecord.rows}×{replayRecord.cols} ·
            {formatOutcomeLabel(replayRecord)}
          </p>
        </div>
        <button
          type="button"
          onclick={() => (replayRecord = null)}
          class="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 hover:bg-slate-800"
        >
          Fermer
        </button>
      </div>

      <Board
        grid={replayGrid}
        rows={replayRecord.rows}
        cols={replayRecord.cols}
        validColumns={[]}
        currentPlayer={1}
        lastMove={replayLastMove}
        winningCells={replayWinCells}
        status={replayPly === (replayRecord.move_history?.length || 0) ? replayRecord.status : 'playing'}
        canInteract={false}
        animateDrops={false}
      />

      <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3">
        <div class="flex items-center gap-1.5">
          <button
            type="button"
            onclick={() => (replayPly = 0)}
            disabled={replayPly === 0}
            class="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-200 disabled:opacity-40"
          >
            ⏮ Début
          </button>
          <button
            type="button"
            onclick={() => (replayPly = Math.max(0, replayPly - 1))}
            disabled={replayPly === 0}
            class="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-200 disabled:opacity-40"
          >
            ◀ Préc.
          </button>
          <button
            type="button"
            onclick={() =>
              (replayPly = Math.min(replayRecord.move_history?.length || 0, replayPly + 1))}
            disabled={replayPly >= (replayRecord.move_history?.length || 0)}
            class="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-200 disabled:opacity-40"
          >
            Suiv. ▶
          </button>
          <button
            type="button"
            onclick={() => (replayPly = replayRecord.move_history?.length || 0)}
            disabled={replayPly >= (replayRecord.move_history?.length || 0)}
            class="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-200 disabled:opacity-40"
          >
            Fin ⏭
          </button>
        </div>

        <div class="font-mono text-xs text-slate-300">
          Coup {replayPly} / {replayRecord.move_history?.length || 0}
          {#if replayLastMove}
            <span class="ml-2 text-indigo-300">
              ({replayLastMove.player_name} → C{replayLastMove.col + 1}·L{replayLastMove.row + 1})
            </span>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}
