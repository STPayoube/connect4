<script>
  import { onDestroy, onMount } from 'svelte';
  import QRCode from 'qrcode';
  import { getWinAPrizeLive, getWinAPrizeLiveWsUrl } from '../lib/api.js';

  let title = $state('Défi Puissance 4');
  let subtitle = $state("Battez l'IA pour gagner un prix !");
  let enabled = $state(true);
  let players = $state([]);
  let qrDataUrl = $state('');
  let copied = $state(false);
  let wsConnected = $state(false);
  let nowSec = $state(Date.now() / 1000);

  let socket = null;
  let reconnectTimer = null;
  let pollTimer = null;
  let clockTimer = null;

  let prizeUrl = $derived(
    typeof window !== 'undefined' ? `${window.location.origin}/winaprize` : '/winaprize'
  );

  function closeSocket() {
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
    wsConnected = false;
  }

  async function fetchSnapshot() {
    try {
      const data = await getWinAPrizeLive();
      title = data.title || 'Défi Puissance 4';
      subtitle = data.subtitle || "Battez l'IA pour gagner un prix !";
      enabled = data.enabled !== false;
      players = data.players || [];
    } catch {
      // ignore transient network errors
    }
  }

  function connectLiveSocket() {
    closeSocket();
    const ws = new WebSocket(getWinAPrizeLiveWsUrl());
    socket = ws;

    ws.onopen = () => {
      wsConnected = true;
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'init' && msg.data) {
          title = msg.data.title || 'Défi Puissance 4';
          subtitle = msg.data.subtitle || "Battez l'IA pour gagner un prix !";
          enabled = msg.data.enabled !== false;
          players = msg.data.players || [];
        } else if (msg.event === 'players_update') {
          players = Array.isArray(msg.data) ? msg.data : [];
        } else if (msg.event === 'config_update' && msg.data) {
          if (msg.data.title) title = msg.data.title;
          if (msg.data.subtitle) subtitle = msg.data.subtitle;
          if (typeof msg.data.enabled === 'boolean') enabled = msg.data.enabled;
        }
      } catch {
        // ignore
      }
    };

    ws.onclose = () => {
      wsConnected = false;
      if (socket === ws) {
        socket = null;
        reconnectTimer = setTimeout(() => {
          connectLiveSocket();
        }, 2500);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  async function copyLink() {
    if (!prizeUrl) return;
    try {
      await navigator.clipboard.writeText(prizeUrl);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      // ignore
    }
  }

  function formatDuration(p) {
    const endTs = p.status === 'playing' ? nowSec : p.updated_at || nowSec;
    const secs = Math.max(0, Math.floor(endTs - p.created_at));
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return `${String(mins).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
  }

  function formatPlayerLabel(p) {
    if (!p.username || p.username === 'Joueur') {
      return `Joueur #${p.short_id}`;
    }
    return p.username;
  }

  function statusLabel(p) {
    if (p.status === 'playing') return 'En cours';
    if (p.status === 'win') return p.human_won ? 'Victoire !' : 'Défaite';
    if (p.status === 'draw') return 'Match nul';
    return 'Terminée';
  }

  function statusClass(p) {
    if (p.status === 'playing') {
      return 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300';
    }
    if (p.status === 'win') {
      return p.human_won
        ? 'border-amber-400/50 bg-amber-500/20 text-amber-200'
        : 'border-rose-500/40 bg-rose-500/15 text-rose-300';
    }
    return 'border-slate-700 bg-slate-800 text-slate-300';
  }

  onMount(async () => {
    try {
      qrDataUrl = await QRCode.toDataURL(`${window.location.origin}/winaprize`, {
        width: 340,
        margin: 2,
        color: { dark: '#0f172a', light: '#ffffff' },
      });
    } catch {
      qrDataUrl = '';
    }

    await fetchSnapshot();
    connectLiveSocket();

    pollTimer = setInterval(() => {
      if (!wsConnected) fetchSnapshot();
    }, 4000);

    clockTimer = setInterval(() => {
      nowSec = Date.now() / 1000;
    }, 1000);
  });

  onDestroy(() => {
    closeSocket();
    if (pollTimer) clearInterval(pollTimer);
    if (clockTimer) clearInterval(clockTimer);
  });
</script>

<div class="flex min-h-screen items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
  <div class="grid w-full max-w-5xl grid-cols-1 items-stretch gap-6 lg:grid-cols-[400px_1fr]">
    <!-- Carte QR Code & Lien -->
    <section
      class="flex flex-col items-center justify-between rounded-3xl border border-slate-800 bg-slate-900/85 p-6 text-center shadow-2xl"
    >
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-white sm:text-2xl">{title}</h1>
        <p class="text-xs text-slate-400 sm:text-sm">{subtitle}</p>
      </div>

      <div class="my-6 flex flex-col items-center">
        {#if qrDataUrl}
          <div class="rounded-3xl bg-white p-4 shadow-[0_20px_50px_-15px_rgba(99,102,241,0.45)]">
            <img
              src={qrDataUrl}
              alt="QR code pour accéder à /winaprize"
              class="h-64 w-64 rounded-xl sm:h-72 sm:w-72"
            />
          </div>
        {:else}
          <div
            class="flex h-64 w-64 items-center justify-center rounded-3xl border border-slate-800 bg-slate-950"
          >
            <div
              class="h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
            ></div>
          </div>
        {/if}

        {#if !enabled}
          <span
            class="mt-3 rounded-full border border-rose-500/40 bg-rose-950/60 px-3 py-1 text-xs font-semibold text-rose-200"
          >
            Défi actuellement fermé
          </span>
        {/if}
      </div>

      <div class="w-full space-y-2.5">
        <a
          href={prizeUrl}
          class="block truncate rounded-xl border border-slate-800 bg-slate-950 px-3.5 py-2.5 font-mono text-xs text-indigo-300 transition hover:border-indigo-500/50 hover:text-indigo-200"
          title={prizeUrl}
        >
          {prizeUrl}
        </a>

        <button
          type="button"
          onclick={copyLink}
          class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-indigo-500 active:scale-[0.98]"
        >
          {copied ? 'Lien copié !' : 'Copier le lien'}
        </button>
      </div>
    </section>

    <!-- Liste des joueurs connectés en temps réel -->
    <section
      class="flex flex-col rounded-3xl border border-slate-800 bg-slate-900/85 p-6 shadow-2xl"
    >
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-4">
        <div class="flex items-center gap-2.5">
          <h2 class="text-base font-bold text-white sm:text-lg">Joueurs connectés</h2>
          <span
            class="rounded-full border border-indigo-400/40 bg-indigo-500/20 px-2.5 py-0.5 font-mono text-xs font-bold text-indigo-200"
          >
            {players.length}
          </span>
        </div>

        <span
          class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium {wsConnected
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : 'border-slate-700 bg-slate-950 text-slate-400'}"
        >
          <span
            class="h-1.5 w-1.5 rounded-full {wsConnected
              ? 'animate-pulse bg-emerald-400'
              : 'bg-slate-500'}"
          ></span>
          {wsConnected ? 'En direct' : 'Synchronisation…'}
        </span>
      </div>

      {#if players.length === 0}
        <div class="flex flex-1 flex-col items-center justify-center py-16 text-center">
          <div
            class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-800 bg-slate-950/70 text-slate-500"
          >
            <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
          </div>
          <p class="text-sm font-medium text-slate-300">Aucun joueur connecté pour le moment</p>
          <p class="mt-1 text-xs text-slate-500">
            Scannez le QR code ou ouvrez le lien pour apparaître ici en direct.
          </p>
        </div>
      {:else}
        <ul class="thin-scroll mt-4 flex-1 space-y-2.5 overflow-y-auto pr-1" style="max-height: 460px;">
          {#each players as p (p.session_id)}
            <li
              class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800/90 bg-slate-950/70 px-4 py-3 transition hover:border-slate-700"
            >
              <div class="flex min-w-0 items-center gap-3">
                <span
                  class="h-2.5 w-2.5 shrink-0 rounded-full {p.status === 'playing'
                    ? 'animate-pulse bg-emerald-400'
                    : p.human_won
                      ? 'bg-amber-400'
                      : 'bg-slate-500'}"
                ></span>
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-slate-100">
                    {formatPlayerLabel(p)}
                  </div>
                  <div class="font-mono text-[11px] text-slate-400">
                    {p.moves} {p.moves <= 1 ? 'coup' : 'coups'} · {formatDuration(p)}
                  </div>
                </div>
              </div>

              <span
                class="shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold {statusClass(
                  p
                )}"
              >
                {statusLabel(p)}
              </span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>
