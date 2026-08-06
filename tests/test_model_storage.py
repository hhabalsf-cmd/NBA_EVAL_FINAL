"""Tests for model_storage — storage keys and failure behavior (client mocked)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import model_storage


def _mock_bucket():
    """Patch the storage client; returns the mock bucket object."""
    bucket = MagicMock()
    client = MagicMock()
    client.storage.from_.return_value = bucket
    return bucket, patch.object(model_storage, "_get_storage_client", return_value=client)


@pytest.mark.unit
class TestUploadDownload:
    def test_player_upload_uses_players_prefix(self, tmp_path):
        f = tmp_path / "LeBron_James_model.pkl"
        f.write_bytes(b"pickle-bytes")
        bucket, patcher = _mock_bucket()
        with patcher:
            assert model_storage.upload_player_model("LeBron James", f) is True
        kwargs = bucket.upload.call_args.kwargs
        assert kwargs["path"] == "players/LeBron_James_model.pkl"
        assert kwargs["file"] == b"pickle-bytes"
        assert kwargs["file_options"]["upsert"] == "true"

    def test_game_upload_uses_games_prefix(self, tmp_path):
        f = tmp_path / "game_predictor.pkl"
        f.write_bytes(b"x")
        bucket, patcher = _mock_bucket()
        with patcher:
            assert model_storage.upload_game_model(f) is True
        assert bucket.upload.call_args.kwargs["path"] == "games/game_predictor.pkl"

    def test_download_writes_file_and_creates_dirs(self, tmp_path):
        target = tmp_path / "nested" / "LeBron_James_model.pkl"
        bucket, patcher = _mock_bucket()
        bucket.download.return_value = b"model-bytes"
        with patcher:
            assert model_storage.download_player_model("LeBron James", target) is True
        assert target.read_bytes() == b"model-bytes"
        bucket.download.assert_called_once_with("players/LeBron_James_model.pkl")

    def test_download_404_returns_false_without_file(self, tmp_path):
        target = tmp_path / "Missing_model.pkl"
        bucket, patcher = _mock_bucket()
        bucket.download.side_effect = Exception("Object not_found: 404")
        with patcher:
            assert model_storage.download_player_model("Missing", target) is False
        assert not target.exists()

    def test_upload_failure_returns_false(self, tmp_path):
        f = tmp_path / "X_model.pkl"
        f.write_bytes(b"x")
        bucket, patcher = _mock_bucket()
        bucket.upload.side_effect = Exception("network down")
        with patcher:
            assert model_storage.upload_player_model("X", f) is False

    def test_upload_missing_local_file_returns_false(self, tmp_path):
        bucket, patcher = _mock_bucket()
        with patcher:
            assert model_storage.upload_player_model("X", tmp_path / "nope.pkl") is False


@pytest.mark.unit
class TestListPlayerModels:
    def test_lists_pkl_names_only(self):
        bucket, patcher = _mock_bucket()
        bucket.list.return_value = [
            {"name": "A_model.pkl"}, {"name": "B_model.pkl"}, {"name": ".emptyFolderPlaceholder"},
        ]
        with patcher:
            assert model_storage.list_player_models() == ["A_model.pkl", "B_model.pkl"]

    def test_empty_on_error(self):
        bucket, patcher = _mock_bucket()
        bucket.list.side_effect = Exception("boom")
        with patcher:
            assert model_storage.list_player_models() == []
