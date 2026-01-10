"""
End-to-end tests for the complete Reddit-Flow workflow.

These tests verify the full workflow from URL to YouTube upload using
mocked API services. They test the entire orchestration without hitting
real external APIs.

Run with: pytest tests/e2e/ -m e2e -v
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.models.reddit import RedditComment, RedditPost
from reddit_flow.models.script import VideoScript
from reddit_flow.models.video import AudioAsset, YouTubeUploadRequest, YouTubeUploadResponse
from reddit_flow.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    WorkflowStatus,
    WorkflowStep,
)

pytestmark = [pytest.mark.e2e]


class MockRedditClient:
    """Mock Reddit client for E2E tests."""

    service_name = "Reddit"

    def __init__(self):
        self.reddit = MagicMock()

    def get_post(self, subreddit_name: str, post_id: str) -> RedditPost:
        """Return a mock Reddit post."""
        return RedditPost(
            id=post_id,
            subreddit=subreddit_name,
            title="What are the best Python testing practices?",
            selftext="I want to improve my unit testing skills. What are some tips?",
            url=f"https://reddit.com/r/{subreddit_name}/comments/{post_id}/",
            author="test_user",
            score=150,
            comments=[
                RedditComment(
                    id="c1",
                    body="Use pytest - it's the best!",
                    author="commenter1",
                    score=50,
                ),
                RedditComment(
                    id="c2",
                    body="Mock your external dependencies",
                    author="commenter2",
                    score=30,
                ),
                RedditComment(
                    id="c3",
                    body="Write tests before code (TDD)",
                    author="commenter3",
                    score=20,
                ),
            ],
        )

    def get_post_data(self, subreddit_name: str, post_id: str) -> Dict[str, Any]:
        """Return mock post data as dictionary."""
        return {
            "id": post_id,
            "subreddit": subreddit_name,
            "title": "What are the best Python testing practices?",
            "selftext": "I want to improve my unit testing skills. What are some tips?",
            "url": f"https://reddit.com/r/{subreddit_name}/comments/{post_id}/",
            "author": "test_user",
            "score": 150,
            "comments": [
                {
                    "id": "c1",
                    "body": "Use pytest - it's the best!",
                    "author": "commenter1",
                    "score": 50,
                },
                {
                    "id": "c2",
                    "body": "Mock your external dependencies",
                    "author": "commenter2",
                    "score": 30,
                },
                {
                    "id": "c3",
                    "body": "Write tests before code (TDD)",
                    "author": "commenter3",
                    "score": 20,
                },
            ],
        }

    def verify_service(self) -> bool:
        return True


class MockGeminiClient:
    """Mock Gemini client for E2E tests."""

    service_name = "Gemini"

    async def generate_script(
        self,
        post_text: str,
        comments_data: list,
        user_opinion: str = None,
        source_post_id: str = None,
        source_subreddit: str = None,
    ) -> VideoScript:
        """Return a mock video script."""
        return VideoScript(
            title="Python Testing Best Practices",
            script="""
            Hey everyone! Today we're diving into Python testing best practices.

            The community has spoken, and here are the top recommendations:

            First, use pytest - it's widely considered the best testing framework
            for Python. It has great features like fixtures and parametrization.

            Second, always mock your external dependencies. This keeps your tests
            fast and isolated from external services.

            Third, consider Test-Driven Development or TDD. Writing tests before
            your code can lead to better designed software.

            That's all for today! Let me know your favorite testing tips in the
            comments below.
            """,
            source_subreddit=source_subreddit or "python",
            source_post_id=source_post_id or "abc123",
            user_opinion=user_opinion,
        )

    def verify_service(self) -> bool:
        return True


class MockElevenLabsClient:
    """Mock ElevenLabs client for E2E tests."""

    service_name = "ElevenLabs"

    def text_to_speech(self, text: str) -> bytes:
        """Return mock audio data."""
        # Return some fake MP3 header bytes
        return b"\xff\xfb\x90\x00" + b"\x00" * 1000

    def verify_service(self) -> bool:
        return True


class MockHeyGenClient:
    """Mock HeyGen client for E2E tests."""

    service_name = "HeyGen"

    def __init__(self):
        self._video_counter = 0
        self._avatar_id = "test_avatar_123"

    @property
    def avatar_id(self) -> str:
        """Return mock avatar ID."""
        return self._avatar_id

    def upload_audio(self, audio_data: bytes, content_type: str = "audio/mpeg") -> AudioAsset:
        """Return a mock audio asset."""
        return AudioAsset(
            url="https://heygen.com/audio/audio_asset_123.mp3",
            asset_id="audio_asset_123",
        )

    def upload_audio_url(self, audio_data: bytes, content_type: str = "audio/mpeg") -> str:
        """Return a mock audio asset URL."""
        return "https://heygen.com/audio/audio_asset_123.mp3"

    def generate_video(
        self,
        audio_url: str,
        title: str = None,
        avatar_id: str = None,
        avatar_style: str = "normal",
        test_mode: bool = None,
        enable_captions: bool = True,
    ) -> str:
        """Return a mock video ID."""
        self._video_counter += 1
        return f"video_{self._video_counter}"

    async def wait_for_video(
        self,
        video_id: str,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Return a completed video URL."""
        if update_callback:
            if asyncio.iscoroutinefunction(update_callback):
                await update_callback("Processing video...")
                await update_callback("Video complete!")
            else:
                update_callback("Processing video...")
                update_callback("Video complete!")

        return "https://heygen.com/videos/test_video.mp4"

    def verify_service(self) -> bool:
        return True


class MockYouTubeClient:
    """Mock YouTube client for E2E tests."""

    service_name = "YouTube"

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list = None,
        category_id: str = "22",
        privacy_status: str = "unlisted",
        progress_callback=None,
    ) -> YouTubeUploadResponse:
        """Return a mock upload response."""
        if progress_callback:
            progress_callback(0.5)
            progress_callback(1.0)

        return YouTubeUploadResponse(
            video_id="yt_video_123abc",
            title=title,
            description=description,
            privacy_status=privacy_status,
            published_at=datetime.now(),
        )

    def upload_video_from_request(
        self,
        request: YouTubeUploadRequest,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> YouTubeUploadResponse:
        """Return a mock upload response using request model."""
        if progress_callback:
            progress_callback(50)
            progress_callback(100)

        return YouTubeUploadResponse(
            video_id="yt_video_123abc",
            title=request.title,
            description=request.description,
            privacy_status=request.privacy_status,
            published_at=datetime.now(),
        )

    def verify_service(self) -> bool:
        return True


@pytest.fixture
def mock_reddit_client():
    """Provide mock Reddit client."""
    return MockRedditClient()


@pytest.fixture
def mock_gemini_client():
    """Provide mock Gemini client."""
    return MockGeminiClient()


@pytest.fixture
def mock_elevenlabs_client():
    """Provide mock ElevenLabs client."""
    return MockElevenLabsClient()


@pytest.fixture
def mock_heygen_client():
    """Provide mock HeyGen client."""
    return MockHeyGenClient()


@pytest.fixture
def mock_youtube_client():
    """Provide mock YouTube client."""
    return MockYouTubeClient()


@pytest.fixture
def workflow_orchestrator(
    mock_reddit_client,
    mock_gemini_client,
    mock_elevenlabs_client,
    mock_heygen_client,
    mock_youtube_client,
):
    """Create orchestrator with all mocked services."""
    from reddit_flow.services.content_service import ContentService
    from reddit_flow.services.media_service import MediaService
    from reddit_flow.services.script_service import ScriptService
    from reddit_flow.services.upload_service import UploadService

    # Create services with mock clients
    content_service = ContentService(reddit_client=mock_reddit_client)
    script_service = ScriptService(gemini_client=mock_gemini_client)
    media_service = MediaService(
        elevenlabs_client=mock_elevenlabs_client,
        heygen_client=mock_heygen_client,
    )
    upload_service = UploadService(youtube_client=mock_youtube_client)

    return WorkflowOrchestrator(
        content_service=content_service,
        script_service=script_service,
        media_service=media_service,
        upload_service=upload_service,
    )


class TestFullWorkflowE2E:
    """End-to-end tests for complete workflow."""

    @pytest.mark.asyncio
    async def test_complete_workflow_success(self, workflow_orchestrator):
        """Test complete workflow from URL to YouTube upload."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        with patch("requests.get") as mock_requests:
            # Mock video download
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(url)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.youtube_url is not None
        assert "youtube.com" in result.youtube_url or "youtu.be" in result.youtube_url

    @pytest.mark.asyncio
    async def test_workflow_captures_all_steps(self, workflow_orchestrator):
        """Test that all workflow steps are captured."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        with patch("requests.get") as mock_requests:
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(url)

        # Verify all steps completed
        step_names = [step.step for step in result.steps]

        assert WorkflowStep.PARSE_URL in step_names
        assert WorkflowStep.FETCH_CONTENT in step_names
        assert WorkflowStep.GENERATE_SCRIPT in step_names
        assert WorkflowStep.GENERATE_MEDIA in step_names
        assert WorkflowStep.UPLOAD_VIDEO in step_names

    @pytest.mark.asyncio
    async def test_workflow_with_user_opinion(self, workflow_orchestrator):
        """Test workflow with user opinion added."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"
        user_opinion = "I personally prefer pytest over unittest."

        with patch("requests.get") as mock_requests:
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(url, user_opinion=user_opinion)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.script is not None

    @pytest.mark.asyncio
    async def test_workflow_with_progress_callback(self, workflow_orchestrator):
        """Test that progress callbacks are invoked."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"
        callback_calls = []

        async def progress_callback(message: str):
            callback_calls.append(message)

        with patch("requests.get") as mock_requests:
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(
                url, update_callback=progress_callback
            )

        assert result.status == WorkflowStatus.COMPLETED
        assert len(callback_calls) > 0

    @pytest.mark.asyncio
    async def test_workflow_duration_tracked(self, workflow_orchestrator):
        """Test that workflow duration is tracked."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        with patch("requests.get") as mock_requests:
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(url)

        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_script_only_mode(self, workflow_orchestrator):
        """Test generating script without video creation."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        result = await workflow_orchestrator.generate_script_only(url)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.script is not None
        # Should not have uploaded to YouTube
        assert result.youtube_url is None

    @pytest.mark.asyncio
    async def test_script_only_steps(self, workflow_orchestrator):
        """Test that script-only mode only runs expected steps."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        result = await workflow_orchestrator.generate_script_only(url)

        step_names = [step.step for step in result.steps]

        assert WorkflowStep.PARSE_URL in step_names
        assert WorkflowStep.FETCH_CONTENT in step_names
        assert WorkflowStep.GENERATE_SCRIPT in step_names
        # Media and upload should not be in steps
        assert WorkflowStep.GENERATE_MEDIA not in step_names
        assert WorkflowStep.UPLOAD_VIDEO not in step_names


class TestWorkflowErrorRecovery:
    """Test error handling in E2E workflow."""

    @pytest.mark.asyncio
    async def test_invalid_url_handled(self, workflow_orchestrator):
        """Test that invalid URLs are handled gracefully."""
        from reddit_flow.exceptions.errors import InvalidURLError

        url = "https://invalid-url.com/not-reddit"

        with pytest.raises(InvalidURLError):
            await workflow_orchestrator.process_reddit_url(url)

    @pytest.mark.asyncio
    async def test_workflow_error_captured(self, workflow_orchestrator):
        """Test that workflow errors are properly captured."""
        from reddit_flow.exceptions.errors import InvalidURLError

        url = "https://not-a-real-url"

        with pytest.raises(InvalidURLError):
            await workflow_orchestrator.process_reddit_url(url)


class TestWorkflowDataFlow:
    """Test data flows correctly through workflow."""

    @pytest.mark.asyncio
    async def test_reddit_data_flows_to_script(self, workflow_orchestrator):
        """Test Reddit content flows to script generation."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        result = await workflow_orchestrator.generate_script_only(url)

        assert result.status == WorkflowStatus.COMPLETED
        # Script should reference the source
        assert result.script.source_subreddit is not None

    @pytest.mark.asyncio
    async def test_script_data_flows_to_video(self, workflow_orchestrator):
        """Test script flows to video generation."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        with patch("requests.get") as mock_requests:
            mock_response = MagicMock()
            mock_response.content = b"fake_video_data"
            mock_response.raise_for_status = MagicMock()
            mock_requests.return_value = mock_response

            result = await workflow_orchestrator.process_reddit_url(url)

        assert result.status == WorkflowStatus.COMPLETED
        # Video should be generated (media_result.video_url) and uploaded (youtube_url)
        assert result.media_result is not None
        assert result.media_result.video_url is not None or result.youtube_url is not None


class TestWorkflowIdempotency:
    """Test workflow behaves consistently."""

    @pytest.mark.asyncio
    async def test_same_url_generates_unique_workflow_ids(self, workflow_orchestrator):
        """Test each workflow execution gets unique ID."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"

        result1 = await workflow_orchestrator.generate_script_only(url)
        result2 = await workflow_orchestrator.generate_script_only(url)

        assert result1.workflow_id != result2.workflow_id

    @pytest.mark.asyncio
    async def test_multiple_workflows_independent(self, workflow_orchestrator):
        """Test multiple workflows don't interfere."""
        urls = [
            "https://www.reddit.com/r/python/comments/abc123/",
            "https://www.reddit.com/r/programming/comments/xyz789/",
            "https://www.reddit.com/r/learnpython/comments/def456/",
        ]

        results = []
        for url in urls:
            result = await workflow_orchestrator.generate_script_only(url)
            results.append(result)

        # All should complete successfully
        assert all(r.status == WorkflowStatus.COMPLETED for r in results)

        # All should have unique IDs
        workflow_ids = [r.workflow_id for r in results]
        assert len(set(workflow_ids)) == len(workflow_ids)
