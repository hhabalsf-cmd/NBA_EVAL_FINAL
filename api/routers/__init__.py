"""Routers package."""
from .players import router as players_router
from .bets import router as bets_router
from .picks import router as picks_router
from .games import router as games_router
from .auth import router as auth_router
from .parlays import router as parlays_router
from .sync import router as sync_router

__all__ = ['players_router', 'bets_router', 'picks_router', 'games_router', 'auth_router', 'parlays_router', 'sync_router']
