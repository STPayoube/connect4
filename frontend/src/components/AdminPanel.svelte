<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    adminDeleteSession,
    adminListSessions,
    adminLogin,
    adminLogout,
    adminUpdateSessionDifficulty,
    adminUpdateSessionLiveConfig,
    forfeitGame,
    getAdminStreamUrl,
    getAdminWsUrl,
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
  let connMode = $state('offline'); // connecting | ws | sse | offline
  let filterStatus = $state('all');
  let channelFilter = $state('all');
  let searchQuery = $state('');
  let spectateId = $state(null);
  let nowMs = $state(Date.now());
  let adminToast = $state(null);
  let collisionPopup = $state(null);

  // Live board resize controls inside Spectate Modal
  let specRows = $state(6);
  let specCols = $state(7);
  let specAlign = $state(4);
  let specSaving = $state(false);

  let socket = null;
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
  let specMaxAlign = $derived(Math.min(specRows, specCols));

  $effect(() => {
    if (specAlign > specMaxAlign) specAlign = specMaxAlign;
  });

  function openSpectate(session) {
    spectateId = session.session_id;
    specRows = session.config.rows;
    specCols = session.config.cols;
    specAlign = session.config.align;
  }

  function showToast(msg) {
    adminToast = msg;
    setTimeout(() => {
      if (adminToast === msg) adminToast = null;
    }, 3200);
  }

  function closeConnections() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
      socket = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    connMode = 'offline';
  }

  function handleStreamMessage(eventType, data) {
    if (eventType === 'init') {
      const next = {};
      for (const s of data.sessions || []) {
        next[s.session_id] = s;
      }
      sessionsMap = next;
    } else if (eventType === 'session_update') {
      sessionsMap = { ...sessionsMap, [data.session_id]: data };
    } else if (eventType === 'session_delete') {
      const next = { ...sessionsMap };
      delete next[data.session_id];
      sessionsMap = next;
      if (spectateId === data.session_id) spectateId = null;
    } else if (eventType === 'stats_update') {
      statsRefreshTick += 1;
    }
  }

  function connectAdminSseFallback(activeToken) {
    if (eventSource) eventSource.close();
    const es = new EventSource(getAdminStreamUrl(activeToken));
    eventSource = es;

    es.addEventListener('init', (evt) => {
      try {
        handleStreamMessage('init', JSON.parse(evt.data));
        connMode = 'sse';
      } catch {
        // ignore
      }
    });
    es.addEventListener('session_update', (evt) => {
      try {
        handleStreamMessage('session_update', JSON.parse(evt.data));
        connMode = 'sse';
      } catch {
        // ignore
      }
    });
    es.addEventListener('session_delete', (evt) => {
      try {
        handleStreamMessage('session_delete', JSON.parse(evt.data));
      } catch {
        // ignore
      }
    });
    es.addEventListener('stats_update', () => {
      statsRefreshTick += 1;
    });
    es.onopen = () => {
      connMode = 'sse';
    };
    es.onerror = async () => {
      connMode = 'offline';
      es.close();
      eventSource = null;
      await verifyAndScheduleReconnect(activeToken);
    };
  }

  async function verifyAndScheduleReconnect(activeToken) {
    try {
      await adminListSessions(activeToken);
      reconnectTimer = setTimeout(() => connectAdminSocket(activeToken), 2500);
    } catch (err) {
      if (err.status === 401) {
        handleSignOut(false);
        loginError = 'Session administrateur expirée. Veuillez vous reconnecter.';
      } else {
        reconnectTimer = setTimeout(() => connectAdminSocket(activeToken), 3000);
      }
    }
  }

  function connectAdminSocket(activeToken) {
    closeConnections();
    if (!activeToken) return;

    connMode = 'connecting';
    let openedOnce = false;
    const ws = new WebSocket(getAdminWsUrl(activeToken));
    socket = ws;

    ws.onopen = () => {
      openedOnce = true;
      connMode = 'ws';
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event) {
          handleStreamMessage(msg.event, msg.data);
          connMode = 'ws';
        }
      } catch {
        // ignore
      }
    };

    ws.onclose = async (evt) => {
      if (socket !== ws) return;
      socket = null;
      if (evt.code === 4401) {
        handleSignOut(false);
        loginError = 'Session administrateur expirée. Veuillez vous reconnecter.';
        return;
      }
      if (!openedOnce) {
        connectAdminSseFallback(activeToken);
      } else {
        connMode = 'offline';
        await verifyAndScheduleReconnect(activeToken);
      }
    };

    ws.onerror = () => {
      ws.close();
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
      connectAdminSocket(token);
    } catch (err) {
      loginError = err.message || 'Échec de la connexion.';
    } finally {
      loggingIn = false;
    }
  }

  async function handleSignOut(callApi = true) {
    const oldToken = token;
    closeConnections();
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

  async function handleForceEndSession(session) {
    if (!token || session.status !== 'playing') return;
    try {
      const updated = await forfeitGame(session.session_id, 'manual_end');
      sessionsMap = { ...sessionsMap, [updated.session_id]: updated };
      showToast(`Partie de ${session.username} terminée et enregistrée dans l'historique.`);
    } catch (err) {
      showToast(err.message || 'Impossible de terminer cette partie.');
    }
  }

  function formatStatusBadge(s) {
    if (s.waiting_for_opponent) return 'Attente';
    if (s.status === 'playing') return 'En direct';
    if (s.status === 'win') return `Gagné : ${s.players?.[String(s.winner)]?.name}`;
    if (s.status === 'draw') return 'Nul';
    if (s.status === 'forfeit') {
      if (s.end_reason === 'accidental_exit') return 'Forfait (Sortie)';
      if (s.end_reason === 'abandon_restart') return 'Forfait (Abandon)';
      return 'Fin manuelle';
    }
    return s.status;
  }

  async function handleLiveDifficultyChange(session, newLevel) {
    if (!token || session.config.mode === 'player_vs_player') return;
    try {
      const updated = await adminUpdateSessionDifficulty(token, session.session_id, newLevel);
      sessionsMap = { ...sessionsMap, [updated.session_id]: updated };
      showToast(`IA de ${session.username} passée en ${formatLevel(newLevel)} en direct !`);
    } catch (err) {
      showToast(err.message || 'Impossible de modifier la difficulté.');
    }
  }

  async function handleLiveBoardResize(session) {
    if (!token) return;
    specSaving = true;
    try {
      const updated = await adminUpdateSessionLiveConfig(token, session.session_id, {
        rows: Number(specRows),
        cols: Number(specCols),
        align: Number(specAlign),
      });
      sessionsMap = { ...sessionsMap, [updated.session_id]: updated };
      showToast(
        `Grille de ${session.username} redimensionnée en ${updated.config.rows}×${updated.config.cols} (align ${updated.config.align}) !`
      );
    } catch (err) {
      if (err.status === 409) {
        collisionPopup = err.message;
        specRows = session.config.rows;
        specCols = session.config.cols;
        specAlign = session.config.align;
      } else {
        showToast(err.message || 'Erreur lors du redimensionnement.');
      }
    } finally {
      specSaving = false;
    }
  }

  function formatMode(mode) {
    if (mode === 'player_vs_player') return 'JvJ';
    if (mode === 'ai_vs_ai') return 'IA vs IA';
    return "Contre l'IA";
  }

  function formatTimeAgo(ts) {
    const diff = Math.max(0, Math.floor(nowMs / 1000 - ts));
    if (diff < 5) return "à l'instant";
    if (diff < 60) return `il y a ${diff}s`;
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)}m`;
    return `il y a ${Math.floor(diff / 3600)}h`;
  }

  function isWinningCell(session, r, c) {
    return (session.winning_cells || []).some(([wr, wc]) => wr === r && wc === c);
  }

  function handleWindowKeydown(event) {
    if (event.key === 'Escape') {
      if (collisionPopup) collisionPopup = null;
      else if (spectateId) spectateId = null;
    }
  }

  onMount(() => {
    clockTimer = setInterval(() => {
      nowMs = Date.now();
    }, 5000);
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      token = saved;
      connectAdminSocket(saved);
    }
  });

  onDestroy(() => {
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
    closeConnections();
  });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Barre supérieure -->
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
          <h1 class="text-lg font-bold text-white sm:text-xl">Panneau d'administration</h1>
          <p class="text-xs text-slate-400">
            Parties en direct, difficulté & taille de grille à la volée, statistiques, /winaprize et liste noire
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2.5">
        {#if token}
          <div
            class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium {connMode ===
              'ws' || connMode === 'sse'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : connMode === 'connecting'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-300'}"
          >
            <span
              class="h-2 w-2 rounded-full {connMode === 'ws' || connMode === 'sse'
                ? 'animate-pulse bg-emerald-400'
                : connMode === 'connecting'
                  ? 'animate-pulse bg-amber-400'
                  : 'bg-rose-400'}"
            ></span>
            {connMode === 'ws'
              ? 'WebSocket direct'
              : connMode === 'sse'
                ? 'Flux direct'
                : connMode === 'connecting'
                  ? 'Connexion…'
                  : 'Reconnexion…'}
          </div>
          <button
            type="button"
            onclick={() => handleSignOut(true)}
            class="rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800"
          >
            Déconnexion
          </button>
        {/if}

        <button
          type="button"
          onclick={onBackToGame}
          class="rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
        >
          ← Retour au jeu
        </button>
      </div>
    </header>

    {#if !token}
      <!-- Écran de connexion Admin -->
      <div class="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">Authentification administrateur</h2>
        <p class="mt-1 text-xs text-slate-400">
          Entrez le mot de passe administrateur pour accéder au suivi temps réel, aux statistiques et aux réglages.
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
              Mot de passe administrateur
            </label>
            <input
              id="admin-pwd"
              type="password"
              required
              bind:value={password}
              placeholder="Entrez le mot de passe"
              class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={loggingIn}
            class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-50"
          >
            {loggingIn ? 'Vérification…' : 'Déverrouiller le panneau'}
          </button>
        </form>
      </div>
    {:else}
      <!-- Onglets Admin -->
      <nav class="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
        {#each [
          { id: 'live', label: `Parties en direct (${stats.playing})` },
          { id: 'stats', label: 'Statistiques & Historique' },
          { id: 'prize', label: `Contrôle /winaprize (${stats.prizeLive} en cours)` },
          { id: 'blacklist', label: 'Liste noire' },
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
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
            <div class="text-xs text-slate-400">Sessions actives</div>
            <div class="mt-1 font-mono text-2xl font-bold text-white">{stats.total}</div>
          </div>
          <div class="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4">
            <div class="text-xs text-emerald-300">En cours</div>
            <div class="mt-1 font-mono text-2xl font-bold text-emerald-300">{stats.playing}</div>
          </div>
          <div class="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-4">
            <div class="text-xs text-amber-300">/winaprize en cours</div>
            <div class="mt-1 font-mono text-2xl font-bold text-amber-300">{stats.prizeLive}</div>
          </div>
          <div class="rounded-2xl border border-indigo-500/30 bg-indigo-950/20 p-4">
            <div class="text-xs text-indigo-300">Amis en ligne</div>
            <div class="mt-1 font-mono text-2xl font-bold text-indigo-300">{stats.onlineLive}</div>
          </div>
        </div>

        <!-- Filtres -->
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <div class="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1">
              {#each [
                { id: 'all', label: 'Toutes' },
                { id: 'playing', label: 'En cours' },
                { id: 'finished', label: 'Terminées' },
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
              <option value="all">Tous les canaux</option>
              <option value="winaprize">/winaprize</option>
              <option value="normal">Mode normal</option>
              <option value="online_pvp">Amis en ligne</option>
            </select>
          </div>

          <input
            type="search"
            bind:value={searchQuery}
            placeholder="Filtrer par pseudo, #salon ou ID…"
            class="w-full rounded-xl border border-slate-800 bg-slate-900/90 px-3.5 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none sm:w-72"
          />
        </div>

        {#if sessionsList.length === 0}
          <div
            class="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-6 py-16 text-center"
          >
            <p class="text-sm font-medium text-slate-300">Aucune partie active pour ce filtre.</p>
            <p class="mt-1 text-xs text-slate-500">
              Les grilles en direct apparaîtront ici dès que des joueurs lanceront une partie.
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
                <div class="space-y-2">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <span class="truncate text-sm font-bold text-white">{s.username}</span>
                        {#if s.channel === 'winaprize'}
                          <span
                            class="rounded-full border border-amber-400/50 bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200"
                          >
                            Prix
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
                              : s.status === 'forfeit'
                                ? s.end_reason === 'manual_end'
                                  ? 'bg-amber-500/20 text-amber-300'
                                  : 'bg-rose-500/20 text-rose-300'
                                : 'bg-slate-800 text-slate-300'}"
                        >
                          {formatStatusBadge(s)}
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

                  <div class="flex flex-wrap items-center gap-1.5 text-[10px]">
                    <span class="rounded bg-slate-800 px-1.5 py-0.5 font-medium text-slate-300">
                      {formatMode(s.config.mode)}
                    </span>
                    <span class="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-400">
                      {s.config.rows}×{s.config.cols} · A{s.config.align}
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
                      {s.move_history.length} coups
                    </span>
                  </div>
                </div>

                <!-- Mini grille en direct -->
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

                {#if s.config.mode !== 'player_vs_player' && s.status === 'playing'}
                  <div class="mb-2.5">
                    <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Difficulté en direct
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
                          {lvl.short}
                        </button>
                      {/each}
                    </div>
                  </div>
                {/if}

                <div class="flex items-center justify-between gap-2 pt-1">
                  <span class="font-mono text-[10px] text-slate-500">
                    ID {s.session_id.slice(0, 8)}
                  </span>
                  <div class="flex items-center gap-1.5">
                    {#if s.status === 'playing'}
                      <button
                        type="button"
                        onclick={() => handleForceEndSession(s)}
                        class="rounded-lg border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/20"
                        title="Clôturer la partie et l'archiver dans SQLite"
                      >
                        Terminer
                      </button>
                    {/if}
                    <button
                      type="button"
                      onclick={() => openSpectate(s)}
                      class="rounded-lg bg-indigo-600/90 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500"
                    >
                      Observer / Modifier
                    </button>
                    <button
                      type="button"
                      onclick={() => handleDeleteSession(s.session_id)}
                      class="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-400 hover:border-rose-500/50 hover:text-rose-300"
                    >
                      Suppr.
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

<!-- Modale Spectateur + Modification en direct (Difficulté & Taille de grille) -->
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
              En direct : {spectatedSession.username}
            </h2>
            <span class="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
              {spectatedSession.players?.['1']?.name} vs {spectatedSession.players?.['2']?.name}
            </span>
          </div>
          <p class="mt-0.5 text-xs text-slate-400">
            Modifiez la difficulté ou la taille de la grille en temps réel ci-contre
          </p>
        </div>
        <button
          type="button"
          onclick={() => (spectateId = null)}
          class="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 hover:bg-slate-800"
        >
          Fermer
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
          {#if spectatedSession.status === 'playing'}
            {#if spectatedSession.config.mode !== 'player_vs_player'}
              <div class="rounded-2xl border border-amber-500/35 bg-amber-950/15 p-3.5">
                <div class="mb-2 text-xs font-bold uppercase tracking-wider text-amber-300">
                  Changer la difficulté en direct
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

            <!-- Redimensionnement de grille en direct -->
            <div class="rounded-2xl border border-indigo-500/35 bg-indigo-950/15 p-3.5 space-y-3">
              <div class="text-xs font-bold uppercase tracking-wider text-indigo-300">
                Redimensionner la grille en direct
              </div>
              <div class="space-y-2 text-xs">
                <div>
                  <label for="spec-rows" class="mb-0.5 flex justify-between text-slate-300">
                    <span>Lignes</span><span class="font-mono text-indigo-300">{specRows}</span>
                  </label>
                  <input id="spec-rows" type="range" min="4" max="10" bind:value={specRows} class="w-full accent-indigo-500" />
                </div>
                <div>
                  <label for="spec-cols" class="mb-0.5 flex justify-between text-slate-300">
                    <span>Colonnes</span><span class="font-mono text-indigo-300">{specCols}</span>
                  </label>
                  <input id="spec-cols" type="range" min="4" max="10" bind:value={specCols} class="w-full accent-indigo-500" />
                </div>
                <div>
                  <label for="spec-align" class="mb-0.5 flex justify-between text-slate-300">
                    <span>Alignement</span><span class="font-mono text-indigo-300">{specAlign}</span>
                  </label>
                  <input id="spec-align" type="range" min="3" max={specMaxAlign} bind:value={specAlign} class="w-full accent-indigo-500" />
                </div>
              </div>
              <button
                type="button"
                disabled={specSaving}
                onclick={() => handleLiveBoardResize(spectatedSession)}
                class="w-full rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {specSaving ? 'Application…' : 'Appliquer la taille en direct'}
              </button>
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

<!-- Pop-up d'erreur de collision -->
{#if collisionPopup}
  <div
    class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
    role="alertdialog"
    aria-modal="true"
  >
    <div class="w-full max-w-md rounded-2xl border border-rose-500/50 bg-slate-900 p-6 shadow-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-500/20 text-rose-300">
          ⚠️
        </div>
        <div>
          <h3 class="text-base font-bold text-rose-200">Redimensionnement impossible</h3>
          <p class="text-xs text-slate-400">Des pions occupent déjà les cases supprimées</p>
        </div>
      </div>

      <p class="mt-4 rounded-xl border border-rose-500/30 bg-rose-950/40 p-3 text-xs leading-relaxed text-rose-100">
        {collisionPopup}
      </p>

      <div class="mt-5 flex justify-end">
        <button
          type="button"
          onclick={() => (collisionPopup = null)}
          class="rounded-xl bg-rose-600 px-5 py-2 text-xs font-semibold text-white hover:bg-rose-500"
        >
          Compris
        </button>
      </div>
    </div>
  </div>
{/if}
