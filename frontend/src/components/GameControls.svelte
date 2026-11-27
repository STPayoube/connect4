<script>
  import { LEVELS } from '../lib/levels.js';

  let {
    game = null,
    isThinking = false,
    isAutoPlaying = false,
    autoSpeedMs = 600,
    showInspector = true,
    onNewGame = () => {},
    onRandomStart = () => {},
    onPlayWithFriend = () => {},
    onSwitchMode = () => {},
    onQuickLevel = () => {},
    onUndo = () => {},
    onOpenSettings = () => {},
    onToggleInspector = () => {},
    onStepAi = () => {},
    onToggleAutoPlay = () => {},
    onChangeSpeed = () => {},
  } = $props();

  let currentMode = $derived(game?.config?.mode || 'human_vs_ai');
  let isAiVsAi = $derived(currentMode === 'ai_vs_ai');
  let isHumanVsAi = $derived(currentMode === 'human_vs_ai');
  let activeIsAi = $derived(
    game?.status === 'playing' && game?.players?.[String(game.current_player)]?.type === 'ai'
  );

  const modes = [
    { id: 'human_vs_ai', label: "Contre l'IA" },
    { id: 'player_vs_player', label: 'Joueur vs Joueur' },
    { id: 'ai_vs_ai', label: 'IA vs IA' },
  ];
</script>

<div class="space-y-3">
  <!-- Sélecteur de mode -->
  <div class="grid grid-cols-3 gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1">
    {#each modes as m}
      <button
        type="button"
        onclick={() => onSwitchMode(m.id)}
        class="rounded-lg px-2 py-1.5 text-xs font-semibold transition {currentMode === m.id
          ? 'bg-indigo-600 text-white shadow'
          : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'}"
      >
        {m.label}
      </button>
    {/each}
  </div>

  <!-- Niveau IA rapide -->
  {#if isHumanVsAi && game}
    <div class="rounded-xl border border-slate-800/90 bg-slate-900/70 p-2.5">
      <div class="mb-1.5 flex items-center justify-between">
        <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Niveau de l'IA
        </span>
        <span class="text-[11px] text-slate-500">Nouvelle partie</span>
      </div>
      <div class="grid grid-cols-4 gap-1.5">
        {#each LEVELS as lvl}
          <button
            type="button"
            onclick={() => onQuickLevel(lvl.id)}
            class="rounded-lg border px-1 py-1.5 text-center text-[11px] font-semibold transition {game
              .config.ai_level === lvl.id
              ? lvl.active
              : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700 hover:text-slate-200'}"
          >
            {lvl.short}
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Jouer avec un ami en ligne (QR Code + WebSocket) -->
  <button
    type="button"
    onclick={onPlayWithFriend}
    class="flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3.5 py-2.5 text-sm font-semibold text-emerald-200 shadow-sm transition hover:bg-emerald-500/25 active:scale-[0.98]"
  >
    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <path stroke-linecap="round" d="M14 14h3v3h-3zM19 14v7M14 19h5" />
    </svg>
    Jouer avec un ami (QR Code)
  </button>

  <!-- Actions principales -->
  <div class="grid grid-cols-2 gap-2">
    <button
      type="button"
      onclick={onNewGame}
      class="inline-flex items-center justify-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 active:scale-[0.98]"
    >
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
      Nouvelle
    </button>

    <button
      type="button"
      onclick={onRandomStart}
      class="inline-flex items-center justify-center gap-1.5 rounded-xl border border-indigo-400/40 bg-indigo-500/15 px-3 py-2 text-sm font-semibold text-indigo-200 transition hover:bg-indigo-500/25 active:scale-[0.98]"
      title="Lancer une partie avec un premier joueur aléatoire"
    >
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <circle cx="8.5" cy="8.5" r="1.2" fill="currentColor" />
        <circle cx="15.5" cy="15.5" r="1.2" fill="currentColor" />
        <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      </svg>
      Aléatoire
    </button>
  </div>

  <!-- Actions secondaires -->
  <div class="flex items-center gap-2">
    <button
      type="button"
      onclick={onUndo}
      disabled={!game?.can_undo || isThinking}
      class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-slate-700/80 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 14l-4-4m0 0l4-4m-4 4h11a4 4 0 010 8h-1" />
      </svg>
      Annuler
    </button>

    <button
      type="button"
      onclick={onOpenSettings}
      class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-slate-700/80 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-800"
    >
      <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
        />
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
      Paramètres
    </button>

    {#if currentMode !== 'player_vs_player'}
      <button
        type="button"
        onclick={onToggleInspector}
        class="inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-semibold transition {showInspector
          ? 'border-indigo-500/50 bg-indigo-500/15 text-indigo-200'
          : 'border-slate-700/80 bg-slate-900 text-slate-400 hover:text-slate-200'}"
        title="Afficher ou masquer l'inspecteur IA WeakC4"
      >
        Debug IA
      </button>
    {/if}
  </div>

  <!-- Contrôles IA vs IA / pas-à-pas -->
  {#if isAiVsAi || activeIsAi}
    <div class="rounded-xl border border-indigo-500/25 bg-slate-900/80 p-3 backdrop-blur">
      <div class="mb-2 flex items-center justify-between">
        <span class="text-xs font-semibold uppercase tracking-wider text-indigo-300">
          {isAiVsAi ? 'Lecture IA vs IA' : 'Contrôle du tour IA'}
        </span>
        {#if isAiVsAi}
          <div class="flex items-center gap-1 rounded-lg bg-slate-950/80 p-0.5 text-[11px]">
            {#each [
              { label: 'Lent', ms: 1100 },
              { label: 'Normal', ms: 550 },
              { label: 'Rapide', ms: 180 },
            ] as opt}
              <button
                type="button"
                onclick={() => onChangeSpeed(opt.ms)}
                class="rounded-md px-2 py-0.5 font-medium transition {autoSpeedMs === opt.ms
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'}"
              >
                {opt.label}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <div class="flex items-center gap-2">
        {#if isAiVsAi}
          <button
            type="button"
            onclick={onToggleAutoPlay}
            disabled={game?.status !== 'playing'}
            class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 {isAutoPlaying
              ? 'bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/50 hover:bg-amber-500/30'
              : 'bg-emerald-600 text-white hover:bg-emerald-500'}"
          >
            {isAutoPlaying ? 'Pause' : 'Lecture auto'}
          </button>
        {/if}

        <button
          type="button"
          onclick={onStepAi}
          disabled={!activeIsAi || isThinking || isAutoPlaying}
          class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-medium text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Coup IA
        </button>
      </div>
    </div>
  {/if}
</div>
