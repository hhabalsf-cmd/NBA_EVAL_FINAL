import sys
import os
from pathlib import Path

# Add project root to path so we can import nba_evaluator
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from nba_evaluator import find_best_bets

def format_twitter_post(bets):
    """Formats the list of best bets into a Twitter thread or text."""
    if not bets:
        return "No high-confidence props found today. The ML model is sitting this one out! 🤖📈\n#NBAPicks #SportsBetting"

    post_lines = ["🚨 **AI Props of the Day** 🚨\n"]
    post_lines.append("Our Gradient Boosting model has processed today's slate and found massive edge on these plays:\n")

    for i, bet in enumerate(bets[:4], 1):
        direction_emoji = "🟢" if bet['direction'] == "OVER" else "🔴"
        edge_indicator = "🔥" if bet['edge'] > 15 else ("⭐" if bet['edge'] > 10 else "📈")
        
        post_lines.append(f"{i}. **{bet['player']} {bet['direction']} {bet['line']} {bet['stat']}** {direction_emoji}")
        post_lines.append(f"   Model Projection: {bet['prediction']}")
        post_lines.append(f"   Calculated Edge: {bet['edge']:.1f}% {edge_indicator}")
        post_lines.append(f"   Matchup: vs {bet['opponent']} ({'Home' if bet['is_home'] else 'Away'})\n")

    post_lines.append("These picks are 100% data-driven, filtering out injury/rest variables and historical matchup data.")
    post_lines.append("Build the edge and beat the books. 💰\n\n#NBAPicks #SportsBetting #MachineLearning #PlayerProps")
    
    return "\n".join(post_lines)

def main():
    print("Running ML evaluator to find top 4 picks for today...")
    
    # We set min_edge to a reasonable number to get quality picks, and max_results to 4.
    bets = find_best_bets(min_edge=7.0, max_edge=45.0, max_results=4, select_games=False)
    
    formatted_post = format_twitter_post(bets)
    
    # Save to a file so the browser subagent (or user) can easily read it
    output_path = project_root / "daily_picks_post.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(formatted_post)
    
    print(f"\n✅ Generated post saved to {output_path}")
    print("\n--- PREVIEW ---\n")
    print(formatted_post)
    print("\n---------------")

if __name__ == "__main__":
    main()
