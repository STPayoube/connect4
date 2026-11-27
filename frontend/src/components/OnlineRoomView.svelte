<script>
  import { onDestroy, onMount } from 'svelte';
  import QRCode from 'qrcode';
  import {
    createRoom,
    getRoom,
    getRoomStreamUrl,
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
  let seat = $state(0); // 1 = P1, 2 = P2, 0 = Spectator
  let playerToken = $state('');
  let qrDataUrl = $state('');
  let copied = $state(false);
  let streamConnected = $state(false);

  let isLoading = $state(true);
  let isSending = $state(false);
  let error = $state(null);

  let nameInput = $state('');
  let needsName = $state(false);

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

  function closeStream() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    streamConnected = false;
  }

  async function generateQr(url) {
    if (!url) return;
    try {
      qrDataUrl = await QRCode.toDataURL(url, {
        width: 240,
        margin: 2,
        color: {
          dark: '#0f172a',
          light: '#ffffff',
        },
      });
    } catch {
      qrDataUrl = '';
    }
  }

  function connectRoomStream(code) {
    closeStream();
    const es = new EventSource(getRoomStreamUrl(code));
    eventSource = es;

    const handleState = (evt) => {
      try {
        const next = JSON.parse(evt.data);
        const prevPlies = game?.move_history?.length ?? 0;
        game = next;
        streamConnected = true;
        if (next.move_history.length > prevPlies && next.last_move) {
          playDropSound(next.last_move.row);
        }
        if (next.status === 'win' && prevPlies < next.move_history.length) {
          playWinSound();
        }
      } catch {
        // ignore parse error
      }
    };

    es.addEventListener('init', handleState);
    es.addEventListener('room_update', handleState);
    es.onopen = () => {
      streamConnected = true;
    };
    es.onerror = () => {
      streamConnected = false;
      es.close();
      eventSource = null;
      reconnectTimer = setTimeout(() => {
        if (roomCode === code) connectRoomStream(code);
      }, 2500);
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
      connectRoomStream(roomCode);
      isLoading = false;
    } catch (err) {
      error = err.message || 'Could not create online room.';
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

    // Restore seat if this browser tab already created or joined this room
    const savedToken = sessionStorage.getItem(tokenStorageKey(cleanCode));
    const savedSeat = Number(sessionStorage.getItem(seatStorageKey(cleanCode)) || '0');
    if (savedToken && (savedSeat === 1 || savedSeat === 2)) {
      try {
        const current = await getRoom(cleanCode);
        game = current;
        playerToken = savedToken;
        seat = savedSeat;
        await generateQr(`${window.location.origin}/game#${cleanCode}`);
        connectRoomStream(cleanCode);
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
      connectRoomStream(roomCode);
      isLoading = false;
    } catch (err) {
      error = err.message || `Could not join room #${cleanCode}.`;
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
    try {
      const updated = await playRoomMove(roomCode, col, playerToken);
      game = updated;
    } catch (err) {
      error = err.message || 'Move rejected.';
    } finally {
      isSending = false;
    }
  }

  async function handleRematch(randomStart = false) {
    if (!roomCode || !playerToken || seat === 0) return;
    error = null;
    try {
      game = await rematchRoom(roomCode, playerToken, randomStart);
    } catch (err) {
      error = err.message || 'Could not start rematch.';
    }
  }

  async function copyShareLink() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      // fallback ignored
    }
  }

  function handleNameSubmit(event) {
    event.preventDefault();
    const cleaned = nameInput.trim().slice(0, 32);
    if (!cleaned) return;
    needsName = false;
    onSaveUsername(cleaned);
    if (initialCode) {
      enterExistingRoom(initialCode, cleaned);
    } else {
      hostNewRoom(cleaned);
    }
  }

  onMount(() => {
    nameInput = username || '';
    const cleanInit = (initialCode || '').trim().toUpperCase().replace(/^#/, '');

    // If re-entering own room from sessionStorage, skip name prompt
    if (cleanInit && sessionStorage.getItem(tokenStorageKey(cleanInit))) {
      enterExistingRoom(cleanInit, username || 'Player');
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
    closeStream();
  });
</script>

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
            Online Friend Match
            {#if roomCode}
              <span class="ml-1 font-mono text-indigo-400">#{roomCode}</span>
            {/if}
          </h1>
          <p class="text-xs text-slate-400">
            {#if seat === 1}
              You are Player 1 (Coral Red)
            {:else if seat === 2}
              You are Player 2 (Amber Gold)
            {:else if game}
              Spectating Live
            {:else}
              Play Connect 4 with a friend on any device
            {/if}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {#if roomCode}
          <span
            class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium {streamConnected
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}"
          >
            <span
              class="h-1.5 w-1.5 rounded-full {streamConnected
                ? 'animate-pulse bg-emerald-400'
                : 'bg-amber-400'}"
            ></span>
            {streamConnected ? 'Live Sync' : 'Connecting…'}
          </span>
        {/if}

        <button
          type="button"
          onclick={onBackHome}
          class="rounded-full border border-slate-700 bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
        >
          ← Back to Lobby
        </button>
      </div>
    </header>

    {#if needsName}
      <div
        class="mx-auto mt-14 max-w-sm rounded-2xl border border-slate-700/80 bg-slate-900 p-6 shadow-2xl"
      >
        <h2 class="text-base font-bold text-white">
          {initialCode ? `Join Room #${initialCode.toUpperCase()}` : 'Create Friend Room'}
        </h2>
        <p class="mt-1 text-xs text-slate-400">
          Enter your username to {initialCode ? 'join your friend’s game' : 'generate an invite QR code'}.
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
            bind:value={nameInput}
            placeholder="Your username"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            class="w-full rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500"
          >
            {initialCode ? 'Join Match' : 'Create Room & QR Code'}
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
          <span class="text-sm">Setting up room…</span>
        </div>
      </div>
    {:else if !game}
      <div
        class="mx-auto mt-12 max-w-md rounded-2xl border border-rose-500/30 bg-slate-900/80 p-6 text-center"
      >
        <h2 class="text-base font-bold text-rose-200">Room Unavailable</h2>
        <p class="mt-2 text-xs text-slate-400">{error || 'This room link has expired.'}</p>
        <button
          type="button"
          onclick={() => hostNewRoom(username || nameInput || 'Player')}
          class="mt-4 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500"
        >
          Create New Room
        </button>
      </div>
    {:else}
      <main class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_340px]">
        <!-- Left: Board & Status -->
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
                Waiting for your friend to scan the QR code or open the link…
              </div>
              <p class="mt-1 text-xs text-slate-400">
                The game will begin automatically the moment they join.
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

        <!-- Right Sidebar: QR Invite Card + Rematch + Move History -->
        <aside class="space-y-4">
          <!-- QR Code & Share Invite Card -->
          <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <div class="flex items-center justify-between">
              <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Invite a Friend
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
                    alt="QR code to join room #{roomCode}"
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
                {copied ? 'Copied Invite Link!' : 'Copy Invite Link'}
              </button>
            </div>
          </div>

          <!-- Rematch Controls -->
          {#if !game.waiting_for_opponent && seat > 0 && game.status !== 'playing'}
            <div class="grid grid-cols-2 gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-3">
              <button
                type="button"
                onclick={() => handleRematch(false)}
                class="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
              >
                Rematch
              </button>
              <button
                type="button"
                onclick={() => handleRematch(true)}
                class="rounded-xl border border-emerald-400/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
              >
                Random Rematch
              </button>
            </div>
          {/if}

          <MoveHistory moves={game.move_history} />
        </aside>
      </main>
    {/if}
  </div>
</div>
