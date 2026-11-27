<script>
  import { onMount } from 'svelte';
  import {
    adminAddBlacklist,
    adminDeleteBlacklist,
    adminListBlacklist,
  } from '../lib/api.js';

  let { token = '' } = $props();

  let entries = $state([]);
  let pattern = $state('');
  let matchType = $state('exact');
  let reason = $state('');
  let loading = $state(true);
  let saving = $state(false);
  let error = $state(null);

  async function loadEntries() {
    if (!token) return;
    loading = true;
    error = null;
    try {
      const res = await adminListBlacklist(token);
      entries = res.entries || [];
    } catch (err) {
      error = err.message || 'Could not load blacklist.';
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
      error = err.message || 'Could not add blacklist entry.';
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
      error = err.message || 'Could not remove entry.';
    }
  }

  onMount(() => {
    loadEntries();
  });
</script>

<div class="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
  <!-- Add Form -->
  <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
    <h2 class="text-sm font-bold text-white">Add Banned Username</h2>
    <p class="mt-1 text-xs text-slate-400">
      Blocked across Normal games, /winaprize, and Online Friend rooms (case-insensitive).
    </p>

    {#if error}
      <div class="mt-3 rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">
        {error}
      </div>
    {/if}

    <form onsubmit={handleAdd} class="mt-4 space-y-3.5 text-xs">
      <div>
        <label for="bl-pat" class="mb-1 block font-medium text-slate-300">Username / Word</label>
        <input
          id="bl-pat"
          type="text"
          required
          maxlength="32"
          bind:value={pattern}
          placeholder="e.g. badword"
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
      </div>

      <div>
        <label for="bl-type" class="mb-1 block font-medium text-slate-300">Match Rule</label>
        <select
          id="bl-type"
          bind:value={matchType}
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option value="exact">Exact Username Match</option>
          <option value="contains">Contains Substring</option>
        </select>
      </div>

      <div>
        <label for="bl-reason" class="mb-1 block font-medium text-slate-300">
          Reason (optional)
        </label>
        <input
          id="bl-reason"
          type="text"
          maxlength="120"
          bind:value={reason}
          placeholder="e.g. Inappropriate name"
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
      </div>

      <button
        type="submit"
        disabled={saving}
        class="w-full rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-rose-500 disabled:opacity-50"
      >
        {saving ? 'Adding…' : 'Block Username'}
      </button>
    </form>
  </div>

  <!-- List -->
  <div class="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-bold text-white">Active Blacklist ({entries.length})</h2>
      <button
        type="button"
        onclick={loadEntries}
        class="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700"
      >
        Refresh
      </button>
    </div>

    {#if loading}
      <p class="py-10 text-center text-xs text-slate-500">Loading blacklist…</p>
    {:else if entries.length === 0}
      <p class="rounded-xl border border-dashed border-slate-800 py-10 text-center text-xs text-slate-500">
        No usernames are currently blacklisted.
      </p>
    {:else}
      <ul class="divide-y divide-slate-800/80">
        {#each entries as entry (entry.id)}
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
                  {entry.match_type}
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
              Unban
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>
