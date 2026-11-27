<script>
  import { onMount } from 'svelte';
  import {
    adminAddBlacklist,
    adminDeleteBlacklist,
    adminListBlacklist,
    adminSeedDefaultBlacklist,
  } from '../lib/api.js';

  let { token = '' } = $props();

  let entries = $state([]);
  let pattern = $state('');
  let matchType = $state('exact');
  let reason = $state('');
  let searchFilter = $state('');
  let loading = $state(true);
  let saving = $state(false);
  let seeding = $state(false);
  let error = $state(null);
  let info = $state(null);

  let filteredEntries = $derived.by(() => {
    const q = searchFilter.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.pattern.toLowerCase().includes(q) || (e.reason || '').toLowerCase().includes(q)
    );
  });

  async function loadEntries() {
    if (!token) return;
    loading = true;
    error = null;
    try {
      const res = await adminListBlacklist(token);
      entries = res.entries || [];
    } catch (err) {
      error = err.message || 'Impossible de charger la liste noire.';
    } finally {
      loading = false;
    }
  }

  async function handleAdd(event) {
    event.preventDefault();
    if (!pattern.trim()) return;
    saving = true;
    error = null;
    try {
      await adminAddBlacklist(token, pattern.trim(), matchType, reason.trim());
      pattern = '';
      reason = '';
      await loadEntries();
    } catch (err) {
      error = err.message || "Impossible d'ajouter cette entrée.";
    } finally {
      saving = false;
    }
  }

  async function handleRemove(id) {
    error = null;
    try {
      await adminDeleteBlacklist(token, id);
      entries = entries.filter((e) => e.id !== id);
    } catch (err) {
      error = err.message || 'Impossible de supprimer cette entrée.';
    }
  }

  async function handleSeedDefaults() {
    if (seeding) return;
    seeding = true;
    error = null;
    info = null;
    try {
      const res = await adminSeedDefaultBlacklist(token);
      entries = res.entries || [];
      info =
        res.added > 0
          ? `${res.added} entrées par défaut (insultes, slurs FR/EN, noms réservés) ajoutées.`
          : 'La liste noire par défaut est déjà complète.';
    } catch (err) {
      error = err.message || 'Impossible de charger la liste par défaut.';
    } finally {
      seeding = false;
    }
  }

  onMount(() => {
    loadEntries();
  });
</script>

<div class="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
  <!-- Formulaire d'ajout -->
  <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
    <h2 class="text-sm font-bold text-white">Bannir un pseudo</h2>
    <p class="mt-1 text-xs text-slate-400">
      Bloqué dans le mode normal, /winaprize et les parties entre amis (insensible à la casse).
    </p>

    {#if error}
      <div class="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">
        {error}
      </div>
    {/if}

    <form onsubmit={handleAdd} class="mt-4 space-y-3.5 text-xs">
      <div>
        <label for="bl-pat" class="mb-1 block font-medium text-slate-300">Pseudo ou mot interdit</label>
        <input
          id="bl-pat"
          type="text"
          required
          maxlength="32"
          bind:value={pattern}
          placeholder="ex. motinterdit"
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
      </div>

      <div>
        <label for="bl-type" class="mb-1 block font-medium text-slate-300">Type de blocage</label>
        <select
          id="bl-type"
          bind:value={matchType}
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option value="exact">Correspondance exacte</option>
          <option value="contains">Contient le mot</option>
        </select>
      </div>

      <div>
        <label for="bl-reason" class="mb-1 block font-medium text-slate-300">
          Motif (optionnel)
        </label>
        <input
          id="bl-reason"
          type="text"
          maxlength="120"
          bind:value={reason}
          placeholder="ex. Pseudo inapproprié"
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
      </div>

      <button
        type="submit"
        disabled={saving}
        class="w-full rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-rose-500 disabled:opacity-50"
      >
        {saving ? 'Ajout…' : 'Bannir le pseudo'}
      </button>
    </form>
  </div>

  <!-- Liste active -->
  <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-sm font-bold text-white">
        Liste noire active ({filteredEntries.length} / {entries.length})
      </h2>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={seeding}
          onclick={handleSeedDefaults}
          class="rounded-lg border border-indigo-500/40 bg-indigo-500/15 px-2.5 py-1 text-xs font-semibold text-indigo-200 hover:bg-indigo-500/25 disabled:opacity-50"
          title="Réimporter les insultes FR/EN, slurs et pseudos réservés manquants"
        >
          {seeding ? 'Import…' : 'Charger la liste par défaut'}
        </button>
        <button
          type="button"
          onclick={loadEntries}
          class="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700"
        >
          Actualiser
        </button>
      </div>
    </div>

    {#if info}
      <div class="mb-3 rounded-xl border border-emerald-500/40 bg-emerald-950/50 px-3 py-2 text-xs text-emerald-200">
        {info}
      </div>
    {/if}

    <div class="mb-3">
      <input
        type="search"
        bind:value={searchFilter}
        placeholder="Filtrer dans la liste noire (mot ou motif)…"
        class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
      />
    </div>

    {#if loading}
      <p class="py-10 text-center text-xs text-slate-500">Chargement de la liste noire…</p>
    {:else if filteredEntries.length === 0}
      <p class="rounded-xl border border-dashed border-slate-800 py-10 text-center text-xs text-slate-500">
        {entries.length === 0
          ? "Aucun pseudo n'est actuellement banni."
          : 'Aucune entrée ne correspond à votre recherche.'}
      </p>
    {:else}
      <ul class="thin-scroll max-h-[520px] divide-y divide-slate-800/80 overflow-y-auto pr-1">
        {#each filteredEntries as entry (entry.id)}
          <li class="flex items-center justify-between gap-3 py-2.5 text-xs">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-mono text-sm font-semibold text-rose-200">{entry.pattern}</span>
                <span
                  class="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase {entry.match_type ===
                  'contains'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'bg-slate-800 text-slate-300'}"
                >
                  {entry.match_type === 'contains' ? 'Contient' : 'Exact'}
                </span>
              </div>
              {#if entry.reason}
                <p class="mt-0.5 text-[11px] text-slate-400">{entry.reason}</p>
              {/if}
            </div>
            <button
              type="button"
              onclick={() => handleRemove(entry.id)}
              class="shrink-0 rounded-lg border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:border-emerald-500/50 hover:text-emerald-300"
            >
              Débannir
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>
