// Codex v2: trailing atlas cells are intentionally empty, not animation frames.
export const PET_FRAMES = [7, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8] as const;
export const PET_WIDTH = 144,
  PET_HEIGHT = 156;
export function clampPet(x: number, y: number, width: number, height: number) {
  return {
    x: Math.max(
      8,
      Math.min(Number.isFinite(x) ? x : width - 170, width - PET_WIDTH - 8),
    ),
    y: Math.max(
      8,
      Math.min(Number.isFinite(y) ? y : height - 190, height - PET_HEIGHT - 28),
    ),
  };
}
