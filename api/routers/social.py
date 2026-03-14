"""Social features: leaderboard, public profiles, follows, feed."""
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import db

from ..limiter import limiter
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["social"])

# Allowlist for leaderboard sort columns — prevents SQL injection even if
# FastAPI's query validation is bypassed or misconfigured.
_LEADERBOARD_SORT_COLS = {"win_rate": "win_rate", "roi_units": "roi_units"}


def get_optional_user(request: Request) -> Optional[dict]:
    """Return current user if authenticated, None otherwise. Never raises."""
    try:
        return get_current_user(request)
    except Exception:
        return None


# ── Schemas ────────────────────────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    user_id: str
    username: str
    avatar_url: Optional[str] = None
    total_graded: int
    total_won: int
    win_rate: float
    roi_units: float


class PublicProfile(BaseModel):
    user_id: str
    username: str
    avatar_url: Optional[str] = None
    is_public: bool
    total_graded: int = 0
    total_won: int = 0
    win_rate: float = 0.0
    roi_units: float = 0.0
    followers_count: int = 0
    following_count: int = 0
    is_following: Optional[bool] = None


class PublicPick(BaseModel):
    id: int
    player: str
    stat: str
    line: float
    prediction: float
    direction: str
    edge: float
    confidence: Optional[float] = None
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    actual_result: Optional[float] = None
    won: Optional[bool] = None
    game_date: Optional[str] = None
    model_type: Optional[str] = None


class FollowInfo(BaseModel):
    following: List[dict]
    followers: List[dict]


class FeedPick(BaseModel):
    id: int
    username: str
    avatar_url: Optional[str] = None
    player: str
    stat: str
    line: float
    prediction: float
    direction: str
    won: Optional[bool] = None
    game_date: Optional[str] = None
    timestamp: str


# ── Leaderboard ────────────────────────────────────────────────────────────────

@router.get("/leaderboard", response_model=List[LeaderboardEntry])
@limiter.limit("30/minute")
async def get_leaderboard(
    request: Request,
    sort_by: str = Query(default="win_rate", regex="^(win_rate|roi_units)$"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Return top users from the leaderboard materialized view."""
    sort_col = _LEADERBOARD_SORT_COLS.get(sort_by, "win_rate")
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, username, avatar_url, total_graded, total_won, win_rate, roi_units "
            "FROM leaderboard_view ORDER BY " + sort_col + " DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        return [
            LeaderboardEntry(
                user_id=str(r["user_id"]),
                username=r["username"],
                avatar_url=r.get("avatar_url"),
                total_graded=r["total_graded"],
                total_won=r["total_won"],
                win_rate=float(r["win_rate"]),
                roi_units=float(r["roi_units"]),
            )
            for r in rows
        ]
    finally:
        db.put_connection(conn)


# ── Public Profiles ────────────────────────────────────────────────────────────

@router.get("/users/{username}/profile", response_model=PublicProfile)
@limiter.limit("30/minute")
async def get_public_profile(
    request: Request,
    username: str,
    current_user: Optional[dict] = Depends(get_optional_user),
):
    """Get a user's public profile with stats."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()

        # Fetch profile
        cur.execute(
            "SELECT id, username, avatar_url, is_public FROM profiles WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        profile_id, uname, avatar_url, is_public = row

        if not is_public:
            return PublicProfile(
                user_id=str(profile_id),
                username=uname,
                avatar_url=avatar_url,
                is_public=False,
            )

        # Aggregate pick stats
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE won IS NOT NULL) AS total_graded,
                COUNT(*) FILTER (WHERE won = 1) AS total_won,
                ROUND(
                    COUNT(*) FILTER (WHERE won = 1)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE won IS NOT NULL), 0) * 100, 1
                ) AS win_rate,
                ROUND(
                    SUM(CASE WHEN won = 1 THEN 1.0 WHEN won = 0 THEN -1.1 ELSE 0 END)::numeric, 2
                ) AS roi_units
            FROM picks
            WHERE user_id = %s AND voided = 0
            """,
            (str(profile_id),),
        )
        stats_row = cur.fetchone()
        total_graded = stats_row[0] or 0
        total_won = stats_row[1] or 0
        win_rate = float(stats_row[2] or 0)
        roi_units = float(stats_row[3] or 0)

        # Follower / following counts
        cur.execute("SELECT COUNT(*) FROM follows WHERE followed_id = %s", (str(profile_id),))
        followers_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM follows WHERE follower_id = %s", (str(profile_id),))
        following_count = cur.fetchone()[0]

        # Is the current user following this profile?
        is_following = None
        if current_user and str(current_user["id"]) != str(profile_id):
            cur.execute(
                "SELECT 1 FROM follows WHERE follower_id = %s AND followed_id = %s",
                (str(current_user["id"]), str(profile_id)),
            )
            is_following = cur.fetchone() is not None

        return PublicProfile(
            user_id=str(profile_id),
            username=uname,
            avatar_url=avatar_url,
            is_public=True,
            total_graded=total_graded,
            total_won=total_won,
            win_rate=win_rate,
            roi_units=roi_units,
            followers_count=followers_count,
            following_count=following_count,
            is_following=is_following,
        )
    finally:
        db.put_connection(conn)


@router.get("/users/{username}/picks", response_model=List[PublicPick])
@limiter.limit("30/minute")
async def get_public_picks(
    request: Request,
    username: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=50),
):
    """Get graded picks for a public profile."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()

        # Verify public profile
        cur.execute(
            "SELECT id, is_public FROM profiles WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if not row[1]:
            raise HTTPException(status_code=403, detail="This profile is private")

        profile_id = row[0]
        offset = (page - 1) * per_page

        cur.execute(
            """
            SELECT id, player, stat, line, prediction, direction, edge, confidence,
                   opponent, is_home, actual_result, won, game_date, model_type
            FROM picks
            WHERE user_id = %s AND voided = 0 AND won IS NOT NULL
            ORDER BY game_date DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (str(profile_id), per_page, offset),
        )
        rows = cur.fetchall()

        return [
            PublicPick(
                id=r["id"],
                player=r["player"],
                stat=r["stat"],
                line=float(r["line"]),
                prediction=float(r["prediction"]),
                direction=r["direction"],
                edge=float(r["edge"]),
                confidence=float(r["confidence"]) if r.get("confidence") else None,
                opponent=r.get("opponent"),
                is_home=bool(r["is_home"]) if r.get("is_home") is not None else None,
                actual_result=float(r["actual_result"]) if r.get("actual_result") is not None else None,
                won=bool(r["won"]) if r["won"] is not None else None,
                game_date=str(r["game_date"]) if r.get("game_date") else None,
                model_type=r.get("model_type"),
            )
            for r in rows
        ]
    finally:
        db.put_connection(conn)


# ── Follows ────────────────────────────────────────────────────────────────────

@router.post("/follows/{user_id}", status_code=201)
@limiter.limit("30/minute")
async def follow_user(
    request: Request,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Follow a user."""
    if str(current_user["id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    conn = db.get_connection()
    try:
        cur = conn.cursor()

        # Verify target user exists
        cur.execute("SELECT 1 FROM profiles WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        # Check not already following
        cur.execute(
            "SELECT 1 FROM follows WHERE follower_id = %s AND followed_id = %s",
            (str(current_user["id"]), user_id),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Already following this user")

        cur.execute(
            "INSERT INTO follows (follower_id, followed_id) VALUES (%s, %s)",
            (str(current_user["id"]), user_id),
        )
        conn.commit()
        return {"status": "following"}
    finally:
        db.put_connection(conn)


@router.delete("/follows/{user_id}", status_code=200)
@limiter.limit("30/minute")
async def unfollow_user(
    request: Request,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Unfollow a user."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM follows WHERE follower_id = %s AND followed_id = %s",
            (str(current_user["id"]), user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not following this user")
        conn.commit()
        return {"status": "unfollowed"}
    finally:
        db.put_connection(conn)


@router.get("/follows", response_model=FollowInfo)
@limiter.limit("30/minute")
async def get_follows(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get who the current user follows and who follows them."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        uid = str(current_user["id"])

        # Following
        cur.execute(
            """
            SELECT p.id, p.username, p.avatar_url
            FROM follows f JOIN profiles p ON p.id = f.followed_id
            WHERE f.follower_id = %s
            ORDER BY f.created_at DESC
            """,
            (uid,),
        )
        following = [{"id": str(r[0]), "username": r[1], "avatar_url": r[2]} for r in cur.fetchall()]

        # Followers
        cur.execute(
            """
            SELECT p.id, p.username, p.avatar_url
            FROM follows f JOIN profiles p ON p.id = f.follower_id
            WHERE f.followed_id = %s
            ORDER BY f.created_at DESC
            """,
            (uid,),
        )
        followers = [{"id": str(r[0]), "username": r[1], "avatar_url": r[2]} for r in cur.fetchall()]

        return FollowInfo(following=following, followers=followers)
    finally:
        db.put_connection(conn)


# ── Feed ───────────────────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[FeedPick])
@limiter.limit("30/minute")
async def get_feed(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Get recent graded picks from followed users."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        uid = str(current_user["id"])

        cur.execute(
            """
            SELECT pk.id, p.username, p.avatar_url,
                   pk.player, pk.stat, pk.line, pk.prediction, pk.direction,
                   pk.won, pk.game_date, pk.timestamp
            FROM picks pk
            JOIN profiles p ON p.id = pk.user_id
            JOIN follows f ON f.followed_id = pk.user_id AND f.follower_id = %s
            WHERE pk.voided = 0 AND pk.won IS NOT NULL AND p.is_public = true
            ORDER BY pk.timestamp DESC
            LIMIT %s
            """,
            (uid, limit),
        )
        rows = cur.fetchall()

        return [
            FeedPick(
                id=r["id"],
                username=r["username"],
                avatar_url=r.get("avatar_url"),
                player=r["player"],
                stat=r["stat"],
                line=float(r["line"]),
                prediction=float(r["prediction"]),
                direction=r["direction"],
                won=bool(r["won"]) if r["won"] is not None else None,
                game_date=str(r["game_date"]) if r.get("game_date") else None,
                timestamp=str(r["timestamp"]),
            )
            for r in rows
        ]
    finally:
        db.put_connection(conn)
