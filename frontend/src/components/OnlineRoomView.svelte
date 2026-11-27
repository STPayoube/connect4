<script>
  import { onDestroy, onMount } from 'svelte';
  import QRCode from 'qrcode';
  import {
    checkUsername,
    createRoom,
    getRoom,
    getRoomStreamUrl,
    getRoomWsUrl,
    joinRoom,
    playRoomMove,
    rematchRoom,
  } from '../lib/api.js';
  import { playDropSound, playWinSound } from '../lib/sound.js';
  import Board from './Board.svelte';
  import StatusBanner from './StatusBanner.svelte';
  import MoveHistory from './MoveHistory.svelte';

  let {
    initialCode = '',
    username = '',
    onSaveUsername = () => {},
    onBackHome = () => {},
    onRoomCodeChange = () => {},
  } = $props();

  let roomCode = $state('');
  let game = $state(null);
  let seat = $state(0); // 1 = J1, 2 = J2, 0 = Spectateur
  let playerToken = $state('');
  let qrDataUrl = $state('');
  let copied = $state(false);
  let connMode = $state('connecting'); // connecting | ws | sse | offline

  let isLoading = $state(true);
  let isSending = $state(false);
  let error = $state(null);

  let nameInput = $state('');
  let needsName = $state(false);
  let savingName = $state(false);

  let socket = null;
  let eventSource = null;
  let reconnectTimer = null;

  let shareUrl = $derived(
    roomCode && typeof window !== 'undefined'
      ? `${window.location.origin}/game#${roomCode}`
      : ''
  );

  let canPlay = $derived(
    Boolean(
      game &&
        !game.waiting_for_opponent &&
        game.status === 'playing' &&
        !isSending &&
        seat > 0 &&
        game.current_player === seat
    )
  );

  function tokenStorageKey(code) {
    return `connect4_room_token_${code}`;
  }

  function seatStorageKey(code) {
    return `connect4_room_seat_${code}`;
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

  function applyIncomingState(next) {
    const prevPlies = game?.move_history?.length ?? 0;
    game = next;
    isSending = false;
    if (next.move_history.length > prevPlies && next.last_move) {
      playDropSound(next.last_move.row);
    }
    if (next.status === 'win' && prevPlies < next.move_history.length) {
      playWinSound();
    }
  }

  async function generateQr(url) {
    if (!url) return;
    try {
      qrDataUrl = await QRCode.toDataURL(url, {
        width: 240,
        margin: 2,
        color: { dark: '#0f172a', light: '#ffffff' },
      });
    } catch {
      qrDataUrl = '';
    }
  }

  function connectRoomSseFallback(code) {
    if (eventSource) eventSource.close();
    const es = new EventSource(getRoomStreamUrl(code));
    eventSource = es;

    const handleEvt = (evt) => {
      try {
        applyIncomingState(JSON.parse(evt.data));
        connMode = 'sse';
      } catch {
        // ignore
      }
    };

    es.addEventListener('init', handleEvt);
    es.addEventListener('room_update', handleEvt);
    es.onopen = () => {
      connMode = 'sse';
    };
    es.onerror = () => {
      es.close();
      eventSource = null;
      connMode = 'offline';
      reconnectTimer = setTimeout(() => {
        if (roomCode === code) connectRoomSocket(code);
      }, 2500);
    };
  }

  function connectRoomSocket(code) {
    closeConnections();
    connMode = 'connecting';
    let openedOnce = false;

    const ws = new WebSocket(getRoomWsUrl(code));
    socket = ws;

    ws.onopen = () => {
      openedOnce = true;
      connMode = 'ws';
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'init' || msg.event === 'room_update') {
          applyIncomingState(msg.data);
          connMode = 'ws';
        } else if (msg.event === 'error') {
          error = msg.data?.detail || 'Coup refusé.';
          isSending = false;
        }
      } catch {
        // ignore
      }
    };

    ws.onclose = () => {
      if (socket !== ws) return;
      socket = null;
      if (!openedOnce) {
        // Repli automatique SSE si le reverse-proxy ne gère pas encore Upgrade WS
        connectRoomSseFallback(code);
      } else {
        connMode = 'offline';
        reconnectTimer = setTimeout(() => {
          if (roomCode === code) connectRoomSocket(code);
        }, 2000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  async function hostNewRoom(playerName) {
    isLoading = true;
    error = null;
    try {
      const res = await createRoom({
        username: playerName,
        rows: 6,
        cols: 7,
        align: 4,
        starting_player: 1,
        random_start: false,
      });
      roomCode = res.room_code;
      seat = res.seat;
      playerToken = res.player_token || '';
      game = res.game;

      sessionStorage.setItem(tokenStorageKey(roomCode), playerToken);
      sessionStorage.setItem(seatStorageKey(roomCode), String(seat));
      onRoomCodeChange(roomCode);

      await generateQr(`${window.location.origin}/game#${roomCode}`);
      connectRoomSocket(roomCode);
      isLoading = false;
    } catch (err) {
      error = err.message || 'Impossible de créer le salon en ligne.';
      if (err.status === 403) {
        needsName = true;
      }
      isLoading = false;
    }
  }

  async function enterExistingRoom(code, playerName) {
    const cleanCode = code.trim().toUpperCase().replace(/^#/, '');
    roomCode = cleanCode;
    isLoading = true;
    error = null;

    const savedToken = sessionStorage.getItem(tokenStorageKey(cleanCode));
    const savedSeat = Number(sessionStorage.getItem(seatStorageKey(cleanCode)) || '0');
    if (savedToken && (savedSeat === 1 || savedSeat === 2)) {
      try {
        const current = await getRoom(cleanCode);
        game = current;
        playerToken = savedToken;
        seat = savedSeat;
        await generateQr(`${window.location.origin}/game#${cleanCode}`);
        connectRoomSocket(cleanCode);
        isLoading = false;
        return;
      } catch {
        sessionStorage.removeItem(tokenStorageKey(cleanCode));
        sessionStorage.removeItem(seatStorageKey(cleanCode));
      }
    }

    try {
      const res = await joinRoom(cleanCode, playerName);
      roomCode = res.room_code;
      seat = res.seat;
      playerToken = res.player_token || '';
      game = res.game;
      if (playerToken && seat > 0) {
        sessionStorage.setItem(tokenStorageKey(roomCode), playerToken);
        sessionStorage.setItem(seatStorageKey(roomCode), String(seat));
      }
      await generateQr(`${window.location.origin}/game#${roomCode}`);
      connectRoomSocket(roomCode);
      isLoading = false;
    } catch (err) {
      error = err.message || `Impossible de rejoindre le salon #${cleanCode}.`;
      if (err.status === 403) {
        needsName = true;
      }
      isLoading = false;
    }
  }

  async function handlePlayColumn(col) {
    if (!canPlay || !roomCode || !playerToken) return;
    isSending = true;
    error = null;

    // Envoi ultra-rapide par WebSocket si ouvert
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'move', col, player_token: playerToken }));
      return;
    }

    try {
      const updated = await playRoomMove(roomCode, col, playerToken);
      applyIncomingState(updated);
    } catch (err) {
      error = err.message || 'Coup refusé.';
      isSending = false;
    }
  }

  async function handleRematch(randomStart = false) {
    if (!roomCode || !playerToken || seat === 0) return;
    error = null;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({ type: 'rematch', player_token: playerToken, random_start: randomStart })
      );
      return;
    }
    try {
      game = await rematchRoom(roomCode, playerToken, randomStart);
    } catch (err) {
      error = err.message || 'Impossible de lancer la revanche.';
    }
  }

  async function copyShareLink() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      // ignore
    }
  }

  async function handleNameSubmit(event) {
    event.preventDefault();
    if (savingName) return;
    const cleaned = nameInput.trim().slice(0, 32);
    if (!cleaned) return;
    savingName = true;
    error = null;
    try {
      await checkUsername(cleaned);
      needsName = false;
      onSaveUsername(cleaned);
      if (initialCode) {
        enterExistingRoom(initialCode, cleaned);
      } else {
        hostNewRoom(cleaned);
      }
    } catch (err) {
      error = err.message || "Ce pseudo n'est pas autorisé. Veuillez en choisir un autre.";
    } finally {
      savingName = false;
    }
  }

  onMount(() => {
    nameInput = username || '';
    const cleanInit = (initialCode || '').trim().toUpperCase().replace(/^#/, '');

    if (cleanInit && sessionStorage.getItem(tokenStorageKey(cleanInit))) {
      enterExistingRoom(cleanInit, username || 'Joueur');
      return;
    }

    if (!username) {
      needsName = true;
      isLoading = false;
      return;
    }

    if (cleanInit) {
      enterExistingRoom(cleanInit, username);
    } else {
      hostNewRoom(username);
    }
  });

  onDestroy(() => {
    closeConnections();
  });
</script>

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
            Partie entre amis
            {#if roomCode}
              <span class="ml-1 font-mono text-indigo-400">#{roomCode}</span>
            {/if}
          </h1>
          <p class="text-xs text-slate-400">
            {#if seat === 1}
              Vous êtes Joueur 1
            {:else if seat === 2}
              Vous êtes Joueur 2
            {:else if game}
              Mode Spectateur en direct
            {:else}
              Jouez à Puissance 4 avec un ami sur deux appareils
            {/if}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {#if roomCode}
          <span
            class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium {connMode ===
              'ws' || connMode === 'sse'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}"
          >
            <span
              class="h-1.5 w-1.5 rounded-full {connMode === 'ws' || connMode === 'sse'
                ? 'animate-pulse bg-emerald-400'
                : 'bg-amber-400'}"
            ></span>
            {connMode === 'ws'
              ? 'WebSocket'
              : connMode === 'sse'
                ? 'Synchro directe'
                : 'Connexion…'}
          </span>
        {/if}

        <button
          type="button"
          onclick={onBackHome}
          class="rounded-full border border-slate-700 bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
        >
          ← Retour à l'accueil
        </button>
      </div>
    </header>

    {#if needsName}
      <div
        class="mx-auto mt-14 max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl"
      >
        <h2 class="text-base font-bold text-white">
          {initialCode ? `Rejoindre le salon #${initialCode.toUpperCase()}` : 'Créer un salon ami'}
        </h2>
        <p class="mt-1 text-xs text-slate-400">
          Entrez votre pseudo pour {initialCode
            ? 'rejoindre la partie de votre ami'
            : 'générer un QR code d’invitation'}.
        </p>

        {#if error}
          <div
            class="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200"
          >
            {error}
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
            {savingName
              ? 'Vérification…'
              : initialCode
                ? 'Rejoindre la partie'
                : 'Créer le salon & QR Code'}
          </button>
        </form>
      </div>
    {:else if isLoading}
      <div
        class="flex h-96 items-center justify-center rounded-3xl border border-slate-800 bg-slate-900/50"
      >
        <div class="flex flex-col items-center gap-3 text-slate-400">
          <div
            class="h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
          ></div>
          <span class="text-sm">Préparation du salon…</span>
        </div>
      </div>
    {:else if !game}
      <div
        class="mx-auto mt-12 max-w-md rounded-2xl border border-rose-500/30 bg-slate-900/80 p-6 text-center"
      >
        <h2 class="text-base font-bold text-rose-200">Salon introuvable</h2>
        <p class="mt-2 text-xs text-slate-400">{error || 'Ce lien de salon a expiré.'}</p>
        <button
          type="button"
          onclick={() => hostNewRoom(username || nameInput || 'Joueur')}
          class="mt-4 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500"
        >
          Créer un nouveau salon
        </button>
      </div>
    {:else}
      <main class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_340px]">
        <!-- Gauche : Grille & Statut -->
        <section class="space-y-4">
          <StatusBanner
            {game}
            isThinking={false}
            {error}
            onDismissError={() => (error = null)}
          />

          {#if game.waiting_for_opponent}
            <div
              class="rounded-2xl border border-indigo-500/40 bg-indigo-950/30 p-5 text-center"
            >
              <div class="inline-flex items-center gap-2 text-sm font-semibold text-indigo-200">
                <span class="h-2.5 w-2.5 animate-ping rounded-full bg-indigo-400"></span>
                En attente que votre ami scanne le QR code ou ouvre le lien…
              </div>
              <p class="mt-1 text-xs text-slate-400">
                La partie démarrera automatiquement dès qu'il rejoindra.
              </p>
            </div>
          {/if}

          <Board
            grid={game.grid}
            rows={game.config.rows}
            cols={game.config.cols}
            validColumns={game.valid_columns}
            currentPlayer={game.current_player}
            lastMove={game.last_move}
            winningCells={game.winning_cells}
            status={game.status}
            canInteract={canPlay}
            onPlayColumn={handlePlayColumn}
          />
        </section>

        <!-- Droite : QR Code + Revanche + Historique -->
        <aside class="space-y-4">
          <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <div class="flex items-center justify-between">
              <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Inviter un ami
              </h2>
              <span class="rounded bg-indigo-500/20 px-2 py-0.5 font-mono text-xs font-bold text-indigo-300">
                #{roomCode}
              </span>
            </div>

            {#if qrDataUrl}
              <div class="my-3 flex justify-center">
                <div class="rounded-2xl bg-white p-2.5 shadow-lg">
                  <img
                    src={qrDataUrl}
                    alt="QR code pour rejoindre le salon #{roomCode}"
                    class="h-44 w-44 rounded-lg"
                  />
                </div>
              </div>
            {/if}

            <div class="space-y-2">
              <div
                class="truncate rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 font-mono text-[11px] text-slate-300"
                title={shareUrl}
              >
                {shareUrl}
              </div>

              <button
                type="button"
                onclick={copyShareLink}
                class="w-full rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-500"
              >
                {copied ? 'Lien copié !' : "Copier le lien d'invitation"}
              </button>
            </div>
          </div>

          {#if !game.waiting_for_opponent && seat > 0 && game.status !== 'playing'}
            <div class="grid grid-cols-2 gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-3">
              <button
                type="button"
                onclick={() => handleRematch(false)}
                class="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
              >
                Revanche
              </button>
              <button
                type="button"
                onclick={() => handleRematch(true)}
                class="rounded-xl border border-emerald-400/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
              >
                Revanche aléatoire
              </button>
            </div>
          {/if}

          <MoveHistory moves={game.move_history} />
        </aside>
      </main>
    {/if}
  </div>
</div>
