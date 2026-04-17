import { loadFont } from "@remotion/google-fonts/Inter";

// ── Colors ────────────────────────────────────────────────────────────────────
export const GOLD = "#C9A87C";
export const BG = "#09090B";
export const CARD_BG = "#131316";
export const WHITE = "#EDEDEC";
export const MUTED = "#8F8B87";
export const GREEN = "#6BBF8A";
export const CYAN = "#06B6D4";
export const BORDER = "#232329";
export const RED = "#D4736E";

// ── Font ──────────────────────────────────────────────────────────────────────
const { fontFamily: interFamily } = loadFont("normal", {
  weights: ["400", "700", "900"],
  subsets: ["latin"],
});
export const fontFamily = interFamily;

// ── Spring Presets ────────────────────────────────────────────────────────────
export const SPRING_SMOOTH = { damping: 200 };
export const SPRING_SNAPPY = { damping: 18, stiffness: 120 };
export const SPRING_BOUNCY = { damping: 12, stiffness: 200 };
