<script>
  import { LEVELS } from '../lib/levels.js';

  let { open = false, config = null, onClose = () => {}, onApply = () => {} } = $props();

  let rows = $state(6);
  let cols = $state(7);
  let align = $state(4);
  let mode = $state('human_vs_ai');
  let humanPlayer = $state(1);
  let startingPlayer = $state('1');
  let aiLevel = $state('medium');
  let ai2Level = $state('medium');
  let username = $state('Invité');
  let player2Name = $state('Joueur 2');

  const presets = [
    { name: 'Classique 6×7', rows: 6, cols: 7, align: 4 },
    { name: 'WeakC4 7×8', rows: 7, cols: 8, align: 4 },
    { name: 'Rapide 5×6', rows: 5, cols: 6, align: 4 },
    { name: 'Puissance 5', rows: 8, cols: 9, align: 5 },
  ];

  let wasOpen = false;

  $effect(() => {
    if (open && !wasOpen && config) {
      rows = config.rows;
      cols = config.cols;
      align = config.align;
      mode = config.mode;
      humanPlayer = config.human_player;
      startingPlayer = config.random_start ? 'random' : String(config.starting_player);
      aiLevel = config.ai_level || 'medium';
      ai2Level = config.ai2_level || config.ai_level || 'medium';
      username = config.username || 'Invité';
      player2Name = config.player2_name || 'Joueur 2';
    }
    wasOpen = open;
  });

  let maxAlign = $derived(Math.min(rows, cols));

  $effect(() => {
    if (align > maxAlign) {
      align = maxAlign;
    }
  });

  function applyPreset(preset) {
    rows = preset.rows;
    cols = preset.cols;
    align = preset.align;
  }

  function handleSubmit(event) {
    event.preventDefault();
    const isRandom = startingPlayer === 'random';
    onApply({
      rows: Number(rows),
      cols: Number(cols),
      align: Number(align),
      mode,
      human_player: Number(humanPlayer),
      starting_player: isRandom ? 'random' : Number(startingPlayer),
      random_start: isRandom,
      ai_level: aiLevel,
      ai2_level: mode === 'ai_vs_ai' ? ai2Level : aiLevel,
      username: username.trim() || 'Invité',
      player2_name: player2Name.trim() || 'Joueur 2',
    });
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-labelledby="settings-title"
  >
    <div
      class="thin-scroll max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-slate-700/80 bg-slate-900 shadow-2xl"
    >
      <div class="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div>
          <h2 id="settings-title" class="text-base font-bold text-slate-100">Paramètres de la partie</h2>
          <p class="text-xs text-slate-400">
            Configurez la grille, le mode, les joueurs et la difficulté de l'IA
          </p>
        </div>
        <button
          type="button"
          onclick={onClose}
          class="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          aria-label="Fermer les paramètres"
        >
          ✕
        </button>
      </div>

      <form onsubmit={handleSubmit} class="space-y-5 p-5 text-sm">
        <!-- Mode -->
        <div>
          <span class="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
            Mode de jeu
          </span>
          <div class="grid grid-cols-3 gap-2">
            {#each [
              { id: 'human_vs_ai', title: "Contre l'IA", sub: "Défier l'IA" },
              { id: 'player_vs_player', title: 'Joueur vs Joueur', sub: '2 joueurs local' },
              { id: 'ai_vs_ai', title: 'IA vs IA', sub: 'Observer / pas-à-pas' },
            ] as opt}
              <button
                type="button"
                onclick={() => (mode = opt.id)}
                class="rounded-xl border px-3 py-2.5 text-left transition {mode === opt.id
                  ? 'border-indigo-500 bg-indigo-500/15 text-white'
                  : 'border-slate-800 bg-slate-950/50 text-slate-400 hover:text-slate-200'}"
              >
                <div class="text-xs font-semibold sm:text-sm">{opt.title}</div>
                <div class="text-[11px] text-slate-400">{opt.sub}</div>
              </button>
            {/each}
          </div>
        </div>

        <!-- Pseudos -->
        <div class="grid grid-cols-1 gap-3 {mode === 'player_vs_player' ? 'sm:grid-cols-2' : ''}">
          <div>
            <label for="username-input" class="mb-1.5 block text-xs font-medium text-slate-300">
              {mode === 'player_vs_player' ? 'Pseudo Joueur 1 (Rouge)' : 'Votre pseudo'}
            </label>
            <input
              id="username-input"
              type="text"
              maxlength="32"
              bind:value={username}
              placeholder="Entrez votre pseudo"
              class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>

          {#if mode === 'player_vs_player'}
            <div>
              <label for="p2-input" class="mb-1.5 block text-xs font-medium text-slate-300">
                Pseudo Joueur 2 (Or)
              </label>
              <input
                id="p2-input"
                type="text"
                maxlength="32"
                bind:value={player2Name}
                placeholder="Joueur 2"
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </div>
          {/if}
        </div>

        <!-- Niveaux IA -->
        {#if mode !== 'player_vs_player'}
          <div class="space-y-3">
            <div>
              <span class="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                {mode === 'ai_vs_ai' ? 'Niveau IA 1 (Rouge Corail)' : "Niveau de difficulté de l'IA"}
              </span>
              <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {#each LEVELS as lvl}
                  <button
                    type="button"
                    onclick={() => (aiLevel = lvl.id)}
                    class="rounded-xl border px-2.5 py-2 text-left transition {aiLevel === lvl.id
                      ? lvl.active
                      : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700'}"
                  >
                    <div class="text-xs font-bold">{lvl.label}</div>
                    <div class="text-[10px] opacity-80">{lvl.desc}</div>
                  </button>
                {/each}
              </div>
            </div>

            {#if mode === 'ai_vs_ai'}
              <div>
                <span class="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Niveau IA 2 (Or Ambré)
                </span>
                <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {#each LEVELS as lvl}
                    <button
                      type="button"
                      onclick={() => (ai2Level = lvl.id)}
                      class="rounded-xl border px-2.5 py-2 text-left transition {ai2Level === lvl.id
                        ? lvl.active
                        : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700'}"
                    >
                      <div class="text-xs font-bold">{lvl.label}</div>
                      <div class="text-[10px] opacity-80">{lvl.desc}</div>
                    </button>
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        {/if}

        <!-- Couleur & Premier joueur -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {#if mode === 'human_vs_ai'}
            <div>
              <label for="human-seat" class="mb-1.5 block text-xs font-medium text-slate-300">
                Jouer en tant que
              </label>
              <select
                id="human-seat"
                bind:value={humanPlayer}
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              >
                <option value={1}>Joueur 1 (Rouge Corail)</option>
                <option value={2}>Joueur 2 (Or Ambré)</option>
              </select>
            </div>
          {/if}

          <div class={mode !== 'human_vs_ai' ? 'sm:col-span-2' : ''}>
            <label for="starter-select" class="mb-1.5 block text-xs font-medium text-slate-300">
              Premier joueur
            </label>
            <select
              id="starter-select"
              bind:value={startingPlayer}
              class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="1">Joueur 1 (Rouge Corail)</option>
              <option value="2">Joueur 2 (Or Ambré)</option>
              <option value="random">Aléatoire (Tirage au sort)</option>
            </select>
          </div>
        </div>

        <!-- Préréglages de grille -->
        <div>
          <span class="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
            Grilles prédéfinies
          </span>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {#each presets as preset}
              <button
                type="button"
                onclick={() => applyPreset(preset)}
                class="rounded-lg border px-2.5 py-2 text-center text-xs font-medium transition {rows ===
                  preset.rows &&
                cols === preset.cols &&
                align === preset.align
                  ? 'border-indigo-500 bg-indigo-500/20 text-indigo-200'
                  : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700'}"
              >
                {preset.name}
              </button>
            {/each}
          </div>
        </div>

        <!-- Dimensions -->
        <div class="grid grid-cols-3 gap-3">
          <div>
            <label for="rows-input" class="mb-1 flex justify-between text-xs text-slate-300">
              <span>Lignes</span>
              <span class="font-mono text-indigo-300">{rows}</span>
            </label>
            <input
              id="rows-input"
              type="range"
              min="4"
              max="10"
              bind:value={rows}
              class="w-full accent-indigo-500"
            />
          </div>

          <div>
            <label for="cols-input" class="mb-1 flex justify-between text-xs text-slate-300">
              <span>Colonnes</span>
              <span class="font-mono text-indigo-300">{cols}</span>
            </label>
            <input
              id="cols-input"
              type="range"
              min="4"
              max="10"
              bind:value={cols}
              class="w-full accent-indigo-500"
            />
          </div>

          <div>
            <label for="align-input" class="mb-1 flex justify-between text-xs text-slate-300">
              <span>Alignement</span>
              <span class="font-mono text-indigo-300">{align}</span>
            </label>
            <input
              id="align-input"
              type="range"
              min="3"
              max={maxAlign}
              bind:value={align}
              class="w-full accent-indigo-500"
            />
          </div>
        </div>

        <!-- Pied de modale -->
        <div class="flex items-center justify-end gap-2 border-t border-slate-800 pt-4">
          <button
            type="button"
            onclick={onClose}
            class="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800"
          >
            Annuler
          </button>
          <button
            type="submit"
            class="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500"
          >
            Lancer la partie
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
