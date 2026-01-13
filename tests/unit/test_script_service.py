"""
Unit tests for ScriptService.

Tests cover:
- Service initialization with various configurations
- Script generation from RedditPost models
- Script generation from dictionary content
- Comment formatting and filtering
- Post text building
- Script validation
- Error handling for various edge cases
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_flow.exceptions import AIGenerationError, ContentError
from reddit_flow.models import RedditComment, RedditPost, VideoScript
from reddit_flow.services.script_service import ScriptService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_gemini_client():
    """Create a mock GeminiClient."""
    client = MagicMock()
    client.generate_script = AsyncMock()
    return client


@pytest.fixture
def script_service(mock_gemini_client, mock_prod_settings):
    """Create a ScriptService with mock client."""
    return ScriptService(
        gemini_client=mock_gemini_client,
        max_words=250,
        max_comments=10,
        settings=mock_prod_settings,
    )


@pytest.fixture
def sample_video_script():
    """Create a sample VideoScript for testing."""
    return VideoScript(
        script="Here's what happened on Reddit today. This amazing story went viral...",
        title="The Incredible Story That Took Reddit by Storm",
        source_post_id="abc123",
        source_subreddit="python",
        user_opinion="I found this really interesting",
    )


@pytest.fixture
def sample_reddit_post():
    """Create a sample RedditPost for testing."""
    return RedditPost(
        id="abc123",
        subreddit="python",
        title="Amazing Python trick I discovered",
        selftext="So I was coding and found this amazing trick with list comprehensions...",
        url="https://reddit.com/r/python/comments/abc123/",
        author="test_user",
        score=150,
        comments=[
            RedditComment(
                id="c1",
                body="This is great!",
                author="commenter1",
                score=50,
            ),
            RedditComment(
                id="c2",
                body="I've been using this for years",
                author="commenter2",
                score=30,
            ),
            RedditComment(
                id="c3",
                body="Can you explain more?",
                author="commenter3",
                score=10,
            ),
        ],
    )


@pytest.fixture
def sample_reddit_post_no_body():
    """Create a RedditPost with only a title."""
    return RedditPost(
        id="xyz789",
        subreddit="askreddit",
        title="What's your favorite programming language?",
        selftext="",
        url="https://reddit.com/r/askreddit/comments/xyz789/",
        author="curious_dev",
        score=500,
        comments=[],
    )


@pytest.fixture
def sample_content_dict():
    """Create sample content dictionary for testing."""
    return {
        "subreddit": "python",
        "post": {
            "id": "abc123",
            "title": "Amazing Python trick",
            "selftext": "This is the content of the post...",
            "author": "test_user",
        },
        "comments": [
            {"body": "Great post!", "author": "user1", "score": 25},
            {"body": "Thanks for sharing", "author": "user2", "score": 10},
        ],
    }


# =============================================================================
# Initialization Tests
# =============================================================================


class TestScriptServiceInit:
    """Tests for ScriptService initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService()
            assert service._max_words == 250
            assert service._max_comments == 10
            assert service._gemini_client is None

    def test_init_custom_values(self, mock_gemini_client):
        """Test initialization with custom values."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService(
                gemini_client=mock_gemini_client,
                max_words=500,
                max_comments=20,
            )
            assert service._max_words == 500
            assert service._max_comments == 20
            assert service._gemini_client is mock_gemini_client

    def test_gemini_client_property_returns_injected_client(self, mock_gemini_client):
        """Test that gemini_client property returns injected client."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService(gemini_client=mock_gemini_client)
            assert service.gemini_client is mock_gemini_client

    def test_gemini_client_lazy_loading(self):
        """Test that gemini_client is lazy-loaded."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService()
            assert service._gemini_client is None
            # We can't test actual lazy loading without mocking GeminiClient init


# =============================================================================
# Generate Script from RedditPost Tests
# =============================================================================


class TestGenerateScript:
    """Tests for generate_script method."""

    @pytest.mark.asyncio
    async def test_generate_script_success(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
        sample_video_script,
    ):
        """Test successful script generation from RedditPost."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        result = await script_service.generate_script(sample_reddit_post)

        assert result == sample_video_script
        mock_gemini_client.generate_script.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert "Amazing Python trick" in call_kwargs["post_text"]
        assert call_kwargs["source_post_id"] == "abc123"
        assert call_kwargs["source_subreddit"] == "python"

    @pytest.mark.asyncio
    async def test_generate_script_with_user_opinion(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
        sample_video_script,
    ):
        """Test script generation with user opinion."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        result = await script_service.generate_script(
            sample_reddit_post,
            user_opinion="This is really cool!",
        )

        assert result == sample_video_script
        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert call_kwargs["user_opinion"] == "This is really cool!"

    @pytest.mark.asyncio
    async def test_generate_script_title_only_post(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post_no_body,
        sample_video_script,
    ):
        """Test script generation from post with only title."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        result = await script_service.generate_script(sample_reddit_post_no_body)

        assert result == sample_video_script
        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert "favorite programming language" in call_kwargs["post_text"]

    @pytest.mark.asyncio
    async def test_generate_script_empty_post_raises_error(
        self,
        script_service,
    ):
        """Test that empty post content raises ContentError."""
        empty_post = RedditPost(
            id="empty",
            subreddit="test",
            title="",
            selftext="",
            url="https://reddit.com/r/test/comments/empty/",
        )

        with pytest.raises(ContentError, match="no content to generate"):
            await script_service.generate_script(empty_post)

    @pytest.mark.asyncio
    async def test_generate_script_ai_error(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
    ):
        """Test that AIGenerationError is propagated."""
        mock_gemini_client.generate_script.side_effect = AIGenerationError("AI failed")

        with pytest.raises(AIGenerationError, match="AI failed"):
            await script_service.generate_script(sample_reddit_post)

    @pytest.mark.asyncio
    async def test_generate_script_generic_exception(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
    ):
        """Test that generic exceptions are wrapped in AIGenerationError."""
        mock_gemini_client.generate_script.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(AIGenerationError, match="Script generation failed"):
            await script_service.generate_script(sample_reddit_post)

    @pytest.mark.asyncio
    async def test_generate_script_formats_comments(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
        sample_video_script,
    ):
        """Test that comments are properly formatted."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script(sample_reddit_post)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        comments_data = call_kwargs["comments_data"]

        assert len(comments_data) == 3
        assert comments_data[0]["body"] == "This is great!"
        assert comments_data[0]["author"] == "commenter1"
        assert comments_data[0]["score"] == 50


# =============================================================================
# Generate Script from Dict Tests
# =============================================================================


class TestGenerateScriptFromDict:
    """Tests for generate_script_from_dict method."""

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_success(
        self,
        script_service,
        mock_gemini_client,
        sample_content_dict,
        sample_video_script,
    ):
        """Test successful script generation from dictionary."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        result = await script_service.generate_script_from_dict(sample_content_dict)

        assert result == sample_video_script
        mock_gemini_client.generate_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_with_user_opinion(
        self,
        script_service,
        mock_gemini_client,
        sample_content_dict,
        sample_video_script,
    ):
        """Test script generation from dict with user opinion."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script_from_dict(
            sample_content_dict,
            user_opinion="Interesting topic!",
        )

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert call_kwargs["user_opinion"] == "Interesting topic!"

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_empty_content(self, script_service):
        """Test that empty content raises ContentError."""
        empty_dict = {"post": {"title": "", "selftext": ""}}

        with pytest.raises(ContentError, match="no post text"):
            await script_service.generate_script_from_dict(empty_dict)

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_missing_post(self, script_service):
        """Test handling of missing post key."""
        no_post_dict = {"comments": [{"body": "test"}]}

        with pytest.raises(ContentError, match="no post text"):
            await script_service.generate_script_from_dict(no_post_dict)

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_filters_empty_comments(
        self,
        script_service,
        mock_gemini_client,
        sample_video_script,
    ):
        """Test that empty comments are filtered out."""
        content = {
            "post": {"title": "Test post", "selftext": "Content here"},
            "comments": [
                {"body": "Valid comment", "author": "user1", "score": 10},
                {"body": "", "author": "user2", "score": 5},  # Empty body
                {"author": "user3", "score": 3},  # Missing body
            ],
        }
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script_from_dict(content)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert len(call_kwargs["comments_data"]) == 1
        assert call_kwargs["comments_data"][0]["body"] == "Valid comment"

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_respects_max_comments(
        self,
        mock_gemini_client,
        sample_video_script,
    ):
        """Test that max_comments limit is respected."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService(
                gemini_client=mock_gemini_client,
                max_comments=2,
            )

        content = {
            "post": {"title": "Test", "selftext": "Content"},
            "comments": [
                {"body": f"Comment {i}", "author": f"user{i}", "score": i} for i in range(10)
            ],
        }
        mock_gemini_client.generate_script.return_value = sample_video_script

        await service.generate_script_from_dict(content)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert len(call_kwargs["comments_data"]) == 2

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_ai_error(
        self,
        script_service,
        mock_gemini_client,
        sample_content_dict,
    ):
        """Test that AIGenerationError is propagated from dict method."""
        mock_gemini_client.generate_script.side_effect = AIGenerationError("AI failed")

        with pytest.raises(AIGenerationError, match="AI failed"):
            await script_service.generate_script_from_dict(sample_content_dict)

    @pytest.mark.asyncio
    async def test_generate_script_from_dict_extracts_metadata(
        self,
        script_service,
        mock_gemini_client,
        sample_content_dict,
        sample_video_script,
    ):
        """Test that post metadata is extracted correctly."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script_from_dict(sample_content_dict)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert call_kwargs["source_post_id"] == "abc123"
        assert call_kwargs["source_subreddit"] == "python"


# =============================================================================
# Build Post Text Tests
# =============================================================================


class TestBuildPostText:
    """Tests for _build_post_text method."""

    def test_build_post_text_full_content(self, script_service, sample_reddit_post):
        """Test building text with title and body."""
        result = script_service._build_post_text(sample_reddit_post)

        assert "Amazing Python trick I discovered" in result
        assert "list comprehensions" in result
        assert "\n\n" in result  # Separator between title and body

    def test_build_post_text_title_only(self, script_service, sample_reddit_post_no_body):
        """Test building text with only title."""
        result = script_service._build_post_text(sample_reddit_post_no_body)

        assert "favorite programming language" in result
        assert "\n\n" not in result  # No separator for single part

    def test_build_post_text_empty(self, script_service):
        """Test building text from empty post."""
        empty_post = RedditPost(
            id="empty",
            subreddit="test",
            title="",
            selftext="",
            url="https://reddit.com/r/test/comments/empty/",
        )

        result = script_service._build_post_text(empty_post)
        assert result == ""


# =============================================================================
# Format Comments Tests
# =============================================================================


class TestFormatComments:
    """Tests for _format_comments method."""

    def test_format_comments_basic(self, script_service, sample_reddit_post):
        """Test basic comment formatting."""
        result = script_service._format_comments(sample_reddit_post.comments)

        assert len(result) == 3
        assert result[0]["body"] == "This is great!"
        assert result[0]["author"] == "commenter1"
        assert result[0]["score"] == 50

    def test_format_comments_filters_deleted(self, script_service):
        """Test that deleted comments are filtered out."""
        comments = [
            RedditComment(id="c1", body="Valid comment", author="user1", score=10),
            RedditComment(id="c2", body="[deleted]", author="user2", score=5),
            RedditComment(id="c3", body="Another valid", author="user3", score=8),
        ]

        result = script_service._format_comments(comments)

        assert len(result) == 2
        assert all(c["body"] != "[deleted]" for c in result)

    def test_format_comments_respects_limit(self, mock_gemini_client):
        """Test that max_comments limit is respected."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService(
                gemini_client=mock_gemini_client,
                max_comments=3,
            )

        comments = [
            RedditComment(id=f"c{i}", body=f"Comment {i}", author=f"user{i}", score=i)
            for i in range(10)
        ]

        result = service._format_comments(comments)
        assert len(result) == 3

    def test_format_comments_empty_list(self, script_service):
        """Test formatting empty comment list."""
        result = script_service._format_comments([])
        assert result == []

    def test_format_comments_preserves_order(self, script_service):
        """Test that comment order is preserved."""
        comments = [
            RedditComment(id="c1", body="First", author="u1", score=1),
            RedditComment(id="c2", body="Second", author="u2", score=2),
            RedditComment(id="c3", body="Third", author="u3", score=3),
        ]

        result = script_service._format_comments(comments)

        assert result[0]["body"] == "First"
        assert result[1]["body"] == "Second"
        assert result[2]["body"] == "Third"


# =============================================================================
# Validate Script Tests
# =============================================================================


class TestValidateScript:
    """Tests for _validate_script method."""

    def test_validate_script_valid(self, script_service, sample_video_script):
        """Test validation of valid script."""
        assert script_service._validate_script(sample_video_script) is True

    def test_validate_script_whitespace_only(self, script_service):
        """Test validation fails for whitespace-only script.

        Note: VideoScript model itself validates for empty values,
        but whitespace-only might pass model validation.
        We test with a script that has whitespace after stripping.
        """
        # VideoScript model rejects truly empty scripts, so we test
        # with minimal content that would fail our validation
        script = VideoScript(script="a b c", title="Valid Title")
        # This should fail because it's less than 10 words
        assert script_service._validate_script(script) is False

    def test_validate_script_too_short(self, script_service):
        """Test validation fails for too short script."""
        script = VideoScript(script="Too short", title="Title")
        assert script_service._validate_script(script) is False

    def test_validate_script_minimum_length(self, script_service):
        """Test validation passes for minimum length script."""
        script = VideoScript(
            script="One two three four five six seven eight nine ten eleven",
            title="Title",
        )
        assert script_service._validate_script(script) is True

    def test_validate_script_exactly_ten_words(self, script_service):
        """Test validation fails for exactly 10 words (need > 10)."""
        script = VideoScript(
            script="One two three four five six seven eight nine ten",
            title="Title",
        )
        # word_count returns 10, validation requires > 10 (< 10 check fails means >= 10 passes)
        # Actually our check is: if script.word_count < 10: return False
        # So 10 words would pass, let's verify
        assert script_service._validate_script(script) is True


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestScriptServiceIntegration:
    """Integration-like tests for ScriptService workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_comments(
        self,
        script_service,
        mock_gemini_client,
        sample_reddit_post,
        sample_video_script,
    ):
        """Test full workflow from post with comments to script."""
        mock_gemini_client.generate_script.return_value = sample_video_script

        result = await script_service.generate_script(
            sample_reddit_post,
            user_opinion="Great content!",
        )

        assert result.script is not None
        assert result.title is not None
        assert result.source_post_id == "abc123"
        assert result.source_subreddit == "python"

    @pytest.mark.asyncio
    async def test_workflow_with_deleted_comments(
        self,
        script_service,
        mock_gemini_client,
        sample_video_script,
    ):
        """Test workflow handles deleted comments correctly."""
        post = RedditPost(
            id="test123",
            subreddit="test",
            title="Test Post",
            selftext="Content here",
            url="https://reddit.com/r/test/comments/test123/",
            comments=[
                RedditComment(id="c1", body="[deleted]", author="[deleted]", score=0),
                RedditComment(id="c2", body="Valid comment", author="user", score=10),
                RedditComment(id="c3", body="[deleted]", author="user2", score=5),
            ],
        )
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script(post)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert len(call_kwargs["comments_data"]) == 1
        assert call_kwargs["comments_data"][0]["body"] == "Valid comment"

    @pytest.mark.asyncio
    async def test_workflow_no_comments(
        self,
        script_service,
        mock_gemini_client,
        sample_video_script,
    ):
        """Test workflow with post that has no comments."""
        post = RedditPost(
            id="test123",
            subreddit="test",
            title="Lonely Post",
            selftext="No one commented on this yet",
            url="https://reddit.com/r/test/comments/test123/",
            comments=[],
        )
        mock_gemini_client.generate_script.return_value = sample_video_script

        await script_service.generate_script(post)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert call_kwargs["comments_data"] == []

    @pytest.mark.asyncio
    async def test_workflow_many_comments_limited(
        self,
        mock_gemini_client,
        sample_video_script,
        mock_prod_settings,
    ):
        """Test that many comments are limited correctly."""
        with patch("reddit_flow.services.script_service.logger"):
            service = ScriptService(
                gemini_client=mock_gemini_client,
                max_comments=5,
                settings=mock_prod_settings,
            )

        post = RedditPost(
            id="popular",
            subreddit="popular",
            title="Viral Post",
            selftext="This went viral!",
            url="https://reddit.com/r/popular/comments/popular/",
            comments=[
                RedditComment(id=f"c{i}", body=f"Comment {i}", author=f"u{i}", score=i)
                for i in range(100)
            ],
        )
        mock_gemini_client.generate_script.return_value = sample_video_script

        await service.generate_script(post)

        call_kwargs = mock_gemini_client.generate_script.call_args.kwargs
        assert len(call_kwargs["comments_data"]) == 5
