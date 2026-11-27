<script>
  let {
    player = 1,
    row = 0,
    isLastMove = false,
    isWinning = false,
    isDimmed = false,
    animateDrop = true,
  } = $props();

  let dropDuration = $derived(`${Math.min(240 + row * 48, 560)}ms`);

  let colorClasses = $derived(
    player === 1
      ? 'bg-gradient-to-br from-rose-400 via-rose-500 to-red-700 shadow-[inset_0_-4px_8px_rgba(127,29,29,0.7),inset_0_3px_6px_rgba(255,228,230,0.45),0_4px_12px_rgba(244,63,94,0.35)]'
      : 'bg-gradient-to-br from-amber-300 via-amber-400 to-amber-600 shadow-[inset_0_-4px_8px_rgba(146,64,14,0.65),inset_0_3px_6px_rgba(254,249,195,0.55),0_4px_12px_rgba(251,191,36,0.3)]'
  );

  let innerRingClasses = $derived(
    player === 1
      ? 'border-rose-300/35 bg-gradient-to-tl from-rose-500/40 to-red-800/35'
      : 'border-amber-100/45 bg-gradient-to-tl from-amber-400/35 to-amber-700/30'
  );
</script>

<div
  class="relative h-full w-full rounded-full transition-opacity duration-300 {colorClasses} {animateDrop
    ? 'animate-disc-drop'
    : ''} {isWinning ? 'animate-win-pulse z-10' : ''} {isDimmed ? 'opacity-45' : 'opacity-100'}"
  style="--drop-rows: {row + 1.4}; --drop-duration: {dropDuration};"
>
  <!-- Machined inner groove -->
  <div
    class="pointer-events-none absolute inset-[15%] rounded-full border-2 {innerRingClasses}"
  ></div>

  <!-- Specular highlight -->
  <div
    class="pointer-events-none absolute left-[20%] top-[14%] h-[22%] w-[36%] -rotate-20 rounded-full bg-white/35 blur-[1px]"
  ></div>

  <!-- Last move marker -->
  {#if isLastMove && !isWinning}
    <div
      class="pointer-events-none absolute inset-0 flex items-center justify-center"
      title="Dernier coup joué"
    >
      <span
        class="h-2.5 w-2.5 rounded-full bg-white shadow-[0_0_10px_2px_rgba(255,255,255,0.9)] ring-2 ring-slate-900/60"
      ></span>
    </div>
  {/if}

  <!-- Winning star/dot marker -->
  {#if isWinning}
    <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
      <span
        class="h-3 w-3 rounded-full bg-emerald-200 shadow-[0_0_12px_3px_rgba(255,255,255,0.95)] ring-2 ring-emerald-500"
      ></span>
    </div>
  {/if}
</div>
