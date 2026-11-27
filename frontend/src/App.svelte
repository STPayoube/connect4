<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    checkUsername,
    createGame,
    forfeitGame,
    getGame,
    getGameWsUrl,
    playHumanMove,
    resetGame,
    stepAiMove,
    undoMove,
  } from './lib/api.js';
  import { formatLevel } from './lib/levels.js';
  import {
    isSoundEnabled,
    playDropSound,
    playWinSound,
    setSoundEnabled,
  } from './lib/sound.js';
  import Board from './components/Board.svelte';
  import StatusBanner from './components/StatusBanner.svelte';
  import GameControls from './components/GameControls.svelte';
  import MoveHistory from './components/MoveHistory.svelte';
  import AiInspector from './components/AiInspector.svelte';
  import GameSettingsModal from './components/GameSettingsModal.svelte';
  import AdminPanel from './components/AdminPanel.svelte';
  import PrizeGameView from './components/PrizeGameView.svelte';
  import OnlineRoomView from './components/OnlineRoomView.svelte';

  const USERNAME_STORAGE_KEY = 'connect4_username';
  const ACTIVE_SESSION_KEY = 'connect4_active_session';

  const DEFAULT_CONFIG = {
    rows: 6,
    cols: 7,
    align: 4,
    mode: 'human_vs_ai',
    starting_player: 1,
    human_player: 1,
    ai_level: 'medium',
    ai2_level: 'medium',
    username: 'Invité',
    player2_name: 'Joueur 2',
    random_start: false,
  };

  function detectRoute() {
    if (typeof window === 'undefined') return { view: 'normal', roomCode: '' };
    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    const hash = window.location.hash || '';

    if (path === '/admin' || hash === '#/admin') {
      return { view: 'admin', roomCode: '' };
    }
    if (path === '/winaprize') {
      return { view: 'winaprize', roomCode: '' };
    }
    if (path === '/game') {
      const code = hash.replace(/^#/, '').trim().toUpperCase();
      return { view: 'room', roomCode: code };
    }
    return { view: 'normal', roomCode: '' };
  }

  const initialRoute = detectRoute();
  let activeView = $state(initialRoute.view);
  let roomCode = $state(initialRoute.roomCode);

  let username = $state('');
  let usernameDraft = $state('');
  let usernameError = $state(null);
  let savingUsername = $state(false);
  let showUsernameModal = $state(false);
  let soundOn = $state(isSoundEnabled());

  let game = $state(null);
  let isLoading = $state(false);
  let isThinking = $state(false);
  let error = $state(null);
  let settingsOpen = $state(false);
  let settingsError = $state(null);
  let savingSettings = $state(false);
  let showInspector = $state(true);

  let resumePromptGame = $state(null);
  let resumeBusy = $state(false);
  let restartConfirm = $state(null);
  let restartBusy = $state(false);
  let endGameConfirmOpen = $state(false);
  let endingGame = $state(false);

  let isAutoPlaying = $state(false);
  let autoSpeedMs = $state(550);

  let activeController = null;
  let autoPlayTimer = null;
  let openingAiTimer = null;
  let gameSocket = null;
  let wsReconnectTimer = null;

  let canHumanInteract = $derived(
    Boolean(
      activeView === 'normal' &&
        !settingsOpen &&
        !showUsernameModal &&
        !resumePromptGame &&
        !restartConfirm &&
        !endGameConfirmOpen &&
        game &&
        game.status === 'playing' &&
        !isThinking &&
        !isLoading &&
        game.players?.[String(game.current_player)]?.type === 'human'
    )
  );

  let settingsConfig = $derived(
    game?.config ?? { ...DEFAULT_CONFIG, username: username || 'Invité' }
  );

  $effect(() => {
    if (typeof window === 'undefined' || activeView !== 'normal' || !game) return;
    if (
      game.channel === 'normal' &&
      game.status === 'playing' &&
      (game.move_history?.length || 0) > 0
    ) {
      localStorage.setItem(ACTIVE_SESSION_KEY, game.session_id);
    } else if (game.status !== 'playing' || (game.move_history?.length || 0) === 0) {
      const stored = localStorage.getItem(ACTIVE_SESSION_KEY);
      if (!stored || stored === game.session_id) {
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      }
    }
  });

  function isGameInProgress() {
    return Boolean(game && game.status === 'playing' && (game.move_history?.length || 0) > 0);
  }

  let canChangeUsername = $derived(
    !game || game.status !== 'playing' || (game.move_history?.length || 0) === 0
  );

  function handleBeforeUnload(event) {
    if (activeView === 'normal' && isGameInProgress()) {
      event.preventDefault();
      event.returnValue = '';
    }
  }

  function closeGameSocket() {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    if (gameSocket) {
      gameSocket.onclose = null;
      gameSocket.onerror = null;
      gameSocket.close();
      gameSocket = null;
    }
  }

  function connectGameSocket(sessionId) {
    closeGameSocket();
    if (!sessionId || activeView !== 'normal') return;

    const ws = new WebSocket(getGameWsUrl(sessionId));
    gameSocket = ws;

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
          if (next.status !== 'playing') {
            isAutoPlaying = false;
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
      if (gameSocket !== ws) return;
      gameSocket = null;
      wsReconnectTimer = setTimeout(() => {
        if (activeView === 'normal' && game?.session_id === sessionId) {
          connectGameSocket(sessionId);
        }
      }, 2500);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

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

  function applyRoute(nextView, nextRoomCode = '') {
    activeView = nextView;
    roomCode = nextRoomCode;

    if (nextView !== 'normal') {
      cancelPendingWork();
      closeGameSocket();
      showUsernameModal = false;
      settingsOpen = false;
      return;
    }
    if (!username) {
      showUsernameModal = true;
    } else if (!game && !resumePromptGame && !isLoading) {
      checkSavedSessionOrStart(username);
    } else if (game?.session_id && !gameSocket) {
      connectGameSocket(game.session_id);
    }
  }

  function navigateTo(view, code = '') {
    let targetUrl = '/';
    if (view === 'admin') targetUrl = '/admin';
    else if (view === 'winaprize') targetUrl = '/winaprize';
    else if (view === 'room') targetUrl = code ? `/game#${code}` : '/game';

    const currentFull = `${window.location.pathname}${window.location.hash}`;
    if (currentFull !== targetUrl) {
      window.history.pushState({}, '', targetUrl);
    }
    applyRoute(view, code);
  }

  function handleUrlChange() {
    const r = detectRoute();
    applyRoute(r.view, r.roomCode);
  }

  function toggleSound() {
    soundOn = !soundOn;
    setSoundEnabled(soundOn);
  }

  async function initSession(config = DEFAULT_CONFIG) {
    cancelPendingWork();
    closeGameSocket();
    error = null;
    usernameError = null;
    isLoading = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const state = await createGame({ ...config, auto_play_opening_ai: false }, signal);
      if (activeController !== controller) return;
      game = state;
      isLoading = false;
      connectGameSocket(state.session_id);
      maybeTriggerOpeningHumanVsAiMove(state);
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      isLoading = false;
      if (err.status === 403) {
        usernameError = err.message;
        usernameDraft = username;
        showUsernameModal = true;
      } else {
        error = err.message || 'Impossible de joindre le serveur Puissance 4.';
      }
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
          activeView === 'normal' &&
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

    if (gameSocket && gameSocket.readyState === WebSocket.OPEN) {
      if (game.config.mode === 'human_vs_ai') {
        isThinking = true;
      }
      gameSocket.send(
        JSON.stringify({
          type: 'human_move',
          col,
          auto_ai_reply: game.config.mode === 'human_vs_ai',
        })
      );
      return;
    }

    isThinking = true;
    const controller = new AbortController();
    activeController = controller;
    const signal = controller.signal;

    try {
      const afterHuman = await playHumanMove(game.session_id, col, false, signal);
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
        const afterAi = await stepAiMove(afterHuman.session_id, signal);
        if (activeController !== controller) return;
        game = afterAi;
        if (afterAi.last_move) playDropSound(afterAi.last_move.row);
        if (afterAi.status === 'win') playWinSound();
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Invité' };
        error = 'Votre session a expiré après une mise à jour. Nouvelle partie lancée.';
        await initSession(cfg);
        return;
      }
      error = err.message || 'Impossible de jouer ce coup.';
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
      if (updated.last_move) playDropSound(updated.last_move.row);
      if (updated.status === 'win') playWinSound();
      if (updated.status !== 'playing') {
        isAutoPlaying = false;
      }
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      isAutoPlaying = false;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Invité' };
        error = 'Votre session a expiré après une mise à jour. Nouvelle partie lancée.';
        await initSession(cfg);
        return;
      }
      error = err.message || "Échec du coup de l'IA.";
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
      username: username || 'Invité',
      player2_name: currentCfg.player2_name || 'Joueur 2',
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
      if (!gameSocket) connectGameSocket(state.session_id);
      maybeTriggerOpeningHumanVsAiMove(state);
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        return initSession(baseCfg);
      }
      if (err.status === 403) {
        usernameError = err.message;
        showUsernameModal = true;
      } else {
        error = err.message || 'Impossible de réinitialiser la partie.';
      }
      isLoading = false;
    }
  }

  function buildNextConfig(overrides = {}) {
    const currentCfg = game?.config || DEFAULT_CONFIG;
    return {
      rows: currentCfg.rows,
      cols: currentCfg.cols,
      align: currentCfg.align,
      mode: currentCfg.mode,
      starting_player: currentCfg.starting_player,
      human_player: currentCfg.human_player,
      ai_level: currentCfg.ai_level,
      ai2_level: currentCfg.ai2_level,
      username: username || 'Invité',
      player2_name: currentCfg.player2_name || 'Joueur 2',
      random_start: false,
      ...overrides,
    };
  }

  function requestRestartWithConfirm(title, description, overrides = {}) {
    if (isGameInProgress()) {
      restartConfirm = {
        title,
        description,
        overrides,
      };
      return;
    }
    handleNewGame(overrides);
  }

  async function handleConfirmRestart() {
    if (!restartConfirm || restartBusy) return;
    restartBusy = true;
    const { overrides } = restartConfirm;
    const nextCfg = buildNextConfig(overrides);
    const oldSessionId = game?.session_id;
    try {
      if (oldSessionId) {
        await forfeitGame(oldSessionId, 'abandon_restart');
      }
    } catch {
      // Peut déjà être terminée ou expirée
    } finally {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      restartConfirm = null;
      restartBusy = false;
    }
    await initSession(nextCfg);
  }

  async function handleConfirmEndGame() {
    if (!game || endingGame) return;
    endingGame = true;
    cancelPendingWork();
    error = null;
    try {
      const ended = await forfeitGame(game.session_id, 'manual_end');
      game = ended;
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      endGameConfirmOpen = false;
    } catch (err) {
      error = err.message || 'Impossible de terminer la partie.';
      endGameConfirmOpen = false;
    } finally {
      endingGame = false;
    }
  }

  async function checkSavedSessionOrStart(savedUser) {
    const savedSid = (localStorage.getItem(ACTIVE_SESSION_KEY) || '').trim();
    if (savedSid) {
      isLoading = true;
      try {
        const existing = await getGame(savedSid);
        if (
          existing &&
          existing.channel === 'normal' &&
          existing.status === 'playing' &&
          (existing.move_history?.length || 0) > 0
        ) {
          isLoading = false;
          resumePromptGame = existing;
          return;
        }
      } catch {
        // Session expirée ou introuvable
      }
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      isLoading = false;
    }
    await initSession({ ...DEFAULT_CONFIG, username: savedUser });
  }

  function handleResumeConfirm() {
    if (!resumePromptGame) return;
    const resumed = resumePromptGame;
    resumePromptGame = null;
    game = resumed;
    connectGameSocket(resumed.session_id);
    maybeTriggerOpeningHumanVsAiMove(resumed);
  }

  async function handleResumeDecline() {
    if (!resumePromptGame || resumeBusy) return;
    resumeBusy = true;
    const abandonedId = resumePromptGame.session_id;
    try {
      await forfeitGame(abandonedId, 'accidental_exit');
    } catch {
      // Déjà expirée
    } finally {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      resumePromptGame = null;
      resumeBusy = false;
    }
    await initSession({ ...DEFAULT_CONFIG, username: username || 'Invité' });
  }

  function handleRandomStart() {
    requestRestartWithConfirm(
      'Relancer avec tirage au sort ?',
      'Une partie est déjà entamée. Relancer maintenant enregistrera la partie en cours comme un forfait (abandon).',
      { starting_player: 'random', random_start: true }
    );
  }

  function handleSwitchMode(newMode) {
    if (game?.config?.mode === newMode) return;
    requestRestartWithConfirm(
      'Changer de mode de jeu ?',
      'Une partie est déjà entamée. Changer de mode enregistrera la partie actuelle comme un forfait (abandon).',
      { mode: newMode, starting_player: 1, random_start: false }
    );
  }

  function handleQuickLevel(newLevel) {
    if (!game || game.status !== 'playing') return;
    if (game.config.ai_level === newLevel) return;
    requestRestartWithConfirm(
      'Changer la difficulté ?',
      "Une partie est déjà entamée. Changer le niveau de l'IA enregistrera la partie actuelle comme un forfait (abandon) et en démarrera une nouvelle.",
      { ai_level: newLevel, ai2_level: newLevel }
    );
  }

  async function handleUndo() {
    if (!game || !game.can_undo || isThinking) return;
    cancelPendingWork();
    error = null;
    if (gameSocket && gameSocket.readyState === WebSocket.OPEN) {
      gameSocket.send(JSON.stringify({ type: 'undo' }));
      return;
    }
    const controller = new AbortController();
    activeController = controller;
    try {
      const state = await undoMove(game.session_id, controller.signal);
      if (activeController !== controller) return;
      game = state;
    } catch (err) {
      if (err.name === 'AbortError' || activeController !== controller) return;
      if (err.status === 404) {
        const cfg = { ...(game?.config || DEFAULT_CONFIG), username: username || 'Invité' };
        error = 'Votre session a expiré après une mise à jour. Nouvelle partie lancée.';
        await initSession(cfg);
        return;
      }
      error = err.message || "Impossible d'annuler le coup.";
    }
  }

  async function handleApplySettings(newConfig) {
    if (savingSettings) return;
    savingSettings = true;
    settingsError = null;
    try {
      const effectiveUser = canChangeUsername
        ? (newConfig.username || '').trim().slice(0, 32)
        : username || 'Invité';
      if (!effectiveUser) {
        settingsError = 'Veuillez saisir un pseudo valide.';
        return;
      }
      await checkUsername(effectiveUser);
      if (newConfig.mode === 'player_vs_player' && newConfig.player2_name) {
        await checkUsername(newConfig.player2_name.trim().slice(0, 32));
      }
      if (canChangeUsername) {
        persistUsername(effectiveUser);
      }
      settingsOpen = false;
      requestRestartWithConfirm(
        'Appliquer les nouveaux paramètres ?',
        'Une partie est déjà entamée. Lancer une nouvelle partie avec ces paramètres enregistrera la partie actuelle comme un forfait (abandon).',
        { ...newConfig, username: effectiveUser }
      );
    } catch (err) {
      settingsError = err.message || "Ce pseudo n'est pas autorisé.";
    } finally {
      savingSettings = false;
    }
  }

  function persistUsername(cleaned) {
    username = cleaned;
    usernameDraft = cleaned;
    localStorage.setItem(USERNAME_STORAGE_KEY, cleaned);
  }

  async function handleSaveUsername(event) {
    event.preventDefault();
    if (savingUsername) return;
    const cleaned = usernameDraft.trim().slice(0, 32);
    if (!cleaned) return;
    if (!canChangeUsername && cleaned !== username) {
      usernameError = 'Impossible de changer de pseudo pendant une partie en cours.';
      return;
    }

    savingUsername = true;
    usernameError = null;
    try {
      await checkUsername(cleaned);
      const changed = cleaned !== username;
      persistUsername(cleaned);
      showUsernameModal = false;
      if (!game && !resumePromptGame) {
        checkSavedSessionOrStart(cleaned);
      } else if (changed && game) {
        handleNewGame({ username: cleaned });
      }
    } catch (err) {
      usernameError = err.message || "Ce pseudo n'est pas autorisé. Veuillez en choisir un autre.";
    } finally {
      savingUsername = false;
    }
  }

  function formatModeLabel(mode) {
    if (mode === 'player_vs_player') return 'Joueur vs Joueur';
    if (mode === 'ai_vs_ai') return 'IA vs IA';
    return "Contre l'IA";
  }

  onMount(() => {
    window.addEventListener('popstate', handleUrlChange);
    window.addEventListener('hashchange', handleUrlChange);
    window.addEventListener('beforeunload', handleBeforeUnload);
    const savedUser = (localStorage.getItem(USERNAME_STORAGE_KEY) || '').trim();
    if (savedUser) {
      username = savedUser;
      usernameDraft = savedUser;
      if (activeView === 'normal') {
        checkSavedSessionOrStart(savedUser);
      }
    } else if (activeView === 'normal') {
      showUsernameModal = true;
    }
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('popstate', handleUrlChange);
      window.removeEventListener('hashchange', handleUrlChange);
      window.removeEventListener('beforeunload', handleBeforeUnload);
    }
    cancelPendingWork();
    closeGameSocket();
  });
</script>

{#if activeView === 'admin'}
  <AdminPanel onBackToGame={() => navigateTo('normal')} />
{:else if activeView === 'winaprize'}
  <PrizeGameView onGoHome={() => navigateTo('normal')} />
{:else if activeView === 'room'}
  <OnlineRoomView
    initialCode={roomCode}
    {username}
    onSaveUsername={persistUsername}
    onBackHome={() => navigateTo('normal')}
    onRoomCodeChange={(code) => {
      roomCode = code;
      window.history.replaceState({}, '', `/game#${code}`);
    }}
  />
{:else}
  <div class="min-h-screen px-4 py-5 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-6xl space-y-5">
      <!-- En-tête -->
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
              Puissance 4 <span class="font-normal text-indigo-400">· WeakC4 IA</span>
            </h1>
            <p class="text-xs text-slate-400">
              {#if game}
                {game.config.rows}×{game.config.cols} · Alignement {game.config.align} ·
                {formatModeLabel(game.config.mode)}
                {#if game.config.mode !== 'player_vs_player'}
                  · {formatLevel(game.config.ai_level)}
                {/if}
              {:else}
                Prêt à jouer
              {/if}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            onclick={toggleSound}
            class="rounded-full border border-slate-800 bg-slate-900/70 px-2.5 py-1.5 text-xs text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
            title={soundOn ? 'Couper les sons' : 'Activer les sons'}
          >
            {soundOn ? '🔊' : '🔇'}
          </button>

          {#if username}
            {#if canChangeUsername}
              <button
                type="button"
                onclick={() => {
                  usernameDraft = username;
                  usernameError = null;
                  showUsernameModal = true;
                }}
                class="inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:text-white"
                title="Modifier le pseudo"
              >
                <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
                <span>{username}</span>
                <span class="text-[10px] text-slate-500">Modifier</span>
              </button>
            {:else}
              <span
                class="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-300"
                title="Impossible de changer de pseudo pendant une partie en cours"
              >
                <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
                <span>{username}</span>
              </span>
            {/if}
          {/if}
        </div>
      </header>

      <!-- Contenu principal -->
      <main class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_340px]">
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
                <span class="text-sm">Démarrage de la partie…</span>
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

        <aside class="space-y-4">
          <GameControls
            {game}
            {isThinking}
            {isAutoPlaying}
            {autoSpeedMs}
            {showInspector}
            onNewGame={() =>
              requestRestartWithConfirm(
                'Recommencer une nouvelle partie ?',
                'Une partie est déjà entamée. Lancer une nouvelle partie enregistrera celle-ci comme un forfait (abandon).',
                {
                  starting_player: game?.config?.random_start
                    ? 1
                    : game?.config?.starting_player || 1,
                  random_start: false,
                }
              )}
            onRandomStart={handleRandomStart}
            onEndGame={() => (endGameConfirmOpen = true)}
            onPlayWithFriend={() => navigateTo('room', '')}
            onSwitchMode={handleSwitchMode}
            onQuickLevel={handleQuickLevel}
            onUndo={handleUndo}
            onOpenSettings={() => {
              settingsError = null;
              settingsOpen = true;
            }}
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

  <!-- Modale Bienvenue / Pseudo -->
  {#if showUsernameModal}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">
          {username && !usernameError ? 'Modifier votre pseudo' : 'Bienvenue sur Puissance 4'}
        </h2>
        <p class="mt-1 text-xs text-slate-400">
          Entrez votre pseudo pour commencer à jouer. Votre partie sera associée à ce nom.
        </p>

        {#if usernameError}
          <div
            class="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200"
          >
            {usernameError}
          </div>
        {/if}

        <form onsubmit={handleSaveUsername} class="mt-4 space-y-4">
          <input
            type="text"
            required
            maxlength="32"
            disabled={savingUsername}
            bind:value={usernameDraft}
            placeholder="ex. Ayoube"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
          />

          <div class="flex items-center justify-end gap-2">
            {#if username && !usernameError}
              <button
                type="button"
                disabled={savingUsername}
                onclick={() => (showUsernameModal = false)}
                class="rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                Annuler
              </button>
            {/if}
            <button
              type="submit"
              disabled={savingUsername}
              class="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingUsername
                ? 'Vérification…'
                : username && !usernameError
                  ? 'Enregistrer'
                  : 'Commencer à jouer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- Pop-up Reprendre une partie interrompue -->
  {#if resumePromptGame}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-indigo-500/40 bg-slate-900 p-6 shadow-2xl">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-300">
            ⏸
          </div>
          <div>
            <h2 class="text-base font-bold text-white">Partie interrompue détectée</h2>
            <p class="text-xs text-slate-400">
              Vous avez quitté une partie en cours ({resumePromptGame.move_history.length} coups joués ·
              {resumePromptGame.config.rows}×{resumePromptGame.config.cols}).
            </p>
          </div>
        </div>

        <p class="mt-4 rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs leading-relaxed text-slate-300">
          Souhaitez-vous reprendre cette partie là où vous l'avez laissée ? Si vous cliquez sur
          <strong class="text-rose-300">Non</strong>, elle sera enregistrée comme
          <strong class="text-rose-300">Forfait (Sortie involontaire)</strong>.
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
            Oui, reprendre la partie
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Pop-up Avertissement avant de relancer une partie déjà commencée -->
  {#if restartConfirm}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-amber-500/45 bg-slate-900 p-6 shadow-2xl">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-300">
            ⚠️
          </div>
          <div>
            <h2 class="text-base font-bold text-amber-200">{restartConfirm.title}</h2>
            <p class="text-xs text-slate-400">Partie en cours ({game?.move_history?.length || 0} coups joués)</p>
          </div>
        </div>

        <p class="mt-4 rounded-xl border border-amber-500/25 bg-amber-950/30 p-3 text-xs leading-relaxed text-amber-100">
          {restartConfirm.description}
        </p>

        <div class="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={restartBusy}
            onclick={() => (restartConfirm = null)}
            class="rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            Continuer la partie
          </button>
          <button
            type="button"
            disabled={restartBusy}
            onclick={handleConfirmRestart}
            class="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-rose-500 disabled:opacity-50"
          >
            {restartBusy ? 'Enregistrement…' : 'Abandonner et relancer'}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Pop-up Confirmation Fin de partie -->
  {#if endGameConfirmOpen}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-amber-500/40 bg-slate-900 p-6 shadow-2xl">
        <h2 class="text-base font-bold text-white">Terminer et enregistrer la partie ?</h2>
        <p class="mt-2 text-xs leading-relaxed text-slate-300">
          La partie en cours ({game?.move_history?.length || 0} coups) sera clôturée et sauvegardée dans
          l'historique en tant que <strong class="text-amber-300">Fin manuelle</strong> au lieu de rester active.
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
            {endingGame ? 'Enregistrement…' : 'Confirmer la fin de partie'}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <GameSettingsModal
    open={settingsOpen}
    config={settingsConfig}
    error={settingsError}
    saving={savingSettings}
    lockUsername={!canChangeUsername}
    onClose={() => {
      settingsError = null;
      settingsOpen = false;
    }}
    onApply={handleApplySettings}
  />
{/if}
