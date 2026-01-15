"""
Unit tests for WorkflowOrchestrator.

Tests cover:
- Complete workflow execution
- Partial workflow execution (script-only)
- Step-by-step execution
- Error handling for each step
- Service coordination
- Workflow result structure
- Callback handling
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_flow.exceptions import (
    AIGenerationError,
    ContentError,
    InvalidURLError,
    MediaGenerationError,
    RedditAPIError,
    RedditFlowError,
    TTSError,
    VideoGenerationError,
    YouTubeUploadError,
)
from reddit_flow.models import AudioAsset, LinkInfo, RedditComment, RedditPost, VideoScript
from reddit_flow.services.media_service import MediaGenerationResult
from reddit_flow.services.upload_service import UploadResult
from reddit_flow.services.workflow_orchestrator import (
    StepResult,
    WorkflowOrchestrator,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_content_service():
    """Create a mock ContentService."""
    service = MagicMock()
    service.parse_reddit_url.return_value = LinkInfo(
        link="https://reddit.com/r/python/comments/abc123/test",
        subReddit="python",
        postId="abc123",
    )
    service.get_post_content.return_value = RedditPost(
        id="abc123",
        subreddit="python",
        title="Test Post Title",
        selftext="This is the post content.",
        author="test_user",
        score=100,
        url="https://reddit.com/r/python/comments/abc123/test",
        comments=[
            RedditComment(id="c1", author="commenter1", body="Great post!", score=50),
            RedditComment(id="c2", author="commenter2", body="I agree!", score=25),
        ],
    )
    return service


@pytest.fixture
def mock_script_service():
    """Create a mock ScriptService."""
    service = MagicMock()
    service.generate_script = AsyncMock(
        return_value=VideoScript(
            script="This is the generated script text.",
            title="Generated Video Title",
        )
    )
    return service


@pytest.fixture
def mock_media_service():
    """Create a mock MediaService."""
    service = MagicMock()
    service.generate_video_from_script = AsyncMock(
        return_value=MediaGenerationResult(
            audio_data=b"fake_audio_data",
            audio_asset=AudioAsset(asset_id="audio_123", url="https://example.com/audio"),
            video_id="video_456",
            video_url="https://example.com/video.mp4",
        )
    )
    return service


@pytest.fixture
def mock_upload_service():
    """Create a mock UploadService."""
    service = MagicMock()
    service.upload_from_url_with_script.return_value = UploadResult(
        video_id="yt_abc123",
        title="Uploaded Video Title",
        url="https://www.youtube.com/watch?v=yt_abc123",
        studio_url="https://studio.youtube.com/video/yt_abc123/edit",
    )
    return service


@pytest.fixture
def orchestrator(
    mock_content_service, mock_script_service, mock_media_service, mock_upload_service
):
    """Create a WorkflowOrchestrator with all mocked services."""
    return WorkflowOrchestrator(
        content_service=mock_content_service,
        script_service=mock_script_service,
        media_service=mock_media_service,
        upload_service=mock_upload_service,
    )


@pytest.fixture
def sample_url():
    """Sample Reddit URL for testing."""
    return "https://www.reddit.com/r/python/comments/abc123/test_post/"


# =============================================================================
# WorkflowStatus Tests
# =============================================================================


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.IN_PROGRESS == "in_progress"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"

    def test_status_is_string_enum(self):
        """Test status is a string enum."""
        assert isinstance(WorkflowStatus.PENDING, str)
        assert WorkflowStatus.COMPLETED == "completed"


class TestWorkflowStep:
    """Tests for WorkflowStep enum."""

    def test_step_values(self):
        """Test all step values exist."""
        assert WorkflowStep.PARSE_URL == "parse_url"
        assert WorkflowStep.FETCH_CONTENT == "fetch_content"
        assert WorkflowStep.GENERATE_SCRIPT == "generate_script"
        assert WorkflowStep.GENERATE_MEDIA == "generate_media"
        assert WorkflowStep.UPLOAD_VIDEO == "upload_video"


# =============================================================================
# StepResult Tests
# =============================================================================


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_create_step_result(self):
        """Test creating a StepResult."""
        result = StepResult(
            step=WorkflowStep.PARSE_URL,
            status=WorkflowStatus.COMPLETED,
        )
        assert result.step == WorkflowStep.PARSE_URL
        assert result.status == WorkflowStatus.COMPLETED
        assert isinstance(result.started_at, datetime)
        assert result.completed_at is None
        assert result.data is None
        assert result.error is None

    def test_create_step_result_with_data(self):
        """Test creating a StepResult with data."""
        result = StepResult(
            step=WorkflowStep.FETCH_CONTENT,
            status=WorkflowStatus.COMPLETED,
            data={"title": "Test Post", "comments_count": 5},
        )
        assert result.data["title"] == "Test Post"
        assert result.data["comments_count"] == 5

    def test_create_step_result_with_error(self):
        """Test creating a StepResult with error."""
        result = StepResult(
            step=WorkflowStep.GENERATE_SCRIPT,
            status=WorkflowStatus.FAILED,
            error="AI generation failed",
        )
        assert result.status == WorkflowStatus.FAILED
        assert result.error == "AI generation failed"


# =============================================================================
# WorkflowResult Tests
# =============================================================================


class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""

    def test_create_workflow_result(self):
        """Test creating a WorkflowResult."""
        result = WorkflowResult(workflow_id="wf_001")
        assert result.workflow_id == "wf_001"
        assert result.status == WorkflowStatus.PENDING
        assert isinstance(result.started_at, datetime)
        assert result.completed_at is None
        assert result.steps == []
        assert result.link_info is None
        assert result.post is None
        assert result.script is None
        assert result.media_result is None
        assert result.upload_result is None
        assert result.error is None

    def test_youtube_url_property(self):
        """Test youtube_url property returns upload URL."""
        result = WorkflowResult(workflow_id="wf_001")
        assert result.youtube_url is None

        result.upload_result = UploadResult(
            video_id="abc123",
            title="Test",
            url="https://youtube.com/watch?v=abc123",
            studio_url="https://studio.youtube.com/video/abc123/edit",
        )
        assert result.youtube_url == "https://youtube.com/watch?v=abc123"

    def test_video_id_property(self):
        """Test video_id property returns YouTube video ID."""
        result = WorkflowResult(workflow_id="wf_001")
        assert result.video_id is None

        result.upload_result = UploadResult(
            video_id="xyz789",
            title="Test",
            url="https://youtube.com/watch?v=xyz789",
            studio_url="https://studio.youtube.com/video/xyz789/edit",
        )
        assert result.video_id == "xyz789"

    def test_duration_seconds_property(self):
        """Test duration_seconds property."""
        result = WorkflowResult(workflow_id="wf_001")
        assert result.duration_seconds is None

        result.completed_at = datetime.now()
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0


# =============================================================================
# WorkflowOrchestrator Initialization Tests
# =============================================================================


class TestWorkflowOrchestratorInit:
    """Tests for WorkflowOrchestrator initialization."""

    def test_init_default(self):
        """Test default initialization."""
        orchestrator = WorkflowOrchestrator()
        assert orchestrator._content_service is None
        assert orchestrator._script_service is None
        assert orchestrator._media_service is None
        assert orchestrator._upload_service is None

    def test_init_with_services(
        self,
        mock_content_service,
        mock_script_service,
        mock_media_service,
        mock_upload_service,
    ):
        """Test initialization with services."""
        orchestrator = WorkflowOrchestrator(
            content_service=mock_content_service,
            script_service=mock_script_service,
            media_service=mock_media_service,
            upload_service=mock_upload_service,
        )
        assert orchestrator._content_service is mock_content_service
        assert orchestrator._script_service is mock_script_service
        assert orchestrator._media_service is mock_media_service
        assert orchestrator._upload_service is mock_upload_service

    def test_lazy_load_content_service(self):
        """Test lazy loading of ContentService."""
        orchestrator = WorkflowOrchestrator()

        with patch("reddit_flow.services.workflow_orchestrator.ContentService") as MockService:
            MockService.return_value = MagicMock()
            service = orchestrator.content_service
            MockService.assert_called_once()
            assert orchestrator._content_service is service

    def test_lazy_load_script_service(self):
        """Test lazy loading of ScriptService."""
        orchestrator = WorkflowOrchestrator()

        with patch("reddit_flow.services.workflow_orchestrator.ScriptService") as MockService:
            MockService.return_value = MagicMock()
            service = orchestrator.script_service
            MockService.assert_called_once()
            assert orchestrator._script_service is service

    def test_lazy_load_media_service(self):
        """Test lazy loading of MediaService."""
        orchestrator = WorkflowOrchestrator()

        with patch("reddit_flow.services.workflow_orchestrator.MediaService") as MockService:
            MockService.return_value = MagicMock()
            service = orchestrator.media_service
            MockService.assert_called_once()
            assert orchestrator._media_service is service

    def test_lazy_load_upload_service(self):
        """Test lazy loading of UploadService."""
        orchestrator = WorkflowOrchestrator()

        with patch("reddit_flow.services.workflow_orchestrator.UploadService") as MockService:
            MockService.return_value = MagicMock()
            service = orchestrator.upload_service
            MockService.assert_called_once()
            assert orchestrator._upload_service is service


# =============================================================================
# WorkflowOrchestrator Workflow ID Tests
# =============================================================================


class TestWorkflowIdGeneration:
    """Tests for workflow ID generation."""

    def test_generate_unique_workflow_ids(self, orchestrator):
        """Test workflow IDs are unique."""
        id1 = orchestrator._generate_workflow_id()
        id2 = orchestrator._generate_workflow_id()
        assert id1 != id2
        assert id1.startswith("wf_")
        assert id2.startswith("wf_")

    def test_workflow_id_format(self, orchestrator):
        """Test workflow ID format."""
        workflow_id = orchestrator._generate_workflow_id()
        assert workflow_id.startswith("wf_")
        parts = workflow_id.split("_")
        assert len(parts) == 4  # wf, date, time, counter
        assert parts[0] == "wf"


# =============================================================================
# WorkflowOrchestrator Complete Workflow Tests
# =============================================================================


class TestProcessRedditUrl:
    """Tests for process_reddit_url method."""

    @pytest.mark.asyncio
    async def test_complete_workflow_success(self, orchestrator, sample_url):
        """Test successful complete workflow."""
        result = await orchestrator.process_reddit_url(sample_url)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.error is None
        assert result.link_info is not None
        assert result.post is not None
        assert result.script is not None
        assert result.media_result is not None
        assert result.upload_result is not None
        assert result.youtube_url is not None
        assert len(result.steps) == 5
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_workflow_generates_unique_id(self, orchestrator, sample_url):
        """Test each workflow gets a unique ID."""
        result1 = await orchestrator.process_reddit_url(sample_url)
        result2 = await orchestrator.process_reddit_url(sample_url)

        assert result1.workflow_id != result2.workflow_id

    @pytest.mark.asyncio
    async def test_workflow_with_user_opinion(self, orchestrator, sample_url):
        """Test workflow passes user opinion to script service."""
        result = await orchestrator.process_reddit_url(
            sample_url,
            user_opinion="This is my opinion!",
        )

        orchestrator.script_service.generate_script.assert_called_once()
        call_kwargs = orchestrator.script_service.generate_script.call_args.kwargs
        assert call_kwargs["user_opinion"] == "This is my opinion!"
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_with_avatar_id(self, orchestrator, sample_url):
        """Test workflow passes avatar ID to media service."""
        result = await orchestrator.process_reddit_url(
            sample_url,
            avatar_id="custom_avatar_123",
        )

        orchestrator.media_service.generate_video_from_script.assert_called_once()
        call_kwargs = orchestrator.media_service.generate_video_from_script.call_args.kwargs
        assert call_kwargs["avatar_id"] == "custom_avatar_123"
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_with_test_mode(self, orchestrator, sample_url):
        """Test workflow passes test mode to media service."""
        result = await orchestrator.process_reddit_url(
            sample_url,
            test_mode=True,
        )

        orchestrator.media_service.generate_video_from_script.assert_called_once()
        call_kwargs = orchestrator.media_service.generate_video_from_script.call_args.kwargs
        assert call_kwargs["test_mode"] is True
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_with_callback(self, orchestrator, sample_url):
        """Test workflow calls update callback."""
        callback = AsyncMock()

        result = await orchestrator.process_reddit_url(
            sample_url,
            update_callback=callback,
        )

        assert callback.await_count >= 5  # At least one per step
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_steps_recorded(self, orchestrator, sample_url):
        """Test all steps are recorded in result."""
        result = await orchestrator.process_reddit_url(sample_url)

        assert len(result.steps) == 5
        step_names = [step.step for step in result.steps]
        assert step_names == [
            WorkflowStep.PARSE_URL,
            WorkflowStep.FETCH_CONTENT,
            WorkflowStep.GENERATE_SCRIPT,
            WorkflowStep.GENERATE_MEDIA,
            WorkflowStep.UPLOAD_VIDEO,
        ]
        assert all(step.status == WorkflowStatus.COMPLETED for step in result.steps)


# =============================================================================
# WorkflowOrchestrator Error Handling Tests
# =============================================================================


class TestWorkflowErrorHandling:
    """Tests for error handling in workflows."""

    @pytest.mark.asyncio
    async def test_invalid_url_error(self, orchestrator):
        """Test InvalidURLError is handled properly."""
        orchestrator.content_service.parse_reddit_url.side_effect = InvalidURLError(
            "Invalid Reddit URL"
        )

        with pytest.raises(InvalidURLError):
            await orchestrator.process_reddit_url("invalid_url")

    @pytest.mark.asyncio
    async def test_invalid_url_error_result_status(self, orchestrator):
        """Test result status on InvalidURLError."""
        orchestrator.content_service.parse_reddit_url.side_effect = InvalidURLError(
            "Invalid Reddit URL"
        )

        try:
            await orchestrator.process_reddit_url("invalid_url")
        except InvalidURLError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_reddit_api_error(self, orchestrator, sample_url):
        """Test RedditAPIError is handled properly."""
        orchestrator.content_service.get_post_content.side_effect = RedditAPIError(
            "Reddit API failed"
        )

        with pytest.raises(RedditAPIError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_content_error(self, orchestrator, sample_url):
        """Test ContentError is handled properly."""
        orchestrator.content_service.get_post_content.side_effect = ContentError("No content found")

        with pytest.raises(ContentError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_ai_generation_error(self, orchestrator, sample_url):
        """Test AIGenerationError is handled properly."""
        orchestrator.script_service.generate_script = AsyncMock(
            side_effect=AIGenerationError("AI generation failed")
        )

        with pytest.raises(AIGenerationError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_tts_error(self, orchestrator, sample_url):
        """Test TTSError is handled properly."""
        orchestrator.media_service.generate_video_from_script = AsyncMock(
            side_effect=TTSError("TTS failed")
        )

        with pytest.raises(TTSError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_video_generation_error(self, orchestrator, sample_url):
        """Test VideoGenerationError is handled properly."""
        orchestrator.media_service.generate_video_from_script = AsyncMock(
            side_effect=VideoGenerationError("Video generation failed")
        )

        with pytest.raises(VideoGenerationError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_media_generation_error(self, orchestrator, sample_url):
        """Test MediaGenerationError is handled properly."""
        orchestrator.media_service.generate_video_from_script = AsyncMock(
            side_effect=MediaGenerationError("Media generation failed")
        )

        with pytest.raises(MediaGenerationError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_youtube_upload_error(self, orchestrator, sample_url):
        """Test YouTubeUploadError is handled properly."""
        orchestrator.upload_service.upload_from_url_with_script.side_effect = YouTubeUploadError(
            "Upload failed"
        )

        with pytest.raises(YouTubeUploadError):
            await orchestrator.process_reddit_url(sample_url)

    @pytest.mark.asyncio
    async def test_unexpected_error_wrapped(self, orchestrator, sample_url):
        """Test unexpected errors are wrapped in RedditFlowError."""
        orchestrator.content_service.get_post_content.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(RedditFlowError) as exc_info:
            await orchestrator.process_reddit_url(sample_url)

        assert "Unexpected error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_callback_called_on_failure(self, orchestrator, sample_url):
        """Test callback is called with error message on failure."""
        callback = AsyncMock()
        orchestrator.content_service.get_post_content.side_effect = ContentError("No content")

        with pytest.raises(ContentError):
            await orchestrator.process_reddit_url(sample_url, update_callback=callback)

        # Check callback was called with error message
        error_calls = [call for call in callback.await_args_list if "Failed" in str(call)]
        assert len(error_calls) >= 1


# =============================================================================
# WorkflowOrchestrator Partial Workflow Tests
# =============================================================================


class TestProcessWithLinkInfo:
    """Tests for process_with_link_info method."""

    @pytest.mark.asyncio
    async def test_process_with_link_info_success(self, orchestrator):
        """Test processing with pre-parsed LinkInfo."""
        link_info = LinkInfo(
            link="https://reddit.com/r/test/comments/xyz789/",
            subReddit="test",
            postId="xyz789",
        )

        result = await orchestrator.process_with_link_info(link_info)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.link_info == link_info
        assert len(result.steps) == 5  # Including pre-added parse step
        # Content service should NOT have parse_reddit_url called
        orchestrator.content_service.parse_reddit_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_with_link_info_skips_parsing(self, orchestrator):
        """Test that parse_url step is pre-populated."""
        link_info = LinkInfo(
            link="https://reddit.com/r/test/comments/xyz789/",
            subReddit="test",
            postId="xyz789",
        )

        result = await orchestrator.process_with_link_info(link_info)

        first_step = result.steps[0]
        assert first_step.step == WorkflowStep.PARSE_URL
        assert first_step.status == WorkflowStatus.COMPLETED


class TestGenerateScriptOnly:
    """Tests for generate_script_only method."""

    @pytest.mark.asyncio
    async def test_generate_script_only_success(self, orchestrator, sample_url):
        """Test script-only workflow."""
        result = await orchestrator.generate_script_only(sample_url)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.link_info is not None
        assert result.post is not None
        assert result.script is not None
        assert result.media_result is None  # Not generated
        assert result.upload_result is None  # Not uploaded
        assert len(result.steps) == 3  # Only 3 steps

    @pytest.mark.asyncio
    async def test_generate_script_only_steps(self, orchestrator, sample_url):
        """Test script-only workflow has correct steps."""
        result = await orchestrator.generate_script_only(sample_url)

        step_names = [step.step for step in result.steps]
        assert step_names == [
            WorkflowStep.PARSE_URL,
            WorkflowStep.FETCH_CONTENT,
            WorkflowStep.GENERATE_SCRIPT,
        ]

    @pytest.mark.asyncio
    async def test_generate_script_only_with_opinion(self, orchestrator, sample_url):
        """Test script-only workflow with user opinion."""
        result = await orchestrator.generate_script_only(
            sample_url,
            user_opinion="My thoughts on this...",
        )

        orchestrator.script_service.generate_script.assert_called_once()
        call_kwargs = orchestrator.script_service.generate_script.call_args.kwargs
        assert call_kwargs["user_opinion"] == "My thoughts on this..."
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_generate_script_only_no_media_calls(self, orchestrator, sample_url):
        """Test script-only workflow doesn't call media/upload services."""
        await orchestrator.generate_script_only(sample_url)

        orchestrator.media_service.generate_video_from_script.assert_not_called()
        orchestrator.upload_service.upload_from_url_with_script.assert_not_called()


# =============================================================================
# WorkflowOrchestrator Service Verification Tests
# =============================================================================


class TestVerifyServices:
    """Tests for verify_services method."""

    def test_verify_services_all_pass(
        self,
        mock_content_service,
        mock_script_service,
        mock_media_service,
        mock_upload_service,
    ):
        """Test verify_services when all services pass."""
        # Add required attributes for verification
        mock_content_service.reddit_client = MagicMock()
        mock_script_service.gemini_client = MagicMock()
        mock_media_service.elevenlabs_client = MagicMock()
        mock_media_service.heygen_client = MagicMock()
        mock_upload_service.youtube_client = MagicMock()

        orchestrator = WorkflowOrchestrator(
            content_service=mock_content_service,
            script_service=mock_script_service,
            media_service=mock_media_service,
            upload_service=mock_upload_service,
        )

        result = orchestrator.verify_services()

        assert result["content_service"] is True
        assert result["script_service"] is True
        assert result["media_service"] is True
        assert result["upload_service"] is True

    def test_verify_services_content_fails(
        self,
        mock_content_service,
        mock_script_service,
        mock_media_service,
        mock_upload_service,
    ):
        """Test verify_services when content service fails."""
        # Content service fails
        type(mock_content_service).reddit_client = property(
            lambda self: (_ for _ in ()).throw(Exception("No client"))
        )

        # Others pass
        mock_script_service.gemini_client = MagicMock()
        mock_media_service.elevenlabs_client = MagicMock()
        mock_media_service.heygen_client = MagicMock()
        mock_upload_service.youtube_client = MagicMock()

        orchestrator = WorkflowOrchestrator(
            content_service=mock_content_service,
            script_service=mock_script_service,
            media_service=mock_media_service,
            upload_service=mock_upload_service,
        )

        result = orchestrator.verify_services()

        assert result["content_service"] is False
        assert result["script_service"] is True


# =============================================================================
# Step Execution Tests
# =============================================================================


class TestStepExecution:
    """Tests for individual step execution."""

    @pytest.mark.asyncio
    async def test_parse_url_step_success(self, orchestrator, sample_url):
        """Test parse URL step executes correctly."""
        result = WorkflowResult(workflow_id="test")
        result = await orchestrator._execute_parse_url(result, sample_url, None)

        assert result.link_info is not None
        assert result.link_info.subreddit == "python"
        assert result.link_info.post_id == "abc123"
        assert len(result.steps) == 1
        assert result.steps[0].step == WorkflowStep.PARSE_URL
        assert result.steps[0].status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_parse_url_step_failure(self, orchestrator):
        """Test parse URL step handles failure."""
        orchestrator.content_service.parse_reddit_url.side_effect = InvalidURLError("Bad URL")
        result = WorkflowResult(workflow_id="test")

        with pytest.raises(InvalidURLError):
            await orchestrator._execute_parse_url(result, "bad_url", None)

    @pytest.mark.asyncio
    async def test_fetch_content_step_success(self, orchestrator, sample_url):
        """Test fetch content step executes correctly."""
        result = WorkflowResult(workflow_id="test")
        result.link_info = LinkInfo(
            link=sample_url,
            subReddit="python",
            postId="abc123",
        )

        result = await orchestrator._execute_fetch_content(result, None)

        assert result.post is not None
        assert result.post.subreddit == "python"
        step = result.steps[-1]
        assert step.step == WorkflowStep.FETCH_CONTENT
        assert step.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_generate_script_step_success(self, orchestrator):
        """Test generate script step executes correctly."""
        result = WorkflowResult(workflow_id="test")
        result.post = RedditPost(
            id="abc123",
            subreddit="python",
            title="Test",
            selftext="Content",
            author="user",
            score=100,
            url="https://example.com",
            comments=[],
        )

        result = await orchestrator._execute_generate_script(result, None, None)

        assert result.script is not None
        step = result.steps[-1]
        assert step.step == WorkflowStep.GENERATE_SCRIPT
        assert step.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_generate_media_step_success(self, orchestrator):
        """Test generate media step executes correctly."""
        result = WorkflowResult(workflow_id="test")
        result.script = VideoScript(script="Test script", title="Test Title")

        result = await orchestrator._execute_generate_media(result, None, False, None, None)

        assert result.media_result is not None
        assert result.media_result.video_url is not None
        step = result.steps[-1]
        assert step.step == WorkflowStep.GENERATE_MEDIA
        assert step.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_upload_video_step_success(self, orchestrator):
        """Test upload video step executes correctly."""
        result = WorkflowResult(workflow_id="test")
        result.link_info = LinkInfo(
            link="https://reddit.com/r/test/comments/abc123/",
            subReddit="test",
            postId="abc123",
        )
        result.script = VideoScript(script="Test script", title="Test Title")
        result.media_result = MediaGenerationResult(
            audio_data=b"audio",
            audio_asset=AudioAsset(asset_id="a1", url="https://example.com/audio"),
            video_id="v1",
            video_url="https://example.com/video.mp4",
        )

        result = await orchestrator._execute_upload_video(
            result, "https://reddit.com/r/test/comments/abc123/", False, None
        )

        assert result.upload_result is not None
        assert result.upload_result.video_id == "yt_abc123"
        step = result.steps[-1]
        assert step.step == WorkflowStep.UPLOAD_VIDEO
        assert step.status == WorkflowStatus.COMPLETED


# =============================================================================
# Integration-Like Tests
# =============================================================================


class TestWorkflowIntegration:
    """Integration-like tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow_service_coordination(self, orchestrator, sample_url):
        """Test services are called in correct order with correct data."""
        result = await orchestrator.process_reddit_url(
            sample_url,
            user_opinion="Great post!",
            avatar_id="avatar_123",
            test_mode=True,
        )

        # Verify service calls
        orchestrator.content_service.parse_reddit_url.assert_called_once_with(sample_url)
        orchestrator.content_service.get_post_content.assert_called_once_with(
            subreddit="python",
            post_id="abc123",
        )

        orchestrator.script_service.generate_script.assert_called_once()
        script_call = orchestrator.script_service.generate_script.call_args
        assert script_call.kwargs["user_opinion"] == "Great post!"

        orchestrator.media_service.generate_video_from_script.assert_called_once()
        media_call = orchestrator.media_service.generate_video_from_script.call_args
        assert media_call.kwargs["avatar_id"] == "avatar_123"
        assert media_call.kwargs["test_mode"] is True

        orchestrator.upload_service.upload_from_url_with_script.assert_called_once()

        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_captures_duration(self, orchestrator, sample_url):
        """Test workflow captures duration correctly."""
        result = await orchestrator.process_reddit_url(sample_url)

        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_workflow_step_data_populated(self, orchestrator, sample_url):
        """Test step data is populated with useful information."""
        result = await orchestrator.process_reddit_url(sample_url)

        # Check parse step has subreddit and post_id
        parse_step = result.steps[0]
        assert parse_step.data["subreddit"] == "python"
        assert parse_step.data["post_id"] == "abc123"

        # Check fetch step has title and comments count
        fetch_step = result.steps[1]
        assert "title" in fetch_step.data
        assert "comments_count" in fetch_step.data

        # Check script step has title and word count
        script_step = result.steps[2]
        assert "title" in script_step.data
        assert "word_count" in script_step.data

        # Check media step has video info
        media_step = result.steps[3]
        assert "video_id" in media_step.data
        assert "video_url" in media_step.data

        # Check upload step has YouTube info
        upload_step = result.steps[4]
        assert "video_id" in upload_step.data
        assert "url" in upload_step.data


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_workflow_with_empty_user_opinion(self, orchestrator, sample_url):
        """Test workflow handles empty user opinion."""
        result = await orchestrator.process_reddit_url(sample_url, user_opinion="")

        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_with_long_url(self, orchestrator):
        """Test workflow handles long URLs."""
        long_url = "https://www.reddit.com/r/python/comments/abc123/" + "a" * 1000

        # Mock should still work
        result = await orchestrator.process_reddit_url(long_url)

        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_multiple_workflows_sequential(self, orchestrator, sample_url):
        """Test running multiple workflows sequentially."""
        results = []
        for _ in range(3):
            result = await orchestrator.process_reddit_url(sample_url)
            results.append(result)

        # All should succeed with unique IDs
        assert all(r.status == WorkflowStatus.COMPLETED for r in results)
        workflow_ids = [r.workflow_id for r in results]
        assert len(set(workflow_ids)) == 3  # All unique

    @pytest.mark.asyncio
    async def test_callback_receives_all_updates(self, orchestrator, sample_url):
        """Test callback receives updates for all steps."""
        updates = []

        async def capture_callback(message):
            updates.append(message)

        await orchestrator.process_reddit_url(sample_url, update_callback=capture_callback)

        # Should have at least one update per step plus completion
        assert len(updates) >= 6

    @pytest.mark.asyncio
    async def test_workflow_result_preserves_all_data(self, orchestrator, sample_url):
        """Test workflow result preserves all intermediate data."""
        result = await orchestrator.process_reddit_url(
            sample_url,
            user_opinion="Test opinion",
        )

        # All data should be preserved
        assert result.link_info.subreddit == "python"
        assert result.post.title == "Test Post Title"
        assert result.script.script == "This is the generated script text."
        assert result.media_result.video_id == "video_456"
        assert result.upload_result.video_id == "yt_abc123"
