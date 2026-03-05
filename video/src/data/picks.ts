export type Pick = {
  rank: number;
  player: string;
  team: string;
  stat: string;
  direction: "OVER" | "UNDER";
  line: number;
  hitProb: number; // 0–100
  opponent?: string; // e.g. "vs. WAS · Weak DEF"
};

export const PICKS: Pick[] = [
  {
    rank: 1,
    player: "Kris Dunn",
    team: "SAC",
    stat: "REB",
    direction: "OVER",
    line: 3.5,
    hitProb: 80,
  },
  {
    rank: 2,
    player: "Jaylen Wells",
    team: "MEM",
    stat: "PTS",
    direction: "OVER",
    line: 12.5,
    hitProb: 77,
  },
  {
    rank: 3,
    player: "Andrew Nembhard",
    team: "IND",
    stat: "REB",
    direction: "OVER",
    line: 2.5,
    hitProb: 73,
  },
  {
    rank: 4,
    player: "Deni Avdija",
    team: "POR",
    stat: "REB",
    direction: "OVER",
    line: 6.5,
    hitProb: 68,
  },
];

export const DATE_LABEL = new Date()
  .toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" })
  .toUpperCase()
  .replace(",", "");
