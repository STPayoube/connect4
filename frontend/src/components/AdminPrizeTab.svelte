<script>
  import { onMount } from 'svelte';
  import QRCode from 'qrcode';
  import { adminGetWinAPrizeConfig, adminUpdateWinAPrizeConfig } from '../lib/api.js';
  import { formatLevel, LEVELS } from '../lib/levels.js';

  let { token = '' } = $props();

  let enabled = $state(true);
  let rows = $state(6);
  let cols = $state(7);
  let align = $state(4);
  let aiLevel = $state('medium');
  let startingPlayer = $state('1');
  let humanPlayer = $state(1);
  let allowUndo = $state(false);
  let title = $state('Défi Puissance 4');
  let subtitle = $state("Battez l'IA pour gagner un prix !");
  let applyToLiveGames = $state(true);

  let liveCount = $state(0);
  let saving = $state(false);
  let toast = $state(null);
  let error = $state(null);
  let collisionPopup = $state(null);
  let copied = $state(false);
  let prizeQrUrl = $state('');

  let prizeLink = $derived(
    typeof window !== 'undefined' ? `${window.location.origin}/winaprize` : '/winaprize'
  );
  let maxAlign = $derived(Math.min(rows, cols));

  $effect(() => {
    if (align > maxAlign) align = maxAlign;
  });

  function showToast(msg) {
    toast = msg;
    setTimeout(() => {
      if (toast === msg) toast = null;
    }, 3500);
  }

  async function loadConfig() {
    if (!token) return;
    error = null;
    try {
      const res = await adminGetWinAPrizeConfig(token);
      const c = res.config;
      enabled = c.enabled;
      rows = c.rows;
      cols = c.cols;
      align = c.align;
      aiLevel = c.ai_level;
      startingPlayer = c.random_start ? 'random' : String(c.starting_player);
      humanPlayer = c.human_player;
      allowUndo = c.allow_undo;
      title = c.title;
      subtitle = c.subtitle;
      liveCount = res.live_prize_games || 0;
    } catch (err) {
      error = err.message || 'Impossible de charger la configuration /winaprize.';
    }
  }

  async function saveConfig(overrideLevel = null) {
    if (!token) return;
    saving = true;
    error = null;
    const chosenLevel = overrideLevel || aiLevel;
    const isRandom = startingPlayer === 'random';

    try {
      const res = await adminUpdateWinAPrizeConfig(token, {
        enabled,
        rows: Number(rows),
        cols: Number(cols),
        align: Number(align),
        ai_level: chosenLevel,
        starting_player: isRandom ? 'random' : Number(startingPlayer),
        human_player: Number(humanPlayer),
        random_start: isRandom,
        allow_undo: allowUndo,
        title: title.trim() || 'Défi Puissance 4',
        subtitle: subtitle.trim() || "Battez l'IA pour gagner un prix !",
        apply_to_live_games: applyToLiveGames,
      });
      aiLevel = res.config.ai_level;
      liveCount = res.live_prize_games || 0;
      const suffix =
        res.updated_live_games > 0
          ? ` — appliqué en direct sur ${res.updated_live_games} partie(s) en cours !`
          : '';
      showToast(
        `Paramètres /winaprize enregistrés (${formatLevel(aiLevel)}, ${rows}×${cols}, align ${align})${suffix}`
      );
    } catch (err) {
      if (err.status === 409) {
        collisionPopup = err.message;
        await loadConfig();
      } else {
        error = err.message || 'Échec de la sauvegarde de /winaprize.';
      }
    } finally {
      saving = false;
    }
  }

  async function copyPrizeLink() {
    try {
      await navigator.clipboard.writeText(prizeLink);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      // ignore
    }
  }

  onMount(async () => {
    await loadConfig();
    try {
      prizeQrUrl = await QRCode.toDataURL(prizeLink, {
        width: 220,
        margin: 2,
        color: { dark: '#0f172a', light: '#ffffff' },
      });
    } catch {
      prizeQrUrl = '';
    }
  });
</script>

<div class="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
  <!-- Carte principale -->
  <div class="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-4">
      <div>
        <h2 class="text-base font-bold text-white">Contrôle en direct de /winaprize</h2>
        <p class="text-xs text-slate-400">
          Les changements de difficulté, taille de grille et alignement s'appliquent instantanément aux joueurs en cours.
        </p>
      </div>
      <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-200">
        <input type="checkbox" bind:checked={enabled} onchange={() => saveConfig()} class="accent-emerald-500" />
        <span>{enabled ? 'Défi ouvert' : 'Défi fermé'}</span>
      </label>
    </div>

    {#if error}
      <div class="rounded-xl border border-rose-500/40 bg-rose-950/60 px-3.5 py-2 text-xs text-rose-200">
        {error}
      </div>
    {/if}

    {#if toast}
      <div class="rounded-xl border border-emerald-500/40 bg-emerald-950/50 px-3.5 py-2 text-xs font-medium text-emerald-200">
        {toast}
      </div>
    {/if}

    <!-- Changement de difficulté instantané -->
    <div class="rounded-xl border border-amber-500/35 bg-amber-950/15 p-4 space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span class="text-xs font-bold uppercase tracking-wider text-amber-300">
          Changement de difficulté instantané
        </span>
        <span class="rounded-full bg-amber-500/20 px-2.5 py-0.5 font-mono text-[11px] text-amber-200">
          {liveCount} {liveCount <= 1 ? 'joueur en direct' : 'joueurs en direct'}
        </span>
      </div>

      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {#each LEVELS as lvl}
          <button
            type="button"
            disabled={saving}
            onclick={() => saveConfig(lvl.id)}
            class="rounded-xl border px-3 py-2.5 text-left transition {aiLevel === lvl.id
              ? lvl.active
              : 'border-slate-800 bg-slate-950/70 text-slate-300 hover:border-slate-600'}"
          >
            <div class="text-xs font-bold">{lvl.label}</div>
            <div class="text-[10px] opacity-80">{lvl.desc}</div>
          </button>
        {/each}
      </div>

      <label class="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" bind:checked={applyToLiveGames} class="accent-amber-400" />
        <span>Appliquer immédiatement (difficulté + taille de grille) aux parties /winaprize en cours</span>
      </label>
    </div>

    <!-- Paramètres prédéfinis -->
    <form
      onsubmit={(e) => {
        e.preventDefault();
        saveConfig();
      }}
      class="space-y-4 text-sm"
    >
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label for="prize-title" class="mb-1 block text-xs text-slate-300">Titre de la page</label>
          <input
            id="prize-title"
            type="text"
            maxlength="80"
            bind:value={title}
            class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
          />
        </div>
        <div>
          <label for="prize-sub" class="mb-1 block text-xs text-slate-300">Sous-titre</label>
          <input
            id="prize-sub"
            type="text"
            maxlength="140"
            bind:value={subtitle}
            class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
          />
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3">
        <div>
          <label for="p-rows" class="mb-1 flex justify-between text-xs text-slate-300">
            <span>Lignes</span><span class="font-mono text-indigo-300">{rows}</span>
          </label>
          <input id="p-rows" type="range" min="4" max="10" bind:value={rows} class="w-full accent-indigo-500" />
        </div>
        <div>
          <label for="p-cols" class="mb-1 flex justify-between text-xs text-slate-300">
            <span>Colonnes</span><span class="font-mono text-indigo-300">{cols}</span>
          </label>
          <input id="p-cols" type="range" min="4" max="10" bind:value={cols} class="w-full accent-indigo-500" />
        </div>
        <div>
          <label for="p-align" class="mb-1 flex justify-between text-xs text-slate-300">
            <span>Alignement</span><span class="font-mono text-indigo-300">{align}</span>
          </label>
          <input id="p-align" type="range" min="3" max={maxAlign} bind:value={align} class="w-full accent-indigo-500" />
        </div>
      </div>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label for="p-seat" class="mb-1 block text-xs text-slate-300">Le challenger joue en tant que</label>
          <select
            id="p-seat"
            bind:value={humanPlayer}
            class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
          >
            <option value={1}>Joueur 1</option>
            <option value={2}>Joueur 2</option>
          </select>
        </div>

        <div>
          <label for="p-start" class="mb-1 block text-xs text-slate-300">Premier joueur</label>
          <select
            id="p-start"
            bind:value={startingPlayer}
            class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
          >
            <option value="1">Joueur 1</option>
            <option value="2">Joueur 2</option>
            <option value="random">Tirage aléatoire</option>
          </select>
        </div>
      </div>

      <label class="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" bind:checked={allowUndo} class="accent-indigo-500" />
        <span>Autoriser le bouton Annuler sur /winaprize (déconseillé pour un concours)</span>
      </label>

      <div class="flex justify-end border-t border-slate-800 pt-3">
        <button
          type="submit"
          disabled={saving}
          class="rounded-xl bg-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? 'Application…' : 'Appliquer & Enregistrer'}
        </button>
      </div>
    </form>
  </div>

  <!-- Carte de partage & QR Code -->
  <aside class="space-y-4">
    <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 space-y-3">
      <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-300">
        Lien & QR Code /winaprize
      </h3>
      {#if prizeQrUrl}
        <div class="flex justify-center">
          <div class="rounded-2xl bg-white p-2.5 shadow">
            <img src={prizeQrUrl} alt="QR code pour /winaprize" class="h-44 w-44 rounded-lg" />
          </div>
        </div>
      {/if}
      <div class="truncate rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 font-mono text-[11px] text-slate-300">
        {prizeLink}
      </div>
      <button
        type="button"
        onclick={copyPrizeLink}
        class="w-full rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-500"
      >
        {copied ? 'Lien copié !' : 'Copier le lien /winaprize'}
      </button>
    </div>
  </aside>
</div>

<!-- Pop-up d'erreur de collision de redimensionnement -->
{#if collisionPopup}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
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
          <p class="text-xs text-slate-400">Des pions sont déjà placés sur ces cases</p>
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
