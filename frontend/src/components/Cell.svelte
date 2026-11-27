<script>
  import Disc from './Disc.svelte';

  let {
    value = 0,
    row = 0,
    col = 0,
    isLastMove = false,
    isWinning = false,
    hasWinner = false,
    isHoveredCol = false,
    isValidCol = false,
    canInteract = false,
    animateDrop = true,
    onSelectCol = () => {},
    onHoverCol = () => {},
  } = $props();

  let interactive = $derived(canInteract && isValidCol);
</script>

<button
  type="button"
  aria-label="Ligne {row + 1}, Colonne {col + 1}{value === 1
    ? ', Joueur 1'
    : value === 2
      ? ', Joueur 2'
      : ', Vide'}"
  disabled={!interactive}
  onclick={() => interactive && onSelectCol(col)}
  onmouseenter={() => onHoverCol(col)}
  onfocus={() => onHoverCol(col)}
  class="group relative flex aspect-square w-full items-center justify-center rounded-full p-[6%] transition-colors duration-150 focus:outline-none {interactive
    ? 'cursor-pointer'
    : 'cursor-default'} {isHoveredCol && interactive
    ? 'bg-indigo-400/15'
    : 'bg-transparent'}"
>
  <!-- Recessed circular cutout -->
  <div
    class="relative flex h-full w-full items-center justify-center rounded-full bg-slate-950/90 p-[4%] shadow-[inset_0_5px_10px_rgba(0,0,0,0.85),0_1px_0_rgba(148,163,184,0.18)] transition-all duration-150 {isHoveredCol &&
    interactive &&
    value === 0
      ? 'ring-2 ring-indigo-400/40'
      : ''}"
  >
    {#if value !== 0}
      <Disc
        player={value}
        {row}
        {isLastMove}
        {isWinning}
        isDimmed={hasWinner && !isWinning}
        {animateDrop}
      />
    {/if}
  </div>
</button>
