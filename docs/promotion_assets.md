# NBA Prop Evaluator (Bettin'Jrys) - Promotion Assets

This document contains swipe copy and strategy for launching and promoting the NBA Prop Evaluator app across various platforms.

---

## 🚀 1. Reddit Strategy

**Target Subreddits:** `r/sportsbetting`, `r/dfsports`, `r/machinelearning`, `r/SideProject`
**Goal:** Provide genuine value, explain the core mechanism (it's not just another random tout or pick-seller), and invite beta testers. Do *not* sound like a marketer.

### Post Draft for `r/sportsbetting`
**Title:** I got tired of paying for picks and using "gut feeling", so I built an ML model (Random Forest) to evaluate NBA player props. Here's what I learned.

**Body:**
Hey everyone, 

Like a lot of you, I've been trying to find a true edge in player props. Most tout services are throwing darts, and manual research takes hours every single day. 

I have a background in data/dev, so over the last few months, I built an evaluation tool that pulls the last 2-3 seasons of game logs, parses injury reports, and runs matchups through a Random Forest model to predict player performance. It then grabs current lines and calculates Expected Value (EV+) and provides a confidence rating (Low/Moderate/Strong). 

**The interesting part:** The model completely ignores narratives. It flagged that certain players consistently over-perform against specific defensive schemes on the second night of back-to-backs—stuff I would never catch manually.

I just deployed a web interface for it called *Bettin'Jrys*. It's 100% free right now (no paywalls, no Discord VIP groups to join). I am mainly looking for feedback from people who bet daily to tell me if the UI is actually useful for your workflow. 

**Link:** [Insert Link Here]

Let me know what you think, or if there's a specific stat/trend you want me to try and build into the model.

---

## 🐦 2. Twitter / X Strategy

**Target Audience:** Sports bettors, Data Nerds, NBA Twitter
**Format:** "Pick of the Day" threads featuring data visualizations. 

### Core Tweet Template (Daily Game Day)
🚨 **AI Prop of the Day** 🚨

Our ML model is flagging huge value on **[Player Name] OVER [Value] [Stat]** tonight vs. [Opponent].

🧠 **The Data:**
- Model Prediction: [Prediction Number]
- Line: [Line Number]
- Edge: [Percentage Edge]% ROI
- Confidence: 🟢 STRONG

The model loves this matchup because [Player] averages [X] vs [Opponent] without [Injured Teammate]. 

Check out the full breakdown and more predictions for tonight's slate: [Link]

#NBAPicks #SportsBetting #MachineLearning #PlayerProps

---

## 🦄 3. Product Hunt / IndieHackers Launch

**Tagline:** Bettin'Jrys - Beat the sportsbooks using Machine Learning. 
**Description:** Stop betting with your gut. Bettin'Jrys uses Random Forest models, historical matchups, and injury data to calculate Expected Value (EV+) for NBA player props. 100% free, purely data-driven insights.

### Launch Comment Draft (Maker's Comment)
Hey everyone! 👋

I'm excited to share Bettin'Jrys with you all. As a casual sports fan and a developer, I was always annoyed by how much "sports betting advice" is just people guessing based on recency bias. 

I wanted to know what the *math* actually said. So, I built Bettin'Jrys.

It pulls in live NBA data, schedule, rest-days, injury reports, and matchup history, and runs it all through multiple ML models (Random Forest, Gradient Boosting) to project what a player will actually do. Then, it compares that projection to live sportsbook lines to find where the books might be wrong.

**Key Features:**
- 🧠 **ML Predictions:** Not just averages. The model weighs rolling trends, variance, and rest days.
- 🎯 **Line Evaluation:** Instantly see if a bet is "Over" or "Under" valued and the statistical confidence.
- 📊 **Historical Context:** See exactly *why* the model made its choice based on opponent history.

I'd love your feedback on the UI and the data presentation! Are there specific metrics you look for when analyzing sports data that are missing? Let me know below! 👇
