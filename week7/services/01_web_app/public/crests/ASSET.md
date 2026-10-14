# Club crests

Catalog checked on 2026-09-30 against Module 07's `/football/teams` dataset (20 clubs for season 2026). `catalog.json` records the original club names, IDs and source URLs supplied by that dataset.

Files are served locally as `/crests/{team_id}.png`; five existing crests were retained and fifteen missing crests added. Source host: `https://crests.football-data.org/`. Bournemouth's source basename is `bournemouth.png`, stored as `1044.png` to match its team ID. Club marks belong to their respective owners; this catalog is provenance, not a license grant.

The selector intentionally contains only the five supported favorite/browsing clubs. Tables and fixtures can display every catalog club. Unknown IDs or failed images show a neutral shield alongside the actual team name. Update this catalog/assets when the dataset changes; there is no new backend endpoint or cross-origin image dependency at runtime.

`public/panda-logo.svg` is a code-native panda brand mark created for PANBALL. Existing stadium artwork and mascot sheets retain their original provenance in their asset directories.
