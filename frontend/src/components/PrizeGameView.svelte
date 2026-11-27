<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    checkUsername,
    createWinAPrizeGame,
    forfeitGame,
    getGame,
    getGameWsUrl,
    getWinAPrizeConfig,
    playHumanMove,
    stepAiMove,
    undoMove,
  } from '../lib/api.js';
  import { playDropSound, playWinSound } from '../lib/sound.js';
  import Board from './Board.svelte';
  import StatusBanner from './StatusBanner.svelte';
  import MoveHistory from './MoveHistory.svelte';

  const PRIZE_SESSION_KEY = 'connect4_active_prize_session';

  let { username = '', onSaveUsername = () => {}, onGoHome = () => {} } = $props();

  let prizeConfig = $state(null);
  let game = $state(null);
  let isLoading = $state(true);
  let isThinking = $state(false);
  let error = $state(null);
  let wsConnected = $state(false);

  let nameInput = $state('');
  let nameError = $state(null);
  let savingName = $state(false);

  let resumePromptGame = $state(null);
  let resumeBusy = $state(false);
  let confirmAction = $state(null); // { title, description, confirmLabel, onConfirm }
  let confirmBusy = $state(false);
  let endGameConfirmOpen = $state(false);
  let endingGame = $state(false);

  let activeController = null;
  let openingTimer = null;
  let socket = null;
  let wsReconnectTimer = null;

  let canInteract = $derived(
    Boolean(
      game &&
        !resumePromptGame &&
        !confirmAction &&
        !endGameConfirmOpen &&
        game.status === 'playing' &&
        !isThinking &&
        !isLoading &&
        game.players?.[String(game.current_player)]?.type === 'human'
    )
  );

  let humanWon = $derived(
    Boolean(game && game.status === 'win' && game.winner === game.config?.human_player)
  );

  let isGameInProgress = $derived(
    Boolean(game && game.status === 'playing' && (game.move_history?.length || 0) > 0)
  );

  $effect(() => {
    if (typeof window === 'undefined' || !game) return;
    if (game.status === 'playing' && (game.move_history?.length || 0) > 0) {
      localStorage.setItem(PRIZE_SESSION_KEY, game.session_id);
    } else {
      const stored = localStorage.getItem(PRIZE_SESSION_KEY);
      if (!stored || stored === game.session_id) {
        localStorage.removeItem(PRIZE_SESSION_KEY);
      }
    }
  });

  function handleBeforeUnload(event) {
    if (isGameInProgress) {
      event.preventDefault();
      event.returnValue = '';
    }
  }

  function closeSocket() {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
      socket = null;
    }
    wsConnected = false;
  }

  function connectGameSocket(sessionId) {
    closeSocket();
    if (!sessionId) return;

    const ws = new WebSocket(getGameWsUrl(sessionId));
    socket = ws;

    ws.onopen = () => {
      wsConnected = true;
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'init' || msg.event === 'game_update') {
          const prevPlies = game?.move_history?.length ?? 0;
          const next = msg.data;
          game = next;
          if (next.move_history.length > prevPlies && next.last_move) {
            playDropSound(next.last_move.row);
          }
          if (next.status === 'win' && next.move_history.length > prevPlies) {
            playWinSound();
          }
        } else if (msg.event === 'ai_thinking') {
          isThinking = Boolean(msg.data);
        } else if (msg.event === 'error') {
          error = msg.data?.detail || 'Erreur de jeu.';
          isThinking = false;
        }
      } catch {
        // ignore
      }
    };

    ws.onclose = () => {
      wsConnected = false;
      if (socket === ws) {
        socket = null;
        wsReconnectTimer = setTimeout(() => {
          if (game?.session_id === sessionId) {
            connectGameSocket(sessionId);
          }
        }, 2500);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  function cancelPending() {
    if (openingTimer) {
      clearTimeout(openingTimer);
      openingTimer = null;
    }
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
    isLoading = false;
    isThinking = false;
  }

  async function loadConfig() {
    try {
      prizeConfig = await getWinAPrizeConfig();
    } catch (err) {
      error = err.message || 'Impossible de charger la configuration du défi.';
    }
  }

  async function startPrizeGame(playerName) {
    cancelPending();
    closeSocket();
    error = null;
    nameError = null;
    isLoading = true;
    const controller = new AbortController();
    activeController = controller;

    try {
      await loadConfig();
      if (prizeConfig && !prizeConfig.enabled) {
        isLoading = false;
        return;
      }
      const state = await createWinAPrizeGame(playerName, controller.signal);
      if (activeController !== controller) return;
      game = state;
      isLoading = false;
      connectGameSocket(state.session_id);

      if (
        state.status === 'playing' &&
        state.players?.[String(state.current_player)]?.type === 'ai'
      ) {
        openingTimer = setTimeout(() => {
          openingTimer = null;
          if (game?.session_id === state.session_id && game?.status === 'playing') {
            triggerAiReply();
          }
        }, 280);
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 403) {
        nameError = err.message;
        game = null;
      } else {
        error = err.message || 'Impossible de lancer la partie.';
      }
      isLoading = false;
    }
  }

  async function triggerAiReply() {
    if (!game || game.status !== 'playing' || isThinking) return;

    if (socket && socket.readyState === WebSocket.OPEN) {
      isThinking = true;
      socket.send(JSON.stringify({ type: 'ai_move' }));
      return;
    }

    isThinking = true;
    const controller = new AbortController();
    activeController = controller;
    try {
      const updated = await stepAiMove(game.session_id, controller.signal);
      if (activeController !== controller) return;
      game = updated;
      if (updated.last_move) playDropSound(updated.last_move.row);
      if (updated.status === 'win') playWinSound();
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      error = err.message || "Erreur lors du coup de l'IA.";
    } finally {
      if (activeController === controller) isThinking = false;
    }
  }

  async function handlePlayColumn(col) {
    if (!canInteract || !game) return;
    error = null;

    // Envoi direct par WebSocket pour une réactivité maximale
    if (socket && socket.readyState === WebSocket.OPEN) {
      isThinking = true;
      socket.send(JSON.stringify({ type: 'human_move', col, auto_ai_reply: true }));
      return;
    }

    // Repli HTTP si le WebSocket n'est pas encore ouvert
    isThinking = true;
    const controller = new AbortController();
    activeController = controller;

    try {
      const afterHuman = await playHumanMove(game.session_id, col, false, controller.signal);
      if (activeController !== controller) return;
      game = afterHuman;
      if (afterHuman.last_move) playDropSound(afterHuman.last_move.row);
      if (afterHuman.status === 'win') {
        playWinSound();
        return;
      }

      if (
        afterHuman.status === 'playing' &&
        afterHuman.players?.[String(afterHuman.current_player)]?.type === 'ai'
      ) {
        const afterAi = await stepAiMove(afterHuman.session_id, controller.signal);
        if (activeController !== controller) return;
        game = afterAi;
        if (afterAi.last_move) playDropSound(afterAi.last_move.row);
        if (afterAi.status === 'win') playWinSound();
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      error = err.message || 'Impossible de jouer ce coup.';
    } finally {
      if (activeController === controller) {
        isThinking = false;
      }
    }
  }

  async function handleUndo() {
    if (!game || !game.can_undo || isThinking) return;
    error = null;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'undo' }));
      return;
    }
    const controller = new AbortController();
    activeController = controller;
    try {
      const updated = await undoMove(game.session_id, controller.signal);
      if (activeController !== controller) return;
      game = updated;
    } catch (err) {
      if (err.name === 'AbortError') return;
      error = err.message || "Impossible d'annuler le coup.";
    }
  }

  async function handleNameSubmit(event) {
    event.preventDefault();
    if (savingName) return;
    const cleaned = nameInput.trim().slice(0, 32);
    if (!cleaned) return;
    savingName = true;
    nameError = null;
    try {
      await checkUsername(cleaned);
      onSaveUsername(cleaned);
      await startPrizeGame(cleaned);
    } catch (err) {
      nameError = err.message || "Ce pseudo n'est pas autorisé. Veuillez en choisir un autre.";
    } finally {
      savingName = false;
    }
  }

  function requestWithAbandonConfirm(title, description, confirmLabel, actionFn) {
    if (isGameInProgress) {
      confirmAction = { title, description, confirmLabel, onConfirm: actionFn };
      return;
    }
    actionFn();
  }

  async function handleConfirmAbandon() {
    if (!confirmAction || confirmBusy) return;
    confirmBusy = true;
    const { onConfirm } = confirmAction;
    const oldId = game?.session_id;
    try {
      if (oldId) {
        await forfeitGame(oldId, 'abandon_restart');
      }
    } catch {
      // ignore
    } finally {
      localStorage.removeItem(PRIZE_SESSION_KEY);
      confirmAction = null;
      confirmBusy = false;
    }
    await onConfirm();
  }

  async function handleConfirmEndGame() {
    if (!game || endingGame) return;
    endingGame = true;
    cancelPending();
    error = null;
    try {
      const ended = await forfeitGame(game.session_id, 'manual_end');
      game = ended;
      localStorage.removeItem(PRIZE_SESSION_KEY);
      endGameConfirmOpen = false;
    } catch (err) {
      error = err.message || 'Impossible de terminer la partie.';
      endGameConfirmOpen = false;
    } finally {
      endingGame = false;
    }
  }

  function handleResumeConfirm() {
    if (!resumePromptGame) return;
    const resumed = resumePromptGame;
    resumePromptGame = null;
    game = resumed;
    connectGameSocket(resumed.session_id);
    if (
      resumed.status === 'playing' &&
      resumed.players?.[String(resumed.current_player)]?.type === 'ai'
    ) {
      triggerAiReply();
    }
  }

  async function handleResumeDecline() {
    if (!resumePromptGame || resumeBusy) return;
    resumeBusy = true;
    const oldId = resumePromptGame.session_id;
    try {
      await forfeitGame(oldId, 'accidental_exit');
    } catch {
      // ignore
    } finally {
      localStorage.removeItem(PRIZE_SESSION_KEY);
      resumePromptGame = null;
      resumeBusy = false;
    }
    if (username && (!prizeConfig || prizeConfig.enabled)) {
      await startPrizeGame(username);
    }
  }

  onMount(async () => {
    window.addEventListener('beforeunload', handleBeforeUnload);
    nameInput = username || '';
    await loadConfig();
    if (prizeConfig && !prizeConfig.enabled) {
      isLoading = false;
      return;
    }

    const savedSid = (localStorage.getItem(PRIZE_SESSION_KEY) || '').trim();
    if (savedSid) {
      try {
        const existing = await getGame(savedSid);
        if (
          existing &&
          existing.channel === 'winaprize' &&
          existing.status === 'playing' &&
          (existing.move_history?.length || 0) > 0
        ) {
          resumePromptGame = existing;
          isLoading = false;
          return;
        }
      } catch {
        // Expirée
      }
      localStorage.removeItem(PRIZE_SESSION_KEY);
    }

    if (username) {
      await startPrizeGame(username);
    } else {
      isLoading = false;
    }
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    }
    cancelPending();
    closeSocket();
  });
</script>

<div class="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
  <div class="mx-auto max-w-5xl space-y-5">
    <!-- En-tête épuré -->
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div
          class="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-400/30 bg-gradient-to-br from-indigo-500/25 to-slate-900 shadow-lg"
        >
          <div class="grid grid-cols-2 gap-1">
            <span class="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
            <span class="h-2.5 w-2.5 rounded-full bg-amber-400"></span>
            <span class="h-2.5 w-2.5 rounded-full bg-amber-400"></span>
            <span class="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
          </div>
        </div>
        <div>
          <h1 class="text-lg font-bold tracking-tight text-white sm:text-xl">
            {prizeConfig?.title || 'Défi Puissance 4'}
          </h1>
          <p class="text-xs text-slate-400">
            {prizeConfig?.subtitle || "Battez l'IA pour gagner un prix !"}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {#if game}
          <span
            class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium {wsConnected
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-slate-700 bg-slate-900 text-slate-400'}"
          >
            <span
              class="h-1.5 w-1.5 rounded-full {wsConnected ? 'animate-pulse bg-emerald-400' : 'bg-slate-500'}"
            ></span>
            {wsConnected ? 'Temps réel' : 'Connexion…'}
          </span>
        {/if}

        <button
          type="button"
          onclick={onGoHome}
          class="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
        >
          Mode normal
        </button>
      </div>
    </header>

    {#if prizeConfig && !prizeConfig.enabled}
      <div
        class="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 text-center shadow-2xl"
      >
        <h2 class="text-lg font-bold text-white">Défi actuellement fermé</h2>
        <p class="mt-2 text-sm text-slate-400">
          Ce défi spécial Puissance 4 est actuellement en pause. Revenez plus tard !
        </p>
        <button
          type="button"
          onclick={onGoHome}
          class="mt-5 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Jouer en mode normal
        </button>
      </div>
    {:else if !game && !isLoading}
      <div
        class="mx-auto mt-14 max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl"
      >
        <h2 class="text-base font-bold text-white">Entrez votre pseudo</h2>
        <p class="mt-1 text-xs text-slate-400">
          Indiquez votre pseudo pour démarrer le défi {prizeConfig?.rows || 6}×{prizeConfig?.cols ||
            7} (alignement {prizeConfig?.align || 4}).
        </p>

        {#if nameError}
          <div
            class="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200"
          >
            {nameError}
          </div>
        {/if}

        <form onsubmit={handleNameSubmit} class="mt-4 space-y-4">
          <input
            type="text"
            required
            maxlength="32"
            disabled={savingName}
            bind:value={nameInput}
            placeholder="Votre pseudo"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={savingName}
            class="w-full rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {savingName ? 'Vérification…' : 'Lancer le défi'}
          </button>
        </form>
      </div>
    {:else}
      {#if humanWon}
        <div
          class="rounded-2xl border border-emerald-400/50 bg-emerald-500/15 px-5 py-4 text-center shadow-lg"
        >
          <p class="text-base font-bold text-emerald-200">
            Félicitations, {game.username} ! Vous avez battu l'IA !
          </p>
          <p class="mt-1 font-mono text-xs text-emerald-300/90">
            Code de victoire vérifié : {game.session_id.slice(0, 8).toUpperCase()} · Enregistré
          </p>
        </div>
      {/if}

      <main class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_300px]">
        <section class="space-y-4">
          <StatusBanner
            {game}
            {isThinking}
            {error}
            hideAiLevel={true}
            onDismissError={() => (error = null)}
          />

          {#if isLoading && !game}
            <div
              class="flex h-96 items-center justify-center rounded-3xl border border-slate-800 bg-slate-900/50"
            >
              <div
                class="h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
              ></div>
            </div>
          {:else if game}
            <Board
              grid={game.grid}
              rows={game.config.rows}
              cols={game.config.cols}
              validColumns={game.valid_columns}
              currentPlayer={game.current_player}
              lastMove={game.last_move}
              winningCells={game.winning_cells}
              status={game.status}
              {canInteract}
              onPlayColumn={handlePlayColumn}
            />
          {/if}
        </section>

        <aside class="space-y-4">
          <div class="flex flex-col gap-2 rounded-2xl border border-slate-800 bg-slate-900/70 p-3.5">
            <button
              type="button"
              onclick={() =>
                requestWithAbandonConfirm(
                  'Relancer le défi ?',
                  'Une partie de défi est déjà entamée. Rejouer maintenant enregistrera la partie en cours comme un forfait (abandon).',
                  'Abandonner et rejouer',
                  () => startPrizeGame(game?.username || nameInput || username)
                )}
              disabled={isLoading || isThinking}
              class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-indigo-500 disabled:opacity-50"
            >
              Rejouer
            </button>

            {#if isGameInProgress}
              <button
                type="button"
                onclick={() => (endGameConfirmOpen = true)}
                disabled={isThinking}
                class="w-full rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20 disabled:opacity-40"
              >
                Fin de partie (Enregistrer)
              </button>
            {/if}

            {#if game?.allow_undo}
              <button
                type="button"
                onclick={handleUndo}
                disabled={!game?.can_undo || isThinking}
                class="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-40"
              >
                Annuler le coup
              </button>
            {/if}

            {#if !isGameInProgress}
              <button
                type="button"
                onclick={() => {
                  cancelPending();
                  closeSocket();
                  game = null;
                  nameInput = username || '';
                }}
                class="w-full rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200"
              >
                Changer de pseudo
              </button>
            {/if}
          </div>

          <MoveHistory moves={game?.move_history || []} />
        </aside>
      </main>
    {/if}
  </div>

  {#if resumePromptGame}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-indigo-500/40 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">Défi interrompu détecté</h2>
        <p class="mt-2 text-xs leading-relaxed text-slate-300">
          Vous avez quitté un défi en cours ({resumePromptGame.move_history.length} coups joués).
          Voulez-vous reprendre la partie ? Si vous cliquez sur <strong class="text-rose-300">Non</strong>,
          elle sera enregistrée comme <strong class="text-rose-300">Forfait (Sortie involontaire)</strong>.
        </p>
        <div class="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={resumeBusy}
            onclick={handleResumeDecline}
            class="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-500/20 disabled:opacity-50"
          >
            {resumeBusy ? 'Enregistrement…' : 'Non (Forfait)'}
          </button>
          <button
            type="button"
            disabled={resumeBusy}
            onclick={handleResumeConfirm}
            class="rounded-xl bg-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-50"
          >
            Oui, reprendre
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if confirmAction}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-amber-500/45 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-amber-200">{confirmAction.title}</h2>
        <p class="mt-3 rounded-xl border border-amber-500/25 bg-amber-950/30 p-3 text-xs leading-relaxed text-amber-100">
          {confirmAction.description}
        </p>
        <div class="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={confirmBusy}
            onclick={() => (confirmAction = null)}
            class="rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            Continuer la partie
          </button>
          <button
            type="button"
            disabled={confirmBusy}
            onclick={handleConfirmAbandon}
            class="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-rose-500 disabled:opacity-50"
          >
            {confirmBusy ? 'Enregistrement…' : confirmAction.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if endGameConfirmOpen}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-amber-500/40 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">Terminer et enregistrer le défi ?</h2>
        <p class="mt-2 text-xs leading-relaxed text-slate-300">
          Cette partie ({game?.move_history?.length || 0} coups) sera clôturée et sauvegardée dans
          l'historique en tant que <strong class="text-amber-300">Fin manuelle</strong>.
        </p>
        <div class="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={endingGame}
            onclick={() => (endGameConfirmOpen = false)}
            class="rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            Annuler
          </button>
          <button
            type="button"
            disabled={endingGame}
            onclick={handleConfirmEndGame}
            class="rounded-xl bg-amber-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-amber-500 disabled:opacity-50"
          >
            {endingGame ? 'Enregistrement…' : 'Confirmer'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
