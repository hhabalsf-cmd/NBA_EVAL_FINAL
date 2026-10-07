"""Tests for Supabase JWT verification."""
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock

SUPABASE_JWT_SECRET = "test-supabase-jwt-secret-that-is-long-enough-32ch"

def test_decode_supabase_token_returns_user_id():
    from api.auth_utils import decode_access_token
    client = Mock()
    client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='user-uuid-123', email='test@example.com'))
    with patch('api.auth_utils._get_admin_client', return_value=client):
        payload = decode_access_token('test-token')
    client.auth.get_user.assert_called_once_with('test-token')
    assert payload["sub"] == "user-uuid-123"
    assert payload["email"] == "test@example.com"


@pytest.mark.parametrize('response', [None, SimpleNamespace(user=None)])
def test_decode_invalid_token_raises(response):
    from api.auth_utils import decode_access_token
    client = Mock()
    client.auth.get_user.return_value = response
    with patch('api.auth_utils._get_admin_client', return_value=client):
        with pytest.raises(ValueError):
            decode_access_token("not.a.valid.token")


def test_auth_provider_failure_is_not_accepted():
    from api.auth_utils import decode_access_token
    client = Mock()
    client.auth.get_user.side_effect = ConnectionError('provider offline')
    with patch('api.auth_utils._get_admin_client', return_value=client), pytest.raises(ConnectionError):
        decode_access_token('unverifiable-token')
