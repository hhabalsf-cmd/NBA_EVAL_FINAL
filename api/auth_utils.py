"""JWT verification using Supabase admin client (compatible with new API keys)."""
import os
from supabase import create_client

_admin_client = None


def _get_admin_client():
    """Lazily create a Supabase admin client using the service role key."""
    global _admin_client
    if _admin_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set."
            )
        _admin_client = create_client(url, key)
    return _admin_client


def decode_access_token(token: str) -> dict:
    """Verify a Supabase-issued JWT by calling the Supabase auth API.

    Returns a dict with at least 'sub' (user id) and 'email'.
    Raises an exception on invalid/expired tokens.
    """
    client = _get_admin_client()
    user_response = client.auth.get_user(token)
    if not user_response or not user_response.user:
        raise ValueError("Invalid or expired token")
    user = user_response.user
    return {
        "sub": user.id,
        "email": user.email or "",
    }
