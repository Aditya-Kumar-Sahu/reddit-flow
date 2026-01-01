"""
Sample unit test to verify pytest infrastructure is working.

This file serves as a template for future unit tests and validates
that the testing infrastructure is properly configured.
"""

import pytest


class TestPytestInfrastructure:
    """Tests to verify pytest is configured correctly."""

    @pytest.mark.unit
    def test_basic_assertion(self):
        """Verify basic test assertions work."""
        assert True

    @pytest.mark.unit
    def test_fixture_available(self, sample_reddit_post):
        """Verify fixtures from conftest.py are available."""
        assert "title" in sample_reddit_post
        assert "comments" in sample_reddit_post
        assert len(sample_reddit_post["comments"]) > 0

    @pytest.mark.unit
    def test_mock_env_vars(self, mock_env_vars):
        """Verify mock environment variables are set."""
        import os
        assert os.getenv("TELEGRAM_BOT_TOKEN") == "test_telegram_token"
        assert os.getenv("REDDIT_CLIENT_ID") == "test_reddit_client_id"

    @pytest.mark.unit
    def test_temp_directory(self, temp_directory):
        """Verify temporary directory fixture works."""
        assert temp_directory.exists()
        test_file = temp_directory / "test.txt"
        test_file.write_text("test content")
        assert test_file.read_text() == "test content"

    @pytest.mark.unit
    def test_sample_data_fixtures(self, sample_script_data, sample_link_info):
        """Verify all sample data fixtures are available."""
        assert "script" in sample_script_data
        assert "title" in sample_script_data
        assert "link" in sample_link_info
        assert "subReddit" in sample_link_info


class TestAsyncSupport:
    """Tests to verify async test support is working."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_function(self):
        """Verify async tests work correctly."""
        import asyncio
        await asyncio.sleep(0.01)
        assert True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_mock(self):
        """Verify async mocking works correctly."""
        from unittest.mock import AsyncMock
        
        mock_func = AsyncMock(return_value="mocked_result")
        result = await mock_func()
        
        assert result == "mocked_result"
        mock_func.assert_called_once()


class TestMarkers:
    """Tests to verify pytest markers are configured."""

    @pytest.mark.unit
    def test_unit_marker(self):
        """This test has the unit marker."""
        assert True

    @pytest.mark.slow
    def test_slow_marker(self):
        """This test has the slow marker (can be skipped with -m 'not slow')."""
        assert True
