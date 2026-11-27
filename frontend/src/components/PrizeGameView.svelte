<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    createWinAPrizeGame,
    getWinAPrizeConfig,
    playHumanMove,
    stepAiMove,
    undoMove,
  } from '../lib/api.js';
  import { playDropSound, playWinSound } from '../lib/sound.js';
  import Board from './Board.svelte';
  import StatusBanner from './StatusBanner.svelte';
  import MoveHistory from './MoveHistory.svelte';

  let { username = '', onSaveUsername = () => {}, onGoHome = () => {} } = $props();

  let prizeConfig = $state(null);
  let game = $state(null);
  let isLoading = $state(true);
  let isThinking = $state(false);
  let error = $state(null);

  let nameInput = $state('');
  let nameError = $state(null);

  let activeController = null;
  let openingTimer = null;

  let canInteract = $derived(
    Boolean(
      game &&
        game.status === 'playing' &&
        !isThinking &&
        !isLoading &&
        game.players?.[String(game.current_player)]?.type === 'human'
    )
  );

  let humanWon = $derived(
    Boolean(game && game.status === 'win' && game.winner === game.config?.human_player)
  );

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
      error = err.message || 'Could not load challenge configuration.';
    }
  }

  async function startPrizeGame(playerName) {
    cancelPending();
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
        error = err.message || 'Could not start game.';
      }
      isLoading = false;
    }
  }

  async function triggerAiReply() {
    if (!game || game.status !== 'playing' || isThinking) return;
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
      error = err.message || 'AI move failed.';
    } finally {
      if (activeController === controller) {
        isThinking = false;
      }
    }
  }

  async function handlePlayColumn(col) {
    if (!canInteract || !game) return;
    error = null;
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
      error = err.message || 'Failed to play move.';
    } finally {
      if (activeController === controller) {
        isThinking = false;
      }
    }
  }

  async function handleUndo() {
    if (!game || !game.can_undo || isThinking) return;
    cancelPending();
    error = null;
    const controller = new AbortController();
    activeController = controller;
    try {
      const updated = await undoMove(game.session_id, controller.signal);
      if (activeController !== controller) return;
      game = updated;
    } catch (err) {
      if (err.name === 'AbortError') return;
      error = err.message || 'Could not undo move.';
    }
  }

  function handleNameSubmit(event) {
    event.preventDefault();
    const cleaned = nameInput.trim().slice(0, 32);
    if (!cleaned) return;
    onSaveUsername(cleaned);
    startPrizeGame(cleaned);
  }

  onMount(async () => {
    nameInput = username || '';
    await loadConfig();
    if (username && (!prizeConfig || prizeConfig.enabled)) {
      await startPrizeGame(username);
    } else {
      isLoading = false;
    }
  });

  onDestroy(() => {
    cancelPending();
  });
</script>

<div class="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
  <div class="mx-auto max-w-5xl space-y-5">
    <!-- Minimal Clean Header -->
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
            {prizeConfig?.title || 'Connect 4 Challenge'}
          </h1>
          <p class="text-xs text-slate-400">
            {prizeConfig?.subtitle || 'Beat the AI to win a prize!'}
          </p>
        </div>
      </div>

      <button
        type="button"
        onclick={onGoHome}
        class="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
      >
        Normal Mode
      </button>
    </header>

    {#if prizeConfig && !prizeConfig.enabled}
      <div
        class="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 text-center shadow-2xl"
      >
        <h2 class="text-lg font-bold text-white">Challenge Currently Closed</h2>
        <p class="mt-2 text-sm text-slate-400">
          This special Connect 4 challenge is paused right now. Please check back later!
        </p>
        <button
          type="button"
          onclick={onGoHome}
          class="mt-5 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Play Normal Connect 4
        </button>
      </div>
    {:else if !game && !isLoading}
      <div
        class="mx-auto mt-14 max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl"
      >
        <h2 class="text-base font-bold text-white">Enter Your Username</h2>
        <p class="mt-1 text-xs text-slate-400">
          Enter your name to begin the {prizeConfig?.rows || 6}×{prizeConfig?.cols || 7} Connect
          {prizeConfig?.align || 4} challenge.
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
            bind:value={nameInput}
            placeholder="Your username"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            class="w-full rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500"
          >
            Start Challenge
          </button>
        </form>
      </div>
    {:else}
      {#if humanWon}
        <div
          class="rounded-2xl border border-emerald-400/50 bg-emerald-500/15 px-5 py-4 text-center shadow-lg"
        >
          <p class="text-base font-bold text-emerald-200">
            Congratulations, {game.username}! You beat the AI!
          </p>
          <p class="mt-1 font-mono text-xs text-emerald-300/90">
            Verified Result ID: {game.session_id.slice(0, 8).toUpperCase()} · Saved to leaderboard
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
              onclick={() => startPrizeGame(game?.username || nameInput || username)}
              disabled={isLoading || isThinking}
              class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-indigo-500 disabled:opacity-50"
            >
              Play Again
            </button>

            {#if game?.allow_undo}
              <button
                type="button"
                onclick={handleUndo}
                disabled={!game?.can_undo || isThinking}
                class="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-40"
              >
                Undo
              </button>
            {/if}

            <button
              type="button"
              onclick={() => {
                cancelPending();
                game = null;
                nameInput = username || '';
              }}
              class="w-full rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200"
            >
              Change Username
            </button>
          </div>

          <MoveHistory moves={game?.move_history || []} />
        </aside>
      </main>
    {/if}
  </div>
</div>
