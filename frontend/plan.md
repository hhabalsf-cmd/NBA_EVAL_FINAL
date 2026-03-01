# NBA Eval Frontend Improvements Plan

## Goal Description
Enhance the design and user experience of the NBA Eval React/Tailwind frontend. The goal is to make the app feel like a premium, modern sports analytics product. Focus areas include advanced data visualization, micro-interactions, layout restructuring, and visual polish.

## Proposed UX/UI Improvements

1. **Modern Data Visualization (Charts/Graphs):**
   - Integrate a charting library like `recharts` to visually display player performance trends over the last 10-15 games.
   - Show trend lines, moving averages, and confidence intervals next to the raw predictions.
   - Replace static text stats with visual gauges for "hit rate" and "confidence".

2. **Micro-Interactions & Animations (Framer Motion):**
   - Add `framer-motion` for smooth page transitions between the Home, Games, and Research tabs.
   - Implement staggered entrance animations for stat cards and lists.
   - Add satisfying click effects and hover states (e.g., slight scaling and glow effects) to primary buttons and "Over/Under" pills.

3. **Information Hierarchy & Bento Box Layouts:**
   - Redesign the `PlayerPage` and `ResearchPage` using a modern "Bento Box" grid layout.
   - Ensure the AI's primary verdict (Over/Under) is the focal point, with supporting data (recent form, matchup stats, defensive rankings) surrounding it in distinct spatial zones.
   - Use better typography scaling (already using JetBrains Mono for numbers, but size and weight contrast can be increased).

4. **Visual Polish & Theming:**
   - Enhance the existing Dark mode with subtle glassmorphism (`backdrop-blur`) on cards and floating elements.
   - Use dynamic gradients based on the team's colors or the prediction's confidence level (e.g., a green gradient border for a 90% confidence "Over").
   - Improve the empty states and loading skeletons (replace standard spinners with pulsing skeleton screens or basketball-themed loaders).

5. **Mobile Experience Optimization:**
   - Ensure the mobile bottom navigation is perfectly spaced and includes haptic feedback cues (if feasible) or visual ripple effects on tap.
   - Implement swipeable cards for moving between different player props quickly.

## Execution Strategy (via Claude Code)
Since the request asks to pass the coding work to the `claude` terminal, the plan is to invoke the `claude` CLI from the frontend directory with a comprehensive prompt containing these exact design requirements.

## Verification Plan
### Automated Tests
- Run `npm run build` to ensure the new dependencies (`framer-motion`, `recharts`, etc.) are installed correctly and compile without TypeScript errors.

### Manual Verification
- Start the Vite dev server and open the browser to visually verify:
  1. The new charts render on the player and research pages.
  2. The Framer Motion animations trigger properly on mount and interaction.
  3. The layout adjusts correctly for both mobile and desktop breakpoints.
