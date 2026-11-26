<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    createGame,
    playHumanMove,
    resetGame,
    stepAiMove,
    undoMove,
  } from './lib/api.js';
  import { formatLevel } from './lib/levels.js';
  import Board from './components/Board.svelte';
  import StatusBanner from './components/StatusBanner.svelte';
  import GameControls from './components/GameControls.svelte';
  import MoveHistory from './components/MoveHistory.svelte';
  import AiInspector from './components/AiInspector.svelte';
  import GameSettingsModal from './components/GameSettingsModal.svelte';
  import AdminPanel from './components/AdminPanel.svelte';

  const USERNAME_STORAGE_KEY = 'connect4_username';

  const DEFAULT_CONFIG = {
    rows: 6,
    cols: 7,
    align: 4,
    mode: 'human_vs_ai',
    starting_player: 1,
    human_player: 1,
    ai_level: 'medium',
    ai2_level: 'medium',
    username: 'Guest',
    player2_name: 'Player 2',
    random_start: false,
  };

  function detectAdminRoute() {
    if (typeof window === 'undefined') return false;
    return (
      window.location.pathname.replace(/\/+$/, '') === '/admin' ||
      window.location.hash === '#/admin'
    );
  }

  let isAdminView = $state(detectAdminRoute());

  let username = $state('');
  let usernameDraft = $state('');
  let showUsernameModal = $state(false);

  let game = $state(null);
  let isLoading = $state(false);
  let isThinking = $state(false);
  let error = $state(null);
  let settingsOpen = $state(false);
  let showInspector = $state(true);

  let isAutoPlaying = $state(false);
  let autoSpeedMs = $state(550);

  let activeController = null;
  let autoPlayTimer = null;
  let openingAiTimer = null;

  let canHumanInteract = $derived(
    Boolean(
      !isAdminView &&
        !settingsOpen &&
        !showUsernameModal &&
        game &&
        game.status === 'playing' &&
        !isThinking &&
        !isLoading &&
        game.players?.[String(game.current_player)]?.type === 'human'
    )
  );

  let settingsConfig = $derived(
    game?.config ?? { ...DEFAULT_CONFIG, username: username || 'Guest' }
  );

  function cancelPendingWork() {
    isAutoPlaying = false;
    if (autoPlayTimer) {
      clearTimeout(autoPlayTimer);
      autoPlayTimer = null;
    }
    if (openingAiTimer) {
      clearTimeout(openingAiTimer);
      openingAiTimer = null;
    }
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
    isLoading = false;
    isThinking = false;
  }

  function syncViewState(admin) {
    isAdminView = admin;
    if (admin) {
      cancelPendingWork();
      showUsernameModal = false;
      settingsOpen = false;
      return;
    }
    if (!username) {
      showUsernameModal = true;
    } else if (!game && !isLoading) {
      initSession({ ...DEFAULT_CONFIG, username });
    }
  }

  function navigateTo(admin) {
    const targetPath = admin ? '/admin' : '/';
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath);
    }
    syncViewState(admin);
  }

  function handlePopState() {
    syncViewState(detectAdminRoute());
  }

  async function initSession(config = DEFAULT_CONFIG) {
    cancelPendingWork();
    error = null;
    isLoading = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const state = await createGame({ ...config, auto_play_opening_ai: false }, signal);
      if (activeController !== controller) return;
      game = state;
      isLoading = false;
      maybeTriggerOpeningHumanVsAiMove(state);
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      error = err.message || 'Could not reach Connect 4 backend.';
      isLoading = false;
    }
  }

  function maybeTriggerOpeningHumanVsAiMove(state) {
    if (openingAiTimer) {
      clearTimeout(openingAiTimer);
      openingAiTimer = null;
    }
    if (
      state &&
      state.config.mode === 'human_vs_ai' &&
      state.status === 'playing' &&
      state.players?.[String(state.current_player)]?.type === 'ai'
    ) {
      const targetSessionId = state.session_id;
      const targetUpdatedAt = state.updated_at;
      openingAiTimer = setTimeout(() => {
        openingAiTimer = null;
        if (
          !isAdminView &&
          game?.session_id === targetSessionId &&
          game?.updated_at === targetUpdatedAt &&
          game?.status === 'playing' &&
          game?.players?.[String(game.current_player)]?.type === 'ai'
        ) {
          runAiStep();
        }
      }, 280);
    }
  }

  async function handlePlayColumn(col) {
    if (!canHumanInteract || !game) return;
    error = null;
    isThinking = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const afterHuman = await playHumanMove(game.session_id, col, false, signal);
      if (activeController !== controller) return;
      game = afterHuman;

      if (
        afterHuman.status === 'playing' &&
        afterHuman.players?.[String(afterHuman.current_player)]?.type === 'ai'
      ) {
        const afterAi = await stepAiMove(afterHuman.session_id, signal);
        if (activeController !== controller) return;
        game = afterAi;
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Guest' };
        error = 'Your session expired after a server restart. Started a fresh game.';
        await initSession(cfg);
        return;
      }
      error = err.message || 'Failed to play move.';
    } finally {
      if (activeController === controller) {
        isThinking = false;
      }
    }
  }

  async function runAiStep() {
    if (!game || game.status !== 'playing' || isThinking) return;
    if (game.players?.[String(game.current_player)]?.type !== 'ai') return;

    error = null;
    isThinking = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const updated = await stepAiMove(game.session_id, signal);
      if (activeController !== controller) return;
      game = updated;
      if (updated.status !== 'playing') {
        isAutoPlaying = false;
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      isAutoPlaying = false;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Guest' };
        error = 'Your session expired after a server restart. Started a fresh game.';
        await initSession(cfg);
        return;
      }
      error = err.message || 'AI move failed.';
    } finally {
      if (activeController === controller) {
        isThinking = false;
      }
    }
  }

  function scheduleNextAutoStep() {
    if (autoPlayTimer) {
      clearTimeout(autoPlayTimer);
      autoPlayTimer = null;
    }
    if (!isAutoPlaying || !game || game.status !== 'playing') {
      isAutoPlaying = false;
      return;
    }
    autoPlayTimer = setTimeout(async () => {
      autoPlayTimer = null;
      if (!isAutoPlaying) return;
      await runAiStep();
      if (isAutoPlaying && game?.status === 'playing') {
        scheduleNextAutoStep();
      }
    }, autoSpeedMs);
  }

  function handleToggleAutoPlay() {
    if (!game || game.status !== 'playing') return;
    if (isAutoPlaying) {
      isAutoPlaying = false;
      if (autoPlayTimer) {
        clearTimeout(autoPlayTimer);
        autoPlayTimer = null;
      }
    } else {
      isAutoPlaying = true;
      runAiStep().then(() => {
        if (isAutoPlaying && game?.status === 'playing') {
          scheduleNextAutoStep();
        }
      });
    }
  }

  async function handleNewGame(overrides = {}) {
    cancelPendingWork();
    error = null;

    const currentCfg = game?.config || DEFAULT_CONFIG;
    const baseCfg = {
      rows: currentCfg.rows,
      cols: currentCfg.cols,
      align: currentCfg.align,
      mode: currentCfg.mode,
      starting_player: currentCfg.starting_player,
      human_player: currentCfg.human_player,
      ai_level: currentCfg.ai_level,
      ai2_level: currentCfg.ai2_level,
      username: username || 'Guest',
      player2_name: currentCfg.player2_name || 'Player 2',
      random_start: false,
      ...overrides,
    };

    if (!game) {
      return initSession(baseCfg);
    }

    isLoading = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const state = await resetGame(
        game.session_id,
        { ...overrides, username: baseCfg.username, auto_play_opening_ai: false },
        signal
      );
      if (activeController !== controller) return;
      game = state;
      isLoading = false;
      maybeTriggerOpeningHumanVsAiMove(state);
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        return initSession(baseCfg);
      }
      error = err.message || 'Failed to reset game.';
      isLoading = false;
    }
  }

  function handleRandomStart() {
    handleNewGame({ starting_player: 'random', random_start: true });
  }

  function handleSwitchMode(newMode) {
    if (game?.config?.mode === newMode) return;
    handleNewGame({ mode: newMode, starting_player: 1, random_start: false });
  }

  function handleQuickLevel(newLevel) {
    if (game?.config?.ai_level === newLevel) return;
    handleNewGame({ ai_level: newLevel, ai2_level: newLevel });
  }

  async function handleUndo() {
    if (!game || !game.can_undo || isThinking) return;
    cancelPendingWork();
    error = null;
    const controller = new AbortController();
    activeController = controller;
    try {
      const state = await undoMove(game.session_id, controller.signal);
      if (activeController !== controller) return;
      game = state;
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Guest' };
        error = 'Your session expired after a server restart. Started a fresh game.';
        await initSession(cfg);
        return;
      }
      error = err.message || 'Could not undo move.';
    }
  }

  function handleApplySettings(newConfig) {
    settingsOpen = false;
    if (newConfig.username && newConfig.username !== username) {
      username = newConfig.username;
      localStorage.setItem(USERNAME_STORAGE_KEY, username);
    }
    handleNewGame(newConfig);
  }

  function handleSaveUsername(event) {
    event.preventDefault();
    const cleaned = usernameDraft.trim().slice(0, 32);
    if (!cleaned) return;
    const changed = cleaned !== username;
    username = cleaned;
    localStorage.setItem(USERNAME_STORAGE_KEY, cleaned);
    showUsernameModal = false;
    if (!game) {
      initSession({ ...DEFAULT_CONFIG, username: cleaned });
    } else if (changed) {
      handleNewGame({ username: cleaned });
    }
  }

  function formatModeLabel(mode) {
    if (mode === 'player_vs_player') return 'Player vs Player';
    if (mode === 'ai_vs_ai') return 'AI vs AI';
    return 'Human vs AI';
  }

  onMount(() => {
    window.addEventListener('popstate', handlePopState);
    const savedUser = (localStorage.getItem(USERNAME_STORAGE_KEY) || '').trim();
    if (savedUser) {
      username = savedUser;
      usernameDraft = savedUser;
      if (!isAdminView) {
        initSession({ ...DEFAULT_CONFIG, username: savedUser });
      }
    } else if (!isAdminView) {
      showUsernameModal = true;
    }
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('popstate', handlePopState);
    }
    cancelPendingWork();
  });
</script>

{#if isAdminView}
  <AdminPanel onBackToGame={() => navigateTo(false)} />
{:else}
  <div class="min-h-screen px-4 py-5 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-6xl space-y-5">
      <!-- Header -->
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
              Connect 4 <span class="font-normal text-indigo-400">· WeakC4 AI</span>
            </h1>
            <p class="text-xs text-slate-400">
              {#if game}
                {game.config.rows}×{game.config.cols} · Connect {game.config.align} ·
                {formatModeLabel(game.config.mode)}
                {#if game.config.mode !== 'player_vs_player'}
                  · {formatLevel(game.config.ai_level)}
                {/if}
              {:else}
                Ready to play
              {/if}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          {#if username}
            <button
              type="button"
              onclick={() => {
                usernameDraft = username;
                showUsernameModal = true;
              }}
              class="inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:text-white"
              title="Change username"
            >
              <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
              <span>{username}</span>
              <span class="text-[10px] text-slate-500">Edit</span>
            </button>
          {/if}

          <button
            type="button"
            onclick={() => navigateTo(true)}
            class="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
          >
            Admin
          </button>
        </div>
      </header>

      <!-- Main Layout -->
      <main class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_340px]">
        <!-- Left: Status Banner + Board -->
        <section class="space-y-4">
          <StatusBanner {game} {isThinking} {error} onDismissError={() => (error = null)} />

          {#if isLoading && !game}
            <div
              class="flex h-96 items-center justify-center rounded-3xl border border-slate-800 bg-slate-900/50"
            >
              <div class="flex flex-col items-center gap-3 text-slate-400">
                <div
                  class="h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
                ></div>
                <span class="text-sm">Starting Connect 4 session…</span>
              </div>
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
              canInteract={canHumanInteract}
              onPlayColumn={handlePlayColumn}
            />
          {/if}
        </section>

        <!-- Right Sidebar: Controls + AI Inspector + History -->
        <aside class="space-y-4">
          <GameControls
            {game}
            {isThinking}
            {isAutoPlaying}
            {autoSpeedMs}
            {showInspector}
            onNewGame={() =>
              handleNewGame({
                starting_player: game?.config?.random_start
                  ? 1
                  : game?.config?.starting_player || 1,
                random_start: false,
              })}
            onRandomStart={handleRandomStart}
            onSwitchMode={handleSwitchMode}
            onQuickLevel={handleQuickLevel}
            onUndo={handleUndo}
            onOpenSettings={() => (settingsOpen = true)}
            onToggleInspector={() => (showInspector = !showInspector)}
            onStepAi={runAiStep}
            onToggleAutoPlay={handleToggleAutoPlay}
            onChangeSpeed={(ms) => (autoSpeedMs = ms)}
          />

          {#if showInspector && game?.config?.mode !== 'player_vs_player'}
            <AiInspector aiInfo={game?.ai_info || null} config={game?.config || null} />
          {/if}

          <MoveHistory moves={game?.move_history || []} />
        </aside>
      </main>
    </div>
  </div>

  <!-- Username Welcome / Edit Modal -->
  {#if showUsernameModal}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">
          {username ? 'Change Username' : 'Welcome to Connect 4'}
        </h2>
        <p class="mt-1 text-xs text-slate-400">
          Enter your username to start playing. Your live game will be tagged with this name.
        </p>

        <form onsubmit={handleSaveUsername} class="mt-4 space-y-4">
          <input
            type="text"
            required
            maxlength="32"
            bind:value={usernameDraft}
            placeholder="e.g. Ayoube"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
          />

          <div class="flex items-center justify-between gap-2">
            {#if !username}
              <button
                type="button"
                onclick={() => navigateTo(true)}
                class="text-xs font-medium text-slate-500 hover:text-slate-300"
              >
                Admin login
              </button>
            {:else}
              <span></span>
            {/if}

            <div class="flex items-center gap-2">
              {#if username}
                <button
                  type="button"
                  onclick={() => (showUsernameModal = false)}
                  class="rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
              {/if}
              <button
                type="submit"
                class="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500"
              >
                {username ? 'Save' : 'Start Playing'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <GameSettingsModal
    open={settingsOpen}
    config={settingsConfig}
    onClose={() => (settingsOpen = false)}
    onApply={handleApplySettings}
  />
{/if}
