<script>
  import Cell from './Cell.svelte';
  import ColumnControls from './ColumnControls.svelte';

  let {
    grid = [],
    rows = 6,
    cols = 7,
    validColumns = [],
    currentPlayer = 1,
    lastMove = null,
    winningCells = [],
    status = 'playing',
    canInteract = false,
    animateDrops = true,
    onPlayColumn = () => {},
  } = $props();

  let hoveredCol = $state(null);

  let validSet = $derived(new Set(validColumns));
  let winningSet = $derived(new Set(winningCells.map(([r, c]) => `${r}:${c}`)));
  let hasWinner = $derived(status === 'win' && winningCells.length > 0);

  let boardMaxWidth = $derived(
    cols <= 5
      ? 'max-w-[440px]'
      : cols <= 7
        ? 'max-w-[580px]'
        : cols <= 8
          ? 'max-w-[650px]'
          : 'max-w-[740px]'
  );

  function handleKeydown(event) {
    if (!canInteract || status !== 'playing') return;
    if (event.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) {
      return;
    }

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      hoveredCol = hoveredCol === null ? Math.floor(cols / 2) : (hoveredCol - 1 + cols) % cols;
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      hoveredCol = hoveredCol === null ? Math.floor(cols / 2) : (hoveredCol + 1) % cols;
    } else if (event.key === 'Enter' || event.key === ' ') {
      if (hoveredCol !== null && validSet.has(hoveredCol)) {
        event.preventDefault();
        onPlayColumn(hoveredCol);
      }
    } else if (event.key >= '1' && event.key <= '9') {
      const idx = Number(event.key) - 1;
      if (idx < cols && validSet.has(idx)) {
        hoveredCol = idx;
        onPlayColumn(idx);
      }
    } else if (event.key === '0' && cols >= 10 && validSet.has(9)) {
      hoveredCol = 9;
      onPlayColumn(9);
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
  class="mx-auto w-full {boardMaxWidth} select-none"
  role="region"
  aria-label="Connect 4 board"
  onmouseleave={() => (hoveredCol = null)}
>
  <ColumnControls
    {cols}
    {hoveredCol}
    {validColumns}
    {currentPlayer}
    {canInteract}
    onSelectCol={onPlayColumn}
    onHoverCol={(c) => (hoveredCol = c)}
  />

  <!-- Tactile Tabletop Board Chassis -->
  <div
    class="relative rounded-2xl border border-indigo-400/25 bg-gradient-to-b from-indigo-900/95 via-slate-900 to-slate-950 p-2.5 shadow-[0_24px_60px_-12px_rgba(0,0,0,0.85),inset_0_1px_1px_rgba(255,255,255,0.18)] sm:rounded-3xl sm:p-3.5"
  >
    <div
      class="grid overflow-hidden rounded-xl bg-slate-900/40 p-1 sm:rounded-2xl"
      style="grid-template-columns: repeat({cols}, minmax(0, 1fr)); gap: {cols >= 9
        ? '0.25rem'
        : '0.5rem'};"
    >
      {#each grid as rowArr, rIdx}
        {#each rowArr as cellVal, cIdx (`${rIdx}-${cIdx}-${cellVal}`)}
          <Cell
            value={cellVal}
            row={rIdx}
            col={cIdx}
            isLastMove={lastMove !== null && lastMove.row === rIdx && lastMove.col === cIdx}
            isWinning={winningSet.has(`${rIdx}:${cIdx}`)}
            {hasWinner}
            isHoveredCol={hoveredCol === cIdx}
            isValidCol={validSet.has(cIdx)}
            {canInteract}
            animateDrop={animateDrops}
            onSelectCol={onPlayColumn}
            onHoverCol={(c) => (hoveredCol = c)}
          />
        {/each}
      {/each}
    </div>
  </div>

  <!-- Subtle tabletop stand feet -->
  <div class="mx-6 flex items-center justify-between">
    <div
      class="h-2.5 w-14 rounded-b-lg border-x border-b border-indigo-400/20 bg-slate-900/90 shadow-lg"
    ></div>
    <p class="mt-2 hidden text-[11px] text-slate-500 sm:block">
      Tip: Click a column or use keys <span class="font-mono text-slate-400">1–{cols}</span> /
      <span class="font-mono text-slate-400">← → Enter</span>
    </p>
    <div
      class="h-2.5 w-14 rounded-b-lg border-x border-b border-indigo-400/20 bg-slate-900/90 shadow-lg"
    ></div>
  </div>
</div>
