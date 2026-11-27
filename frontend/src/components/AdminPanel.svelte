<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    adminDeleteSession,
    adminListSessions,
    adminLogin,
    adminLogout,
    adminUpdateSessionDifficulty,
    getAdminStreamUrl,
  } from '../lib/api.js';
  import { formatLevel, LEVEL_MAP, LEVELS } from '../lib/levels.js';
  import Board from './Board.svelte';
  import MoveHistory from './MoveHistory.svelte';
  import AiInspector from './AiInspector.svelte';
  import AdminStatsTab from './AdminStatsTab.svelte';
  import AdminPrizeTab from './AdminPrizeTab.svelte';
  import AdminBlacklistTab from './AdminBlacklistTab.svelte';

  let { onBackToGame = () => {} } = $props();

  const TOKEN_KEY = 'connect4_admin_token';

  let token = $state('');
  let password = $state('');
  let loginError = $state(null);
  let loggingIn = $state(false);

  let activeTab = $state('live'); // live | stats | prize | blacklist
  let statsRefreshTick = $state(0);

  let sessionsMap = $state({});
  let streamStatus = $state('disconnected');
  let filterStatus = $state('all');
  let channelFilter = $state('all');
  let searchQuery = $state('');
  let spectateId = $state(null);
  let nowMs = $state(Date.now());
  let adminToast = $state(null);

  let eventSource = null;
  let reconnectTimer = null;
  let clockTimer = null;

  let sessionsList = $derived(
    Object.values(sessionsMap)
      .filter((s) => {
        if (filterStatus === 'playing' && s.status !== 'playing') return false;
        if (filterStatus === 'finished' && s.status === 'playing') return false;
        if (channelFilter !== 'all' && (s.channel || 'normal') !== channelFilter) return false;
        if (searchQuery.trim()) {
          const q = searchQuery.trim().toLowerCase();
          const p1 = s.players?.['1']?.name?.toLowerCase() || '';
          const p2 = s.players?.['2']?.name?.toLowerCase() || '';
          const user = (s.username || '').toLowerCase();
          const rc = (s.room_code || '').toLowerCase();
          return (
            user.includes(q) ||
            p1.includes(q) ||
            p2.includes(q) ||
            rc.includes(q) ||
            s.session_id.includes(q)
          );
        }
        return true;
      })
      .sort((a, b) => b.updated_at - a.updated_at)
  );

  let stats = $derived({
    total: Object.keys(sessionsMap).length,
    playing: Object.values(sessionsMap).filter((s) => s.status === 'playing').length,
    prizeLive: Object.values(sessionsMap).filter(
      (s) => s.channel === 'winaprize' && s.status === 'playing'
    ).length,
    onlineLive: Object.values(sessionsMap).filter(
      (s) => s.channel === 'online_pvp' && s.status === 'playing'
    ).length,
  });

  let spectatedSession = $derived(spectateId ? sessionsMap[spectateId] || null : null);

  function showToast(msg) {
    adminToast = msg;
    setTimeout(() => {
      if (adminToast === msg) adminToast = null;
    }, 3000);
  }

  function closeStream() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    streamStatus = 'disconnected';
  }

  function connectStream(activeToken) {
    closeStream();
    if (!activeToken) return;

    streamStatus = 'connecting';
    const es = new EventSource(getAdminStreamUrl(activeToken));
    eventSource = es;

    es.addEventListener('init', (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        const next = {};
        for (const s of parsed.sessions || []) {
          next[s.session_id] = s;
        }
        sessionsMap = next;
        streamStatus = 'connected';
      } catch {
        // ignore
      }
    });

    es.addEventListener('session_update', (evt) => {
      try {
        const s = JSON.parse(evt.data);
        sessionsMap = { ...sessionsMap, [s.session_id]: s };
        streamStatus = 'connected';
      } catch {
        // ignore
      }
    });

    es.addEventListener('session_delete', (evt) => {
      try {
        const { session_id } = JSON.parse(evt.data);
        const next = { ...sessionsMap };
        delete next[session_id];
        sessionsMap = next;
        if (spectateId === session_id) spectateId = null;
      } catch {
        // ignore
      }
    });

    es.addEventListener('stats_update', () => {
      statsRefreshTick += 1;
    });

    es.onopen = () => {
      streamStatus = 'connected';
    };

    es.onerror = async () => {
      streamStatus = 'error';
      es.close();
      eventSource = null;

      try {
        await adminListSessions(activeToken);
        reconnectTimer = setTimeout(() => connectStream(activeToken), 2500);
      } catch (err) {
        if (err.status === 401) {
          handleSignOut(false);
          loginError = 'Admin session expired. Please sign in again.';
        } else {
          reconnectTimer = setTimeout(() => connectStream(activeToken), 3000);
        }
      }
    };
  }

  async function handleLogin(event) {
    event.preventDefault();
    loginError = null;
    loggingIn = true;
    try {
      const res = await adminLogin(password);
      token = res.token;
      sessionStorage.setItem(TOKEN_KEY, token);
      password = '';
      connectStream(token);
    } catch (err) {
      loginError = err.message || 'Authentication failed.';
    } finally {
      loggingIn = false;
    }
  }

  async function handleSignOut(callApi = true) {
    const oldToken = token;
    closeStream();
    token = '';
    sessionsMap = {};
    spectateId = null;
    sessionStorage.removeItem(TOKEN_KEY);
    if (callApi && oldToken) {
      try {
        await adminLogout(oldToken);
      } catch {
        // ignore
      }
    }
  }

  async function handleDeleteSession(sessionId) {
    if (!token) return;
    try {
      await adminDeleteSession(token, sessionId);
    } catch {
      // ignore
    }
  }

  async function handleLiveDifficultyChange(session, newLevel) {
    if (!token || session.config.mode === 'player_vs_player') return;
    try {
      const updated = await adminUpdateSessionDifficulty(token, session.session_id, newLevel);
      sessionsMap = { ...sessionsMap, [updated.session_id]: updated };
      showToast(`Switched ${session.username}'s AI to ${formatLevel(newLevel)} live!`);
    } catch (err) {
      showToast(err.message || 'Failed to switch difficulty.');
    }
  }

  function formatMode(mode) {
    if (mode === 'player_vs_player') return 'PvP';
    if (mode === 'ai_vs_ai') return 'AI vs AI';
    return 'Human vs AI';
  }

  function formatTimeAgo(ts) {
    const diff = Math.max(0, Math.floor(nowMs / 1000 - ts));
    if (diff < 5) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  }

  function isWinningCell(session, r, c) {
    return (session.winning_cells || []).some(([wr, wc]) => wr === r && wc === c);
  }

  function handleWindowKeydown(event) {
    if (event.key === 'Escape' && spectateId) {
      spectateId = null;
    }
  }

  onMount(() => {
    clockTimer = setInterval(() => {
      nowMs = Date.now();
    }, 5000);
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      token = saved;
      connectStream(saved);
    }
  });

  onDestroy(() => {
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
    closeStream();
  });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Top Bar -->
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div
          class="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-400/40 bg-indigo-500/20 text-indigo-300 shadow"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
        </div>
        <div>
          <h1 class="text-lg font-bold text-white sm:text-xl">Admin Control Center</h1>
          <p class="text-xs text-slate-400">
            Live gameplay, mid-game AI difficulty, statistics, /winaprize & blacklist
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2.5">
        {#if token}
          <div
            class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium {streamStatus ===
            'connected'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : streamStatus === 'connecting'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-300'}"
          >
            <span
              class="h-2 w-2 rounded-full {streamStatus === 'connected'
                ? 'animate-pulse bg-emerald-400'
                : streamStatus === 'connecting'
                  ? 'animate-pulse bg-amber-400'
                  : 'bg-rose-400'}"
            ></span>
            {streamStatus === 'connected'
              ? 'Live Stream'
              : streamStatus === 'connecting'
                ? 'Connecting…'
                : 'Reconnecting…'}
          </div>
          <button
            type="button"
            onclick={() => handleSignOut(true)}
            class="rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800"
          >
            Sign Out
          </button>
        {/if}

        <button
          type="button"
          onclick={onBackToGame}
          class="rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
        >
          ← Back to Game
        </button>
      </div>
    </header>

    {#if !token}
      <!-- Admin Login Gate -->
      <div class="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">Admin Authentication</h2>
        <p class="mt-1 text-xs text-slate-400">
          Enter the server admin password to access live games, stats, /winaprize controls, and blacklist.
        </p>

        {#if loginError}
          <div
            class="mt-4 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3.5 py-2 text-xs text-rose-200"
          >
            {loginError}
          </div>
        {/if}

        <form onsubmit={handleLogin} class="mt-5 space-y-4">
          <div>
            <label for="admin-pwd" class="mb-1.5 block text-xs font-medium text-slate-300">
              Admin Password
            </label>
            <input
              id="admin-pwd"
              type="password"
              required
              bind:value={password}
              placeholder="Enter admin password"
              class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={loggingIn}
            class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-50"
          >
            {loggingIn ? 'Verifying…' : 'Unlock Control Panel'}
          </button>
        </form>
      </div>
    {:else}
      <!-- Admin Navigation Tabs -->
      <nav class="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
        {#each [
          { id: 'live', label: `Live Games (${stats.playing})` },
          { id: 'stats', label: 'Statistics & History' },
          { id: 'prize', label: `/winaprize Control (${stats.prizeLive} live)` },
          { id: 'blacklist', label: 'Username Blacklist' },
        ] as tab}
          <button
            type="button"
            onclick={() => (activeTab = tab.id)}
            class="rounded-xl px-4 py-2 text-xs font-semibold transition {activeTab === tab.id
              ? 'bg-indigo-600 text-white shadow'
              : 'border border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-100'}"
          >
            {tab.label}
          </button>
        {/each}
      </nav>

      {#if adminToast}
        <div
          class="rounded-xl border border-emerald-500/40 bg-emerald-950/60 px-4 py-2.5 text-xs font-medium text-emerald-200"
        >
          {adminToast}
        </div>
      {/if}

      {#if activeTab === 'live'}
        <!-- Stats Strip -->
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
            <div class="text-xs text-slate-400">Active Sessions</div>
            <div class="mt-1 font-mono text-2xl font-bold text-white">{stats.total}</div>
          </div>
          <div class="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4">
            <div class="text-xs text-emerald-300">Live Playing</div>
            <div class="mt-1 font-mono text-2xl font-bold text-emerald-300">{stats.playing}</div>
          </div>
          <div class="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-4">
            <div class="text-xs text-amber-300">Live /winaprize</div>
            <div class="mt-1 font-mono text-2xl font-bold text-amber-300">{stats.prizeLive}</div>
          </div>
          <div class="rounded-2xl border border-indigo-500/30 bg-indigo-950/20 p-4">
            <div class="text-xs text-indigo-300">Live Online Friend</div>
            <div class="mt-1 font-mono text-2xl font-bold text-indigo-300">{stats.onlineLive}</div>
          </div>
        </div>

        <!-- Filter & Search Bar -->
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <div class="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1">
              {#each [
                { id: 'all', label: 'All' },
                { id: 'playing', label: 'Live' },
                { id: 'finished', label: 'Finished' },
              ] as tab}
                <button
                  type="button"
                  onclick={() => (filterStatus = tab.id)}
                  class="rounded-lg px-3 py-1.5 text-xs font-semibold transition {filterStatus === tab.id
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'}"
                >
                  {tab.label}
                </button>
              {/each}
            </div>

            <select
              bind:value={channelFilter}
              class="rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-2 text-xs text-slate-200"
            >
              <option value="all">All Channels</option>
              <option value="winaprize">/winaprize</option>
              <option value="normal">Normal</option>
              <option value="online_pvp">Online Friend</option>
            </select>
          </div>

          <input
            type="search"
            bind:value={searchQuery}
            placeholder="Filter by username, #room, or ID…"
            class="w-full rounded-xl border border-slate-800 bg-slate-900/90 px-3.5 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none sm:w-72"
          />
        </div>

        <!-- Live Multi-Game Grid -->
        {#if sessionsList.length === 0}
          <div
            class="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-6 py-16 text-center"
          >
            <p class="text-sm font-medium text-slate-300">No active games match this filter.</p>
            <p class="mt-1 text-xs text-slate-500">
              Live boards appear here in real time as players start games on /, /winaprize, or /game#XXXXXX.
            </p>
          </div>
        {:else}
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {#each sessionsList as s (s.session_id)}
              {@const p1 = s.players?.['1']}
              {@const p2 = s.players?.['2']}
              <article
                class="flex flex-col justify-between rounded-2xl border bg-slate-900/80 p-4 shadow-lg transition {s.channel ===
                'winaprize'
                  ? 'border-amber-500/45'
                  : s.status === 'playing'
                    ? 'border-indigo-500/35'
                    : 'border-slate-800'}"
              >
                <!-- Card Header -->
                <div class="space-y-2">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <span class="truncate text-sm font-bold text-white">{s.username}</span>
                        {#if s.channel === 'winaprize'}
                          <span
                            class="rounded-full border border-amber-400/50 bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200"
                          >
                            Prize
                          </span>
                        {:else if s.channel === 'online_pvp'}
                          <span
                            class="rounded-full border border-emerald-400/50 bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-200"
                          >
                            #{s.room_code}
                          </span>
                        {/if}
                        <span
                          class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase {s.status ===
                          'playing'
                            ? 'bg-emerald-500/15 text-emerald-300'
                            : s.status === 'win'
                              ? 'bg-indigo-500/20 text-indigo-300'
                              : 'bg-slate-800 text-slate-300'}"
                        >
                          {s.waiting_for_opponent
                            ? 'Waiting'
                            : s.status === 'playing'
                              ? 'Live'
                              : s.status === 'win'
                                ? `Won: ${s.players?.[String(s.winner)]?.name}`
                                : 'Draw'}
                        </span>
                      </div>
                      <p class="mt-0.5 truncate text-[11px] text-slate-400">
                        <span class="text-rose-400">{p1?.name}</span> vs
                        <span class="text-amber-300">{p2?.name}</span>
                      </p>
                    </div>

                    <span class="shrink-0 font-mono text-[10px] text-slate-500">
                      {formatTimeAgo(s.updated_at)}
                    </span>
                  </div>

                  <!-- Tags -->
                  <div class="flex flex-wrap items-center gap-1.5 text-[10px]">
                    <span class="rounded bg-slate-800 px-1.5 py-0.5 font-medium text-slate-300">
                      {formatMode(s.config.mode)}
                    </span>
                    <span class="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-400">
                      {s.config.rows}×{s.config.cols} · C{s.config.align}
                    </span>
                    {#if s.config.mode !== 'player_vs_player'}
                      <span
                        class="rounded border px-1.5 py-0.5 font-semibold {LEVEL_MAP[
                          s.config.ai_level
                        ]?.pill || 'border-slate-700 text-slate-300'}"
                      >
                        {formatLevel(s.config.ai_level)}
                      </span>
                    {/if}
                    <span class="ml-auto font-mono text-slate-400">
                      {s.move_history.length} moves
                    </span>
                  </div>
                </div>

                <!-- Live Mini Board -->
                <div
                  class="my-3 rounded-xl border border-indigo-400/20 bg-gradient-to-b from-indigo-950/90 to-slate-950 p-2"
                >
                  <div
                    class="grid gap-1"
                    style="grid-template-columns: repeat({s.config.cols}, minmax(0, 1fr));"
                  >
                    {#each s.grid as rowArr, rIdx}
                      {#each rowArr as val, cIdx}
                        {@const isLast =
                          s.last_move && s.last_move.row === rIdx && s.last_move.col === cIdx}
                        {@const isWin = isWinningCell(s, rIdx, cIdx)}
                        <div
                          class="flex aspect-square items-center justify-center rounded-full bg-slate-950/90 p-[8%]"
                        >
                          {#if val === 1}
                            <div
                              class="h-full w-full rounded-full bg-rose-500 {isWin
                                ? 'ring-2 ring-emerald-300'
                                : isLast
                                  ? 'ring-2 ring-white'
                                  : ''}"
                            ></div>
                          {:else if val === 2}
                            <div
                              class="h-full w-full rounded-full bg-amber-400 {isWin
                                ? 'ring-2 ring-emerald-300'
                                : isLast
                                  ? 'ring-2 ring-white'
                                  : ''}"
                            ></div>
                          {/if}
                        </div>
                      {/each}
                    {/each}
                  </div>
                </div>

                <!-- Live Mid-Game Difficulty Switcher for AI games -->
                {#if s.config.mode !== 'player_vs_player' && s.status === 'playing'}
                  <div class="mb-2.5">
                    <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Live Difficulty Override
                    </div>
                    <div class="grid grid-cols-4 gap-1">
                      {#each LEVELS as lvl}
                        <button
                          type="button"
                          onclick={() => handleLiveDifficultyChange(s, lvl.id)}
                          class="rounded-md border py-1 text-center text-[10px] font-semibold transition {s
                            .config.ai_level === lvl.id
                            ? lvl.active
                            : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-600 hover:text-slate-200'}"
                        >
                          {lvl.id === 'impossible' ? 'Imp' : lvl.label}
                        </button>
                      {/each}
                    </div>
                  </div>
                {/if}

                <!-- Footer Actions -->
                <div class="flex items-center justify-between gap-2 pt-1">
                  <span class="font-mono text-[10px] text-slate-500">
                    ID {s.session_id.slice(0, 8)}
                  </span>
                  <div class="flex items-center gap-1.5">
                    <button
                      type="button"
                      onclick={() => (spectateId = s.session_id)}
                      class="rounded-lg bg-indigo-600/90 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500"
                    >
                      Spectate Live
                    </button>
                    <button
                      type="button"
                      onclick={() => handleDeleteSession(s.session_id)}
                      class="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-400 hover:border-rose-500/50 hover:text-rose-300"
                      title="Delete session"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </article>
            {/each}
          </div>
        {/if}
      {:else if activeTab === 'stats'}
        <AdminStatsTab {token} refreshTrigger={statsRefreshTick} />
      {:else if activeTab === 'prize'}
        <AdminPrizeTab {token} />
      {:else if activeTab === 'blacklist'}
        <AdminBlacklistTab {token} />
      {/if}
    {/if}
  </div>
</div>

<!-- Live Spectate Modal -->
{#if spectatedSession}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
  >
    <div
      class="thin-scroll max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl"
    >
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <div class="flex items-center gap-2">
            <span class="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400"></span>
            <h2 class="text-base font-bold text-white">
              Spectating: {spectatedSession.username}
            </h2>
            <span class="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
              {spectatedSession.players?.['1']?.name} vs {spectatedSession.players?.['2']?.name}
            </span>
          </div>
          <p class="mt-0.5 text-xs text-slate-400">
            Updates automatically in real time — switch difficulty below anytime
          </p>
        </div>
        <button
          type="button"
          onclick={() => (spectateId = null)}
          class="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 hover:bg-slate-800"
        >
          Close
        </button>
      </div>

      <div class="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
        <Board
          grid={spectatedSession.grid}
          rows={spectatedSession.config.rows}
          cols={spectatedSession.config.cols}
          validColumns={[]}
          currentPlayer={spectatedSession.current_player}
          lastMove={spectatedSession.last_move}
          winningCells={spectatedSession.winning_cells}
          status={spectatedSession.status}
          canInteract={false}
          animateDrops={false}
        />

        <div class="space-y-4">
          {#if spectatedSession.config.mode !== 'player_vs_player' && spectatedSession.status === 'playing'}
            <div class="rounded-2xl border border-amber-500/35 bg-amber-950/15 p-3.5">
              <div class="mb-2 text-xs font-bold uppercase tracking-wider text-amber-300">
                Change AI Difficulty Mid-Game
              </div>
              <div class="grid grid-cols-2 gap-1.5">
                {#each LEVELS as lvl}
                  <button
                    type="button"
                    onclick={() => handleLiveDifficultyChange(spectatedSession, lvl.id)}
                    class="rounded-xl border px-2.5 py-2 text-left text-xs font-semibold transition {spectatedSession
                      .config.ai_level === lvl.id
                      ? lvl.active
                      : 'border-slate-800 bg-slate-950/70 text-slate-300 hover:border-slate-600'}"
                  >
                    {lvl.label}
                  </button>
                {/each}
              </div>
            </div>
          {/if}

          {#if spectatedSession.config.mode !== 'player_vs_player'}
            <AiInspector
              aiInfo={spectatedSession.ai_info}
              config={spectatedSession.config}
            />
          {/if}
          <MoveHistory moves={spectatedSession.move_history} />
        </div>
      </div>
    </div>
  </div>
{/if}
