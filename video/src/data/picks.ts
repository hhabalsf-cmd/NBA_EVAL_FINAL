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
    player: "Kevin Durant",
    team: "PHX",
    stat: "PA",
    direction: "OVER",
    line: 30.5,
    hitProb: 80,
    opponent: "vs. MEM · Weak DEF",
  },
  {
    rank: 2,
    player: "Bilal Coulibaly",
    team: "WAS",
    stat: "PRA",
    direction: "OVER",
    line: 15.5,
    hitProb: 78,
    opponent: "vs. CHI · Average DEF",
  },
  {
    rank: 3,
    player: "Kawhi Leonard",
    team: "LAC",
    stat: "PR",
    direction: "OVER",
    line: 34.5,
    hitProb: 76,
    opponent: "vs. ORL · Average DEF",
  },
  {
    rank: 4,
    player: "Brandin Podziemski",
    team: "GSW",
    stat: "PA",
    direction: "OVER",
    line: 10.5,
    hitProb: 74,
    opponent: "vs. NOP · Weak DEF",
  },
];

export const DATE_LABEL = new Date()
  .toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" })
  .toUpperCase()
  .replace(",", "");
