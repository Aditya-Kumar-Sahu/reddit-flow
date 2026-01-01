"""
Unit tests for Pydantic data models.

Tests for src/reddit_flow/models/
"""

import pytest

from reddit_flow.models import (
    LinkInfo,
    RedditComment,
    RedditPost,
    ScriptGenerationRequest,
    VideoDimension,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoScript,
    VideoStatus,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
)

# =============================================================================
# Reddit Models Tests
# =============================================================================


class TestRedditComment:
    """Tests for RedditComment model."""

    def test_create_valid_comment(self) -> None:
        """Test creating a valid comment."""
        comment = RedditComment(
            id="abc123",
            body="This is a great post!",
            author="test_user",
            depth=0,
            score=42,
        )
        assert comment.id == "abc123"
        assert comment.body == "This is a great post!"
        assert comment.author == "test_user"
        assert comment.depth == 0
        assert comment.score == 42

    def test_comment_with_defaults(self) -> None:
        """Test comment with default values."""
        comment = RedditComment(id="xyz789", body="Test")
        assert comment.author == "[deleted]"
        assert comment.depth == 0
        assert comment.score == 0

    def test_deleted_author_handling(self) -> None:
        """Test that None/empty authors become [deleted]."""
        comment1 = RedditComment(id="1", body="Test", author=None)
        comment2 = RedditComment(id="2", body="Test", author="")
        comment3 = RedditComment(id="3", body="Test", author="None")

        assert comment1.author == "[deleted]"
        assert comment2.author == "[deleted]"
        assert comment3.author == "[deleted]"

    def test_deleted_body_handling(self) -> None:
        """Test that None/empty body becomes [deleted]."""
        comment1 = RedditComment(id="1", body=None)
        comment2 = RedditComment(id="2", body="")

        assert comment1.body == "[deleted]"
        assert comment2.body == "[deleted]"

    def test_negative_depth_rejected(self) -> None:
        """Test that negative depth is rejected."""
        with pytest.raises(ValueError):
            RedditComment(id="1", body="Test", depth=-1)


class TestRedditPost:
    """Tests for RedditPost model."""

    def test_create_valid_post(self) -> None:
        """Test creating a valid post."""
        post = RedditPost(
            id="1nf7kh6",
            subreddit="technology",
            title="Amazing Tech Discovery",
            selftext="This is the post body",
            url="https://reddit.com/r/technology/comments/1nf7kh6/",
            author="poster",
            score=1500,
        )
        assert post.id == "1nf7kh6"
        assert post.subreddit == "technology"
        assert post.title == "Amazing Tech Discovery"

    def test_post_with_comments(self) -> None:
        """Test post with nested comments."""
        comments = [
            RedditComment(id="c1", body="Great post!", score=100),
            RedditComment(id="c2", body="I agree", score=50),
        ]
        post = RedditPost(
            id="abc",
            subreddit="test",
            title="Test",
            url="https://reddit.com/",
            comments=comments,
        )
        assert len(post.comments) == 2
        assert post.comment_count == 2

    def test_post_permalink(self) -> None:
        """Test permalink generation."""
        post = RedditPost(
            id="xyz123",
            subreddit="python",
            title="Python Tips",
            url="https://reddit.com/",
        )
        assert post.permalink == "https://www.reddit.com/r/python/comments/xyz123/"

    def test_get_top_comments(self) -> None:
        """Test getting top comments by score."""
        comments = [
            RedditComment(id="c1", body="Low score", score=10),
            RedditComment(id="c2", body="High score", score=100),
            RedditComment(id="c3", body="Medium score", score=50),
        ]
        post = RedditPost(
            id="abc",
            subreddit="test",
            title="Test",
            url="https://reddit.com/",
            comments=comments,
        )
        top = post.get_top_comments(limit=2)
        assert len(top) == 2
        assert top[0].score == 100
        assert top[1].score == 50

    def test_get_top_comments_with_min_score(self) -> None:
        """Test filtering comments by minimum score."""
        comments = [
            RedditComment(id="c1", body="Low", score=5),
            RedditComment(id="c2", body="High", score=100),
        ]
        post = RedditPost(
            id="abc",
            subreddit="test",
            title="Test",
            url="https://reddit.com/",
            comments=comments,
        )
        top = post.get_top_comments(min_score=10)
        assert len(top) == 1
        assert top[0].score == 100


class TestLinkInfo:
    """Tests for LinkInfo model."""

    def test_create_from_ai_response(self) -> None:
        """Test creating LinkInfo from AI JSON response format."""
        data = {
            "link": "https://www.reddit.com/r/sheffield/comments/1nf7kh6/",
            "subReddit": "sheffield",
            "postId": "1nf7kh6",
            "text": "Check this out",
        }
        info = LinkInfo(**data)
        assert info.link == "https://www.reddit.com/r/sheffield/comments/1nf7kh6/"
        assert info.subreddit == "sheffield"
        assert info.post_id == "1nf7kh6"
        assert info.user_text == "Check this out"

    def test_create_with_field_names(self) -> None:
        """Test creating LinkInfo with Python field names."""
        info = LinkInfo(
            link="https://reddit.com/r/test/comments/abc/",
            subreddit="test",
            post_id="abc",
        )
        assert info.subreddit == "test"
        assert info.post_id == "abc"

    def test_null_user_text(self) -> None:
        """Test that null user text is handled."""
        data = {
            "link": "https://reddit.com/r/test/comments/abc/",
            "subReddit": "test",
            "postId": "abc",
            "text": None,
        }
        info = LinkInfo(**data)
        assert info.user_text is None

    def test_subreddit_r_prefix_cleaned(self) -> None:
        """Test that r/ prefix is removed from subreddit."""
        info = LinkInfo(
            link="https://reddit.com/r/test/comments/abc/",
            subreddit="r/technology",
            post_id="abc",
        )
        assert info.subreddit == "technology"

    def test_invalid_link_rejected(self) -> None:
        """Test that non-Reddit links are rejected."""
        with pytest.raises(ValueError) as exc_info:
            LinkInfo(
                link="https://example.com/not-reddit",
                subreddit="test",
                post_id="abc",
            )
        assert "Reddit URL" in str(exc_info.value)


# =============================================================================
# Script Models Tests
# =============================================================================


class TestVideoScript:
    """Tests for VideoScript model."""

    def test_create_valid_script(self) -> None:
        """Test creating a valid script."""
        script = VideoScript(
            script="This is the video script content here.",
            title="Amazing Video Title",
        )
        assert script.script == "This is the video script content here."
        assert script.title == "Amazing Video Title"

    def test_word_count_property(self) -> None:
        """Test word count calculation."""
        script = VideoScript(
            script="One two three four five six seven eight nine ten",
            title="Test",
        )
        assert script.word_count == 10

    def test_youtube_title_truncation(self) -> None:
        """Test YouTube title is truncated to 100 chars."""
        long_title = "A" * 150
        script = VideoScript(script="Content", title=long_title)
        assert len(script.youtube_title) == 100
        assert script.youtube_title.endswith("...")

    def test_youtube_title_no_truncation(self) -> None:
        """Test YouTube title not truncated if short."""
        script = VideoScript(script="Content", title="Short Title")
        assert script.youtube_title == "Short Title"

    def test_estimated_duration(self) -> None:
        """Test estimated duration calculation."""
        # 150 words = 1 minute = 60 seconds
        script = VideoScript(
            script=" ".join(["word"] * 150),
            title="Test",
        )
        assert script.estimated_duration_seconds == 60

    def test_validate_word_limit_within(self) -> None:
        """Test word limit validation when within limit."""
        script = VideoScript(
            script=" ".join(["word"] * 100),
            title="Test",
        )
        assert script.validate_word_limit(200) is True

    def test_validate_word_limit_overflow(self) -> None:
        """Test word limit with allowed overflow."""
        script = VideoScript(
            script=" ".join(["word"] * 220),  # 220 words
            title="Test",
        )
        # 200 * 1.2 = 240, so 220 is within overflow
        assert script.validate_word_limit(200, allow_overflow=0.2) is True

    def test_validate_word_limit_exceeded(self) -> None:
        """Test word limit exceeded."""
        script = VideoScript(
            script=" ".join(["word"] * 300),
            title="Test",
        )
        assert script.validate_word_limit(200) is False

    def test_empty_title_rejected(self) -> None:
        """Test that empty title is rejected."""
        with pytest.raises(ValueError):
            VideoScript(script="Content", title="")

    def test_empty_script_rejected(self) -> None:
        """Test that empty script is rejected."""
        with pytest.raises(ValueError):
            VideoScript(script="", title="Title")


class TestScriptGenerationRequest:
    """Tests for ScriptGenerationRequest model."""

    def test_create_valid_request(self) -> None:
        """Test creating a valid request."""
        request = ScriptGenerationRequest(
            post_text="This is the Reddit post",
            comments_text="Comment 1, Comment 2",
            max_words=300,
        )
        assert request.post_text == "This is the Reddit post"
        assert request.max_words == 300

    def test_default_values(self) -> None:
        """Test default values."""
        request = ScriptGenerationRequest(post_text="Post content")
        assert request.max_words == 200
        assert request.style == "conversational"
        assert request.comments_text == ""

    def test_valid_styles(self) -> None:
        """Test all valid writing styles."""
        for style in ["conversational", "formal", "humorous", "informative"]:
            request = ScriptGenerationRequest(post_text="Test", style=style)
            assert request.style == style

    def test_invalid_style_rejected(self) -> None:
        """Test that invalid style is rejected."""
        with pytest.raises(ValueError):
            ScriptGenerationRequest(post_text="Test", style="invalid_style")


# =============================================================================
# Video Models Tests
# =============================================================================


class TestVideoDimension:
    """Tests for VideoDimension model."""

    def test_default_dimensions(self) -> None:
        """Test default dimensions (portrait for shorts)."""
        dim = VideoDimension()
        assert dim.width == 1080
        assert dim.height == 1920

    def test_aspect_ratio_calculation(self) -> None:
        """Test aspect ratio calculation."""
        dim = VideoDimension(width=1920, height=1080)
        assert dim.aspect_ratio == "16:9"

        dim_portrait = VideoDimension(width=1080, height=1920)
        assert dim_portrait.aspect_ratio == "9:16"

    def test_is_portrait(self) -> None:
        """Test portrait detection."""
        portrait = VideoDimension(width=1080, height=1920)
        landscape = VideoDimension(width=1920, height=1080)

        assert portrait.is_portrait is True
        assert landscape.is_portrait is False

    def test_is_landscape(self) -> None:
        """Test landscape detection."""
        portrait = VideoDimension(width=1080, height=1920)
        landscape = VideoDimension(width=1920, height=1080)

        assert portrait.is_landscape is False
        assert landscape.is_landscape is True


class TestVideoGenerationRequest:
    """Tests for VideoGenerationRequest model."""

    def test_create_request(self) -> None:
        """Test creating a video generation request."""
        request = VideoGenerationRequest(
            audio_url="https://upload.heygen.com/audio.mp3",
            avatar_id="avatar_123",
            title="Test Video",
        )
        assert request.audio_url == "https://upload.heygen.com/audio.mp3"
        assert request.avatar_id == "avatar_123"
        assert request.test_mode is False

    def test_to_heygen_payload(self) -> None:
        """Test conversion to HeyGen API payload."""
        request = VideoGenerationRequest(
            audio_url="https://example.com/audio.mp3",
            avatar_id="avatar_123",
            title="My Video",
            enable_captions=True,
        )
        payload = request.to_heygen_payload()

        assert payload["test"] is False
        assert payload["caption"] is True
        assert payload["title"] == "My Video"
        assert len(payload["video_inputs"]) == 1
        assert payload["video_inputs"][0]["character"]["avatar_id"] == "avatar_123"
        assert payload["video_inputs"][0]["voice"]["audio_url"] == "https://example.com/audio.mp3"

    def test_heygen_payload_without_title(self) -> None:
        """Test payload without title."""
        request = VideoGenerationRequest(
            audio_url="https://example.com/audio.mp3",
            avatar_id="avatar_123",
        )
        payload = request.to_heygen_payload()
        assert "title" not in payload


class TestVideoGenerationResponse:
    """Tests for VideoGenerationResponse model."""

    def test_pending_status(self) -> None:
        """Test pending status properties."""
        response = VideoGenerationResponse(
            video_id="vid_123",
            status=VideoStatus.PENDING,
        )
        assert response.is_pending is True
        assert response.is_complete is False
        assert response.is_failed is False

    def test_completed_status(self) -> None:
        """Test completed status properties."""
        response = VideoGenerationResponse(
            video_id="vid_123",
            status=VideoStatus.COMPLETED,
            video_url="https://example.com/video.mp4",
        )
        assert response.is_pending is False
        assert response.is_complete is True
        assert response.is_failed is False
        assert response.video_url is not None

    def test_failed_status(self) -> None:
        """Test failed status properties."""
        response = VideoGenerationResponse(
            video_id="vid_123",
            status=VideoStatus.FAILED,
            error_message="Generation failed",
        )
        assert response.is_pending is False
        assert response.is_complete is False
        assert response.is_failed is True


class TestYouTubeUploadRequest:
    """Tests for YouTubeUploadRequest model."""

    def test_create_request(self) -> None:
        """Test creating an upload request."""
        request = YouTubeUploadRequest(
            file_path="/path/to/video.mp4",
            title="My Amazing Video",
            description="Video description here",
        )
        assert request.file_path == "/path/to/video.mp4"
        assert request.title == "My Amazing Video"
        assert request.privacy_status == "public"

    def test_title_truncation(self) -> None:
        """Test title is truncated to 100 chars."""
        long_title = "A" * 150
        request = YouTubeUploadRequest(
            file_path="/path/to/video.mp4",
            title=long_title,
        )
        assert len(request.title) == 100
        assert request.title.endswith("...")

    def test_valid_privacy_statuses(self) -> None:
        """Test valid privacy status values."""
        for status in ["public", "private", "unlisted"]:
            request = YouTubeUploadRequest(
                file_path="/video.mp4",
                title="Test",
                privacy_status=status,
            )
            assert request.privacy_status == status

    def test_invalid_privacy_rejected(self) -> None:
        """Test that invalid privacy status is rejected."""
        with pytest.raises(ValueError):
            YouTubeUploadRequest(
                file_path="/video.mp4",
                title="Test",
                privacy_status="invalid",
            )

    def test_to_youtube_body(self) -> None:
        """Test conversion to YouTube API body."""
        request = YouTubeUploadRequest(
            file_path="/video.mp4",
            title="Test Video",
            description="Description",
            category_id="22",
            tags=["tag1", "tag2"],
        )
        body = request.to_youtube_body()

        assert body["snippet"]["title"] == "Test Video"
        assert body["snippet"]["description"] == "Description"
        assert body["snippet"]["categoryId"] == "22"
        assert body["snippet"]["tags"] == ["tag1", "tag2"]
        assert body["status"]["privacyStatus"] == "public"


class TestYouTubeUploadResponse:
    """Tests for YouTubeUploadResponse model."""

    def test_create_response(self) -> None:
        """Test creating an upload response."""
        response = YouTubeUploadResponse(
            video_id="dQw4w9WgXcQ",
            title="My Video",
        )
        assert response.video_id == "dQw4w9WgXcQ"
        assert response.title == "My Video"

    def test_watch_url(self) -> None:
        """Test watch URL generation."""
        response = YouTubeUploadResponse(
            video_id="dQw4w9WgXcQ",
            title="Test",
        )
        assert response.watch_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_studio_url(self) -> None:
        """Test Studio URL generation."""
        response = YouTubeUploadResponse(
            video_id="dQw4w9WgXcQ",
            title="Test",
        )
        assert response.studio_url == "https://studio.youtube.com/video/dQw4w9WgXcQ/edit"
