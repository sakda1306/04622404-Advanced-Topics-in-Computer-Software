# Club Edition — 26 September 2026

Implemented against the supplied Login, Admin and five-club concept images. Changes are confined to service 01.

- Five individual generated stadium artworks in `public/backgrounds/{team-key}.png`, shared by the home hero, login panel, admin hero and match card. The active team selects the actual image, not a color filter.
- Manchester United: Old Trafford steelwork, red flags and scarves.
- Manchester City: Etihad roof, sky blue flags and cool lighting.
- Chelsea: Stamford Bridge, royal blue flags and Pride of London scarf.
- Liverpool: Anfield, liver bird flags and amber/red light.
- Arsenal: Emirates roof, cannon flags and red/white/gold styling.
- Local crest images from `https://crests.football-data.org/{id}.png`, IDs 66, 65, 61, 64, 57. Retained proportions and original colors.
- Larger condensed headings, charcoal panels, geometric PitchSide mark, club selectors, spacious login and an Admin stadium banner.
- Home match preview and league snapshot use existing football APIs. Missing data remains an empty state. Admin Pipeline and recent feedback use existing admin APIs. The API has no daily-volume series, so aggregate distribution charts remain instead of inventing daily statistics.

## Image generation

Built-in imagegen, one call per club. These are generated artistic interpretations of club grounds, not documentary photographs; stadium details and crests within the generated photos may differ from reality. UI crests are separate downloaded assets.

Prompt template used for all five images:

> Create ONE cinematic photorealistic BACKGROUND IMAGE for a premium football club website. Landscape 1536x1024. [Club description below]. Immersive supporter viewpoint inside the stadium at night. Dramatic stormy charcoal sky upper left, stadium roof spans diagonally from middle left to upper right, brilliant floodlights, densely packed fans along lower half, silhouette of a fan lifting a scarf at left, a magnificent waving team flag occupying right quarter. Authentic club identity and spectacular matchday atmosphere. Deep near-black shadows, realistic fabric and film grain, editorial sports photography, subtle smoke, high detail. Keep left upper third relatively dark for white heading overlaid in code. Composition must crop well into wide hero and tall login panel. Only stadium signage and flag text are permitted. NO UI, NO website screenshot, NO buttons, NO layout panels, NO added title or tagline, NO mascot, NO watermark.

Club descriptions:

1. Manchester United, Old Trafford, iconic angular exposed steel roof and SIR ALEX FERGUSON STAND sign, red flags, red and black scarves, glowing MANCHESTER UNITED sign, warm red lighting
2. Manchester City, Etihad Stadium, sweeping modern curved roof and ETIHAD STADIUM sign, sky blue flags with Manchester City crests, cool cyan floodlights
3. Chelsea, Stamford Bridge, intimate steep stands and CHELSEA sign, royal blue flags with Chelsea lion crests, blue and white scarves reading PRIDE OF LONDON, electric royal blue lighting
4. Liverpool, Anfield, massive Kop stand and YOU'LL NEVER WALK ALONE sign, crimson Liverpool liver bird flags and red scarves, warm amber floodlights and deep red lighting
5. Arsenal, Emirates Stadium, sweeping silver curved roof and EMIRATES STADIUM sign, red and white Arsenal cannon flags, cream and gold highlights, warm champagne floodlights

## Verification

25 tests across 9 files passed, including selection of the nearest upcoming fixture and league ordering. Typecheck and formatting passed. All generated images were visually inspected. Full browser visual/responsive verification has not been performed; this is not a claim of pixel-perfect reproduction.
