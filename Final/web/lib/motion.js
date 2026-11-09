// Motion settings in one place (DesignSystem.md 1.3). Change a value here and
// every page transition, success screen and dot grid follows it.

/**
 * Pages that get the full-screen transition on a page change (links, back/forward,
 * the register/login success screen). It runs only when moving from one of these
 * to another. Empty: no page change is covered; only "Generate profile" still
 * shows the panel, because it opens it itself (usePageTransition().show). Exact
 * paths, e.g. ["/", "/login", "/register", "/start", "/profile", "/roles"].
 */
export const TRANSITION_PAGES = [];

/** Full-screen page transition between the pages above. Times in ms. */
export const PAGE_TRANSITION = {
  /** The page stays fully covered at least this long (counted once the halves have met), even when the next page is ready sooner. */
  minHold: 500,
  /** Dots stream in from the left and right and fill the screen. */
  cover: 520,
  /** The dots stream back out to the sides; a little shorter than the cover. */
  reveal: 460,
  /** Lift the panel anyway after this long, so a stuck page shows its own loading or error state. */
  maxHold: 8000,
  /** Success message (register, login): long enough to read. */
  successHold: 900,
  /** "Generate profile": long enough to see the avatar being built. */
  generateHold: 1500,
};

/** How the transition's dots fill the screen (components/motion/dot-curtain.js). */
export const DOT_CURTAIN = {
  /** Tile size, px (each tile starts as a dot); smaller on phones. */
  cell: 16,
  cellSmall: 12,
  /** Latest start of a row, as a share of the cover time; rows start at random up to this. */
  maxDelay: 0.3,
  /** Time a row's front takes from the edge to the middle, as a share of the cover time. */
  travel: [0.38, 0.6],
  /** Time a dot takes to swell into a full tile, as a share of the cover time. */
  grow: 0.12,
  /** How far ahead of the front the small scout dots run, as a share of the cover time. */
  lead: 0.08,
};

/** Twinkling dot grid (landing hero, final call to action, transition panel). */
export const DOT_GRID = {
  /** Distance between dot centres, px. */
  spacing: 8,
  /** Dot radius range, px. */
  radius: [0.6, 1.1],
  /** One twinkle (dim → bright → dim) takes a random time in this range, seconds. */
  cycle: [2, 6],
  /** Share of dots that sparkle brighter than the rest. */
  sparkle: 0.12,
  /** Redraws per second. */
  fps: 30,
};
