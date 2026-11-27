<script>
  let {
    cols = 7,
    hoveredCol = null,
    validColumns = [],
    currentPlayer = 1,
    canInteract = false,
    onSelectCol = () => {},
    onHoverCol = () => {},
  } = $props();

  let validSet = $derived(new Set(validColumns));

  let ghostColors = $derived(
    currentPlayer === 1
      ? 'from-rose-400/90 to-red-600/90 shadow-[0_6px_18px_rgba(244,63,94,0.45)] ring-rose-300/60'
      : 'from-amber-300/90 to-amber-500/90 shadow-[0_6px_18px_rgba(251,191,36,0.45)] ring-amber-200/70'
  );
</script>

<div
  class="mb-2 grid px-2.5 sm:px-3.5"
  style="grid-template-columns: repeat({cols}, minmax(0, 1fr)); gap: {cols >= 9
    ? '0.25rem'
    : '0.5rem'};"
>
  {#each Array(cols) as _, colIdx}
    {@const isValid = validSet.has(colIdx)}
    {@const isHovered = hoveredCol === colIdx}
    {@const active = canInteract && isValid}
    <button
      type="button"
      disabled={!active}
      onclick={() => active && onSelectCol(colIdx)}
      onmouseenter={() => onHoverCol(colIdx)}
      onfocus={() => onHoverCol(colIdx)}
      aria-label="Lâcher un pion dans la colonne {colIdx + 1}"
      class="flex flex-col items-center justify-end gap-1 focus:outline-none {active
        ? 'cursor-pointer'
        : 'cursor-default'}"
    >
      <div class="flex aspect-square w-full max-w-[52px] items-center justify-center p-[8%]">
        <div
          class="h-full w-full rounded-full bg-gradient-to-br ring-2 transition-all duration-150 {ghostColors} {isHovered &&
          active
            ? 'translate-y-0 scale-100 opacity-100'
            : '-translate-y-1.5 scale-75 opacity-0'}"
        ></div>
      </div>
      <span
        class="font-mono text-[11px] font-semibold transition-colors {isHovered && active
          ? currentPlayer === 1
            ? 'text-rose-400'
            : 'text-amber-300'
          : isValid
            ? 'text-slate-500'
            : 'text-slate-700'}"
      >
        {colIdx + 1}
      </span>
    </button>
  {/each}
</div>
