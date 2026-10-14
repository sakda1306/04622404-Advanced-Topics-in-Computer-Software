// Season-scoped fallback, verified against the 07 schedule on 2026-09-30:
// PL 2026: 20 teams, 380 fixtures, rounds 1..38. Do not infer from a filtered page.
const verifiedRounds: Record<string, number> = { "2026": 38 };
export function seasonRounds(season?: string, metadata?: number | null) {
  return metadata && Number.isInteger(metadata) && metadata > 0
    ? metadata
    : season
      ? verifiedRounds[season]
      : undefined;
}
