export type Pick = {
  rank: number;
  player: string;
  team: string;
  stat: string;
  direction: "OVER" | "UNDER";
  line: number;
  hitProb: number; // 0–100
};

export const PICKS: Pick[] = [
  {
    rank: 1,
    player: "Cason Wallace",
    team: "OKC",
    stat: "PRA",
    direction: "OVER",
    line: 14.5,
    hitProb: 85,
  },
  {
    rank: 2,
    player: "Jaylen Brown",
    team: "BOS",
    stat: "REB",
    direction: "OVER",
    line: 6.5,
    hitProb: 80,
  },
  {
    rank: 3,
    player: "Jamal Murray",
    team: "DEN",
    stat: "REB",
    direction: "OVER",
    line: 3.5,
    hitProb: 74,
  },
  {
    rank: 4,
    player: "Derrick White",
    team: "BOS",
    stat: "REB",
    direction: "OVER",
    line: 3.5,
    hitProb: 73,
  },
  {
    rank: 5,
    player: "Tobias Harris",
    team: "DET",
    stat: "REB",
    direction: "OVER",
    line: 5.5,
    hitProb: 73,
  },
];

export const DATE_LABEL = "FEB 27, 2026";
