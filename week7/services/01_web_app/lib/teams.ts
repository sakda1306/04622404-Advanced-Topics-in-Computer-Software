export const teams = [
  {
    key: "manchester-united",
    name: "Manchester United",
    shortName: "Man United",
    initials: "MU",
    teamId: 66,
    mascot: "/mascots/manchester-united.webp",
    color: "#e9474e",
    colorBright: "#fa777c",
    glow: "233, 47, 59",
    hero: "THE RED SIDE OF FOOTBALL",
  },
  {
    key: "manchester-city",
    name: "Manchester City",
    shortName: "Man City",
    initials: "MC",
    teamId: 65,
    mascot: "/mascots/manchester-city.webp",
    color: "#00b4ff",
    colorBright: "#9ce4ff",
    glow: "0, 180, 255",
    hero: "PAINT THE CITY BLUE",
  },
  {
    key: "chelsea",
    name: "Chelsea",
    shortName: "Chelsea",
    initials: "CH",
    teamId: 61,
    mascot: "/mascots/chelsea.webp",
    color: "#5579ff",
    colorBright: "#9bb2ff",
    glow: "46, 91, 245",
    hero: "BLUE IS THE COLOUR",
  },
  {
    key: "liverpool",
    name: "Liverpool",
    shortName: "Liverpool",
    initials: "LIV",
    teamId: 64,
    mascot: "/mascots/liverpool.webp",
    color: "#e84a55",
    colorBright: "#ff8c91",
    glow: "204, 41, 58",
    hero: "YOU'LL NEVER WALK ALONE",
  },
  {
    key: "arsenal",
    name: "Arsenal",
    shortName: "Arsenal",
    initials: "ARS",
    teamId: 57,
    mascot: "/mascots/arsenal.webp",
    color: "#c6a365",
    colorBright: "#ffd89f",
    glow: "198, 163, 101",
    hero: "NORTH LONDON FOREVER",
  },
] as const;

export type TeamKey = (typeof teams)[number]["key"];
export type Team = (typeof teams)[number];

export type BrowseClub = {
  key: string;
  name: string;
  shortName: string;
  teamId: number;
};

// Browse-only clubs: viewable in the switcher, but not selectable as favorite
// (no mascot, theme colours or hero line).
const otherClubs: readonly BrowseClub[] = [
  {
    key: "aston-villa",
    name: "Aston Villa",
    shortName: "Aston Villa",
    teamId: 58,
  },
  {
    key: "bournemouth",
    name: "AFC Bournemouth",
    shortName: "Bournemouth",
    teamId: 1044,
  },
  {
    key: "brentford",
    name: "Brentford",
    shortName: "Brentford",
    teamId: 402,
  },
  {
    key: "brighton",
    name: "Brighton & Hove Albion",
    shortName: "Brighton",
    teamId: 397,
  },
  {
    key: "coventry-city",
    name: "Coventry City",
    shortName: "Coventry City",
    teamId: 1076,
  },
  {
    key: "crystal-palace",
    name: "Crystal Palace",
    shortName: "Crystal Palace",
    teamId: 354,
  },
  {
    key: "everton",
    name: "Everton",
    shortName: "Everton",
    teamId: 62,
  },
  {
    key: "fulham",
    name: "Fulham",
    shortName: "Fulham",
    teamId: 63,
  },
  {
    key: "hull-city",
    name: "Hull City",
    shortName: "Hull City",
    teamId: 322,
  },
  {
    key: "ipswich-town",
    name: "Ipswich Town",
    shortName: "Ipswich Town",
    teamId: 349,
  },
  {
    key: "leeds-united",
    name: "Leeds United",
    shortName: "Leeds United",
    teamId: 341,
  },
  {
    key: "newcastle-united",
    name: "Newcastle United",
    shortName: "Newcastle",
    teamId: 67,
  },
  {
    key: "nottingham-forest",
    name: "Nottingham Forest",
    shortName: "Nottm Forest",
    teamId: 351,
  },
  {
    key: "sunderland",
    name: "Sunderland",
    shortName: "Sunderland",
    teamId: 71,
  },
  {
    key: "tottenham",
    name: "Tottenham Hotspur",
    shortName: "Tottenham",
    teamId: 73,
  },
];

export const browseClubs: readonly BrowseClub[] = [
  ...teams.map(({ key, name, shortName, teamId }) => ({
    key,
    name,
    shortName,
    teamId,
  })),
  ...otherClubs,
];

export function teamFromId(teamId: number | null): Team | undefined {
  return teams.find((team) => team.teamId === teamId);
}
