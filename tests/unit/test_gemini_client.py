"""
Unit tests for GeminiClient.

Tests the Gemini AI client for link extraction and script generation,
with comprehensive mocking of the Google Generative AI SDK.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_flow.clients.gemini_client import GeminiClient
from reddit_flow.exceptions import AIGenerationError, ConfigurationError
from reddit_flow.models import LinkInfo, VideoScript

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_genai():
    """Mock the google.generativeai module."""
    with patch("reddit_flow.clients.gemini_client.genai") as mock:
        mock_model = MagicMock()
        mock.GenerativeModel.return_value = mock_model
        yield mock


@pytest.fixture
def gemini_config():
    """Valid Gemini client configuration."""
    return {
        "api_key": "test-api-key",
        "model": "gemini-2.5-flash-lite",
        "max_words": 500,
        "max_comments": 50,
    }


@pytest.fixture
def gemini_client(mock_genai, gemini_config):
    """Create a GeminiClient with mocked dependencies."""
    return GeminiClient(config=gemini_config)


@pytest.fixture
def sample_link_response():
    """Sample AI response for link extraction."""
    return {
        "link": "https://www.reddit.com/r/Python/comments/abc123/test_post/",
        "subReddit": "Python",
        "postId": "abc123",
        "text": "Check this out!",
    }


@pytest.fixture
def sample_script_response():
    """Sample AI response for script generation."""
    return {
        "script": "This is an engaging script about Python programming. "
        "Let me tell you about this amazing discovery. "
        "The community has spoken and here is what they think.",
        "title": "Python Community Discovers Something Amazing",
    }


# =============================================================================
# Initialization Tests
# =============================================================================


class TestGeminiClientInitialization:
    """Tests for GeminiClient initialization."""

    def test_init_with_config(self, mock_genai, gemini_config):
        """Test initialization with explicit config."""
        client = GeminiClient(config=gemini_config)

        assert client.is_initialized
        assert client.service_name == "Gemini"
        mock_genai.configure.assert_called_once_with(api_key="test-api-key")
        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.5-flash-lite")

    def test_init_with_env_vars(self, mock_genai, monkeypatch):
        """Test initialization using environment variables."""
        monkeypatch.setenv("GOOGLE_API_KEY", "env-api-key")

        client = GeminiClient()

        assert client.is_initialized
        mock_genai.configure.assert_called_once_with(api_key="env-api-key")

    def test_init_missing_api_key_raises_error(self, mock_genai, monkeypatch):
        """Test that missing API key raises ConfigurationError."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            GeminiClient(config={})

        assert "API key not found" in str(exc_info.value)

    def test_init_with_default_model(self, mock_genai, monkeypatch):
        """Test initialization uses default model when not specified."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = GeminiClient()

        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.5-flash-lite")
        assert client.max_words == GeminiClient.DEFAULT_MAX_WORDS
        assert client.max_comments == GeminiClient.DEFAULT_MAX_COMMENTS

    def test_init_with_custom_settings(self, mock_genai):
        """Test initialization with custom max_words and max_comments."""
        config = {
            "api_key": "test-key",
            "model": "gemini-pro",
            "max_words": 750,
            "max_comments": 100,
        }

        client = GeminiClient(config=config)

        assert client.max_words == 750
        assert client.max_comments == 100
        mock_genai.GenerativeModel.assert_called_once_with("gemini-pro")

    def test_init_sdk_error_raises_ai_generation_error(self, mock_genai):
        """Test that SDK initialization errors are wrapped in AIGenerationError."""
        mock_genai.configure.side_effect = Exception("SDK initialization failed")

        with pytest.raises(AIGenerationError) as exc_info:
            GeminiClient(config={"api_key": "test-key"})

        assert "initialization failed" in str(exc_info.value)


# =============================================================================
# Health Check Tests
# =============================================================================


class TestGeminiClientHealthCheck:
    """Tests for GeminiClient health check."""

    def test_health_check_success(self, gemini_client):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.text = "ok"
        gemini_client.model.generate_content.return_value = mock_response

        result = gemini_client._health_check()

        assert result is True
        gemini_client.model.generate_content.assert_called_once_with("Say 'ok'")

    def test_health_check_failure(self, gemini_client):
        """Test health check failure."""
        gemini_client.model.generate_content.side_effect = Exception("API error")

        result = gemini_client._health_check()

        assert result is False

    def test_health_check_empty_response(self, gemini_client):
        """Test health check with empty response."""
        mock_response = MagicMock()
        mock_response.text = None
        gemini_client.model.generate_content.return_value = mock_response

        result = gemini_client._health_check()

        assert result is False


# =============================================================================
# Link Extraction Tests
# =============================================================================


class TestGeminiClientExtractLinkInfo:
    """Tests for extract_link_info method."""

    @pytest.mark.asyncio
    async def test_extract_link_info_returns_model(self, gemini_client, sample_link_response):
        """Test that extract_link_info returns a LinkInfo model."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_link_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.extract_link_info(
            "Check this out! https://www.reddit.com/r/Python/comments/abc123/"
        )

        assert isinstance(result, LinkInfo)
        assert result.link == sample_link_response["link"]
        assert result.subreddit == sample_link_response["subReddit"]
        assert result.post_id == sample_link_response["postId"]
        assert result.user_text == sample_link_response["text"]

    @pytest.mark.asyncio
    async def test_extract_link_info_cleans_markdown(self, gemini_client, sample_link_response):
        """Test that markdown code blocks are cleaned from response."""
        mock_response = AsyncMock()
        mock_response.text = f"```json\n{json.dumps(sample_link_response)}\n```"
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.extract_link_info("test message")

        assert isinstance(result, LinkInfo)
        assert result.subreddit == "Python"

    @pytest.mark.asyncio
    async def test_extract_link_info_null_user_text(self, gemini_client):
        """Test handling of null user text in response."""
        response_data = {
            "link": "https://reddit.com/r/test/comments/123/",
            "subReddit": "test",
            "postId": "123",
            "text": None,
        }
        mock_response = AsyncMock()
        mock_response.text = json.dumps(response_data)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.extract_link_info("test message")

        assert result.user_text is None

    @pytest.mark.asyncio
    async def test_extract_link_info_missing_fields_raises_error(self, gemini_client):
        """Test that missing required fields raise AIGenerationError."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps({"link": "https://reddit.com"})
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.extract_link_info("test message")

        assert "Missing required fields" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_link_info_invalid_json_raises_error(self, gemini_client):
        """Test that invalid JSON raises AIGenerationError."""
        mock_response = AsyncMock()
        mock_response.text = "This is not JSON"
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.extract_link_info("test message")

        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_link_info_api_error_raises_error(self, gemini_client):
        """Test that API errors are wrapped in AIGenerationError."""
        gemini_client.model.generate_content_async = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.extract_link_info("test message")

        assert "Failed to extract link information" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_link_info_dict_returns_dict(self, gemini_client, sample_link_response):
        """Test backward-compatible dict method."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_link_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.extract_link_info_dict("test message")

        assert isinstance(result, dict)
        assert result["link"] == sample_link_response["link"]
        assert result["subReddit"] == sample_link_response["subReddit"]
        assert result["postId"] == sample_link_response["postId"]


# =============================================================================
# Script Generation Tests
# =============================================================================


class TestGeminiClientGenerateScript:
    """Tests for generate_script method."""

    @pytest.mark.asyncio
    async def test_generate_script_returns_model(self, gemini_client, sample_script_response):
        """Test that generate_script returns a VideoScript model."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_script_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate_script(
            post_text="This is a test post",
            comments_data=[{"body": "Great post!", "score": 100}],
        )

        assert isinstance(result, VideoScript)
        assert result.script == sample_script_response["script"]
        assert result.title == sample_script_response["title"]

    @pytest.mark.asyncio
    async def test_generate_script_with_metadata(self, gemini_client, sample_script_response):
        """Test script generation with source metadata."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_script_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate_script(
            post_text="Test post",
            comments_data=[],
            user_opinion="This is interesting",
            source_post_id="abc123",
            source_subreddit="Python",
        )

        assert result.source_post_id == "abc123"
        assert result.source_subreddit == "Python"
        assert result.user_opinion == "This is interesting"

    @pytest.mark.asyncio
    async def test_generate_script_limits_comments(self, gemini_client, sample_script_response):
        """Test that comments are limited to max_comments."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_script_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        # Create more comments than the limit
        comments = [{"body": f"Comment {i}", "score": i} for i in range(100)]

        await gemini_client.generate_script(
            post_text="Test",
            comments_data=comments,
        )

        # Verify the prompt was called
        call_args = gemini_client.model.generate_content_async.call_args
        prompt = call_args[0][0]
        # The prompt should only contain max_comments worth of comments
        assert f"Comment {gemini_client.max_comments}" not in prompt

    @pytest.mark.asyncio
    async def test_generate_script_missing_script_raises_error(self, gemini_client):
        """Test that missing script field raises AIGenerationError."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps({"title": "Only Title"})
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.generate_script(post_text="Test", comments_data=[])

        assert "Missing script or title" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_script_missing_title_raises_error(self, gemini_client):
        """Test that missing title field raises AIGenerationError."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps({"script": "Only Script"})
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.generate_script(post_text="Test", comments_data=[])

        assert "Missing script or title" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_script_invalid_json_raises_error(self, gemini_client):
        """Test that invalid JSON raises AIGenerationError."""
        mock_response = AsyncMock()
        mock_response.text = "Not valid JSON at all"
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.generate_script(post_text="Test", comments_data=[])

        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_script_api_error_raises_error(self, gemini_client):
        """Test that API errors are wrapped in AIGenerationError."""
        gemini_client.model.generate_content_async = AsyncMock(
            side_effect=Exception("Model quota exceeded")
        )

        with pytest.raises(AIGenerationError) as exc_info:
            await gemini_client.generate_script(post_text="Test", comments_data=[])

        assert "Failed to generate script" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_script_dict_returns_dict(self, gemini_client, sample_script_response):
        """Test backward-compatible dict method."""
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_script_response)
        gemini_client.model.generate_content_async = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate_script_dict(
            post_text="Test",
            comments_data=[],
        )

        assert isinstance(result, dict)
        assert "script" in result
        assert "title" in result


# =============================================================================
# JSON Cleaning Tests
# =============================================================================


class TestCleanJsonResponse:
    """Tests for _clean_json_response static method."""

    def test_clean_json_code_block(self):
        """Test cleaning ```json code blocks."""
        text = '```json\n{"key": "value"}\n```'
        result = GeminiClient._clean_json_response(text)
        assert result == '{"key": "value"}'

    def test_clean_plain_code_block(self):
        """Test cleaning plain ``` code blocks."""
        text = '```\n{"key": "value"}\n```'
        result = GeminiClient._clean_json_response(text)
        assert result == '{"key": "value"}'

    def test_clean_no_code_block(self):
        """Test that clean JSON passes through."""
        text = '{"key": "value"}'
        result = GeminiClient._clean_json_response(text)
        assert result == '{"key": "value"}'

    def test_clean_strips_whitespace(self):
        """Test that whitespace is stripped."""
        text = '  \n{"key": "value"}\n  '
        result = GeminiClient._clean_json_response(text)
        assert result == '{"key": "value"}'


# =============================================================================
# Prompt Building Tests
# =============================================================================


class TestPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_link_extraction_prompt(self, gemini_client):
        """Test link extraction prompt contains message."""
        message = "Check out this post: https://reddit.com/r/test/comments/123/"
        prompt = gemini_client._build_link_extraction_prompt(message)

        assert message in prompt
        assert "link" in prompt
        assert "subReddit" in prompt
        assert "postId" in prompt
        assert "JSON" in prompt

    def test_build_script_generation_prompt(self, gemini_client):
        """Test script generation prompt contains all inputs."""
        post_text = "This is the post content"
        comments = [{"body": "Great!", "score": 100}]
        user_opinion = "I think this is interesting"

        prompt = gemini_client._build_script_generation_prompt(post_text, comments, user_opinion)

        assert post_text in prompt
        assert "Great!" in prompt
        assert user_opinion in prompt
        assert str(gemini_client.max_words) in prompt
        assert "script" in prompt.lower()
        assert "title" in prompt.lower()

    def test_build_script_prompt_handles_none_opinion(self, gemini_client):
        """Test script prompt handles None user opinion."""
        prompt = gemini_client._build_script_generation_prompt("Post", [], None)

        assert "None provided" in prompt


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestGeminiClientIntegration:
    """Integration-style tests for the full workflow."""

    @pytest.mark.asyncio
    async def test_full_extraction_to_script_workflow(
        self, gemini_client, sample_link_response, sample_script_response
    ):
        """Test complete workflow from link extraction to script generation."""
        # Setup mock responses
        link_mock = AsyncMock()
        link_mock.text = json.dumps(sample_link_response)

        script_mock = AsyncMock()
        script_mock.text = json.dumps(sample_script_response)

        gemini_client.model.generate_content_async = AsyncMock(side_effect=[link_mock, script_mock])

        # Extract link info
        link_info = await gemini_client.extract_link_info(
            "https://reddit.com/r/Python/comments/abc123/"
        )

        # Generate script using extracted info
        script = await gemini_client.generate_script(
            post_text="Test post content",
            comments_data=[{"body": "Test comment", "score": 10}],
            source_post_id=link_info.post_id,
            source_subreddit=link_info.subreddit,
        )

        assert link_info.subreddit == "Python"
        assert script.source_subreddit == "Python"
        assert script.source_post_id == "abc123"
        assert script.word_count > 0
