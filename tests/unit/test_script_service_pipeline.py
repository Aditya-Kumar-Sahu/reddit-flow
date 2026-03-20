"""Unit tests for generic script generation from canonical content."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from reddit_flow.exceptions import ContentError
from reddit_flow.models import ContentItem, VideoScript
from reddit_flow.services.script_service import ScriptService


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client."""
    client = MagicMock()
    client.generate_script = AsyncMock()
    return client


@pytest.fixture
def script_service(mock_gemini_client, mock_prod_settings):
    """Create a ScriptService with a mocked Gemini client."""
    return ScriptService(
        gemini_client=mock_gemini_client,
        max_words=250,
        max_comments=10,
        settings=mock_prod_settings,
    )


class TestGenerateScriptFromContentItem:
    """Tests for generic content-item script generation."""

    @pytest.mark.asyncio
    async def test_generate_script_from_content_item_success(
        self, script_service, mock_gemini_client
    ):
        """Canonical content should generate a script without Reddit-specific models."""
        mock_gemini_client.generate_script.return_value = VideoScript(
            script="A polished short-form script.",
            title="A Medium Story",
            source_post_id="story-123",
            source_subreddit="medium_article",
        )
        content_item = ContentItem(
            source_type="medium_article",
            source_id="story-123",
            source_url="https://medium.com/@writer/story-123",
            title="A Medium Story",
            body="A short article body.",
            comments=[{"body": "Useful", "author": "reader1", "score": 10}],
        )

        result = await script_service.generate_script_from_content_item(content_item)

        assert result.title == "A Medium Story"
        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert call_kwargs["post_text"] == "A Medium Story\n\nA short article body."
        assert call_kwargs["source_post_id"] == "story-123"
        assert call_kwargs["source_subreddit"] == "medium_article"
        assert len(call_kwargs["comments_data"]) == 1

    @pytest.mark.asyncio
    async def test_generate_script_from_content_item_empty_content_raises_error(
        self, script_service
    ):
        """Canonical content with no text should fail cleanly."""
        content_item = ContentItem(
            source_type="medium_article",
            source_id="story-123",
            source_url="https://medium.com/@writer/story-123",
            title="",
            body="",
        )

        with pytest.raises(ContentError, match="no content to generate"):
            await script_service.generate_script_from_content_item(content_item)
