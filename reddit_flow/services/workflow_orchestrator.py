"""
Workflow orchestrator for coordinating the complete content generation pipeline.

This module provides the WorkflowOrchestrator class that coordinates all services
to transform Reddit content into YouTube videos.
"""

import inspect
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from reddit_flow.clients import MediumClient
from reddit_flow.config import get_logger
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
from reddit_flow.models import (
    LinkInfo,
    PipelineEvent,
    PipelineRequest,
    PipelineResult,
    PublishRequest,
    RedditPost,
    VideoScript,
)

# from reddit_flow.pipeline.providers import (
#     AnthropicScriptProvider,
#     ElevenLabsVoiceProvider,
#     GeminiScriptProvider,
#     GoogleCloudTTSProvider,
#     HeyGenVideoProvider,
#     OpenAIScriptProvider,
#     OpenAITTSProvider,
#     TavusVideoProvider,
# )
from reddit_flow.pipeline.publishers import YouTubePublisher
from reddit_flow.pipeline.registry import ProviderRegistry, SourceAdapterRegistry
from reddit_flow.pipeline.sources import (
    MediumArticleSourceAdapter,
    MediumFeedSourceAdapter,
    RedditSourceAdapter,
)
from reddit_flow.services.content_service import ContentService
from reddit_flow.services.media_service import MediaGenerationResult, MediaService
from reddit_flow.services.script_service import ScriptService
from reddit_flow.services.upload_service import UploadResult, UploadService

logger = get_logger(__name__)


class WorkflowStatus(str, Enum):
    """Status of workflow execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(str, Enum):
    """Steps in the workflow pipeline."""

    PARSE_URL = "parse_url"
    FETCH_CONTENT = "fetch_content"
    GENERATE_SCRIPT = "generate_script"
    GENERATE_MEDIA = "generate_media"
    UPLOAD_VIDEO = "upload_video"


@dataclass
class StepResult:
    """
    Result of a single workflow step.

    Attributes:
        step: The workflow step that was executed.
        status: Status of the step.
        started_at: When the step started.
        completed_at: When the step completed.
        data: Step output data.
        error: Error message if step failed.
    """

    step: WorkflowStep
    status: WorkflowStatus
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    data: Any = None
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    """
    Complete result of a workflow execution.

    Attributes:
        workflow_id: Unique identifier for this workflow run.
        status: Overall workflow status.
        started_at: When workflow started.
        completed_at: When workflow completed.
        steps: Results of individual steps.
        link_info: Parsed Reddit URL information.
        post: Fetched Reddit post.
        script: Generated video script.
        media_result: Generated audio/video assets.
        upload_result: YouTube upload details.
        error: Error message if workflow failed.
    """

    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    steps: List[StepResult] = field(default_factory=list)
    link_info: Optional[LinkInfo] = None
    post: Optional[RedditPost] = None
    script: Optional[VideoScript] = None
    media_result: Optional[MediaGenerationResult] = None
    upload_result: Optional[UploadResult] = None
    error: Optional[str] = None

    @property
    def youtube_url(self) -> Optional[str]:
        """Get YouTube URL if upload was successful."""
        return self.upload_result.url if self.upload_result else None

    @property
    def video_id(self) -> Optional[str]:
        """Get YouTube video ID if upload was successful."""
        return self.upload_result.video_id if self.upload_result else None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get total workflow duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class WorkflowOrchestrator:
    """
    Orchestrates the complete content generation workflow.

    This class coordinates all services to transform Reddit URLs into
    YouTube videos through the following pipeline:
    1. Parse Reddit URL → ContentService
    2. Fetch post and comments → ContentService
    3. Generate video script → ScriptService
    4. Generate audio/video → MediaService
    5. Upload to YouTube → UploadService

    Attributes:
        content_service: Service for Reddit content extraction.
        script_service: Service for AI script generation.
        media_service: Service for audio/video generation.
        upload_service: Service for YouTube uploads.

    Example:
        >>> orchestrator = WorkflowOrchestrator()
        >>> result = await orchestrator.process_reddit_url(
        ...     "https://reddit.com/r/python/comments/abc123/",
        ...     user_opinion="This is interesting!"
        ... )
        >>> print(result.youtube_url)
    """

    def __init__(
        self,
        content_service: Optional[ContentService] = None,
        script_service: Optional[ScriptService] = None,
        media_service: Optional[MediaService] = None,
        upload_service: Optional[UploadService] = None,
        source_registry: Optional[SourceAdapterRegistry] = None,
        publisher_registry: Optional[ProviderRegistry[YouTubePublisher]] = None,
    ) -> None:
        """
        Initialize WorkflowOrchestrator.

        Args:
            content_service: Optional ContentService instance.
            script_service: Optional ScriptService instance.
            media_service: Optional MediaService instance.
            upload_service: Optional UploadService instance.
            source_registry: Optional SourceAdapterRegistry instance.
            publisher_registry: Optional ProviderRegistry[YouTubePublisher] instance.
        """
        self._content_service = content_service
        self._script_service = script_service
        self._media_service = media_service
        self._upload_service = upload_service
        self._source_registry = source_registry
        self._publisher_registry = publisher_registry
        self._workflow_counter = 0
        logger.info("WorkflowOrchestrator initialized")

    @property
    def content_service(self) -> ContentService:
        """Lazy-load ContentService on first access."""
        if self._content_service is None:
            self._content_service = ContentService()
        return self._content_service

    @property
    def script_service(self) -> ScriptService:
        """Lazy-load ScriptService on first access."""
        if self._script_service is None:
            self._script_service = ScriptService()
        return self._script_service

    @property
    def media_service(self) -> MediaService:
        """Lazy-load MediaService on first access."""
        if self._media_service is None:
            self._media_service = MediaService()
        return self._media_service

    @property
    def upload_service(self) -> UploadService:
        """Lazy-load UploadService on first access."""
        if self._upload_service is None:
            self._upload_service = UploadService()
        return self._upload_service

    @property
    def source_registry(self) -> SourceAdapterRegistry:
        """Lazy-load the canonical source registry."""
        if self._source_registry is None:
            medium_client = MediumClient()
            self._source_registry = SourceAdapterRegistry(
                adapters=[
                    RedditSourceAdapter(self.content_service),
                    MediumFeedSourceAdapter(medium_client),
                    MediumArticleSourceAdapter(medium_client),
                ]
            )
        return self._source_registry

    @property
    def publisher_registry(self) -> ProviderRegistry[YouTubePublisher]:
        """Lazy-load the publish destination registry."""
        if self._publisher_registry is None:
            registry: ProviderRegistry[YouTubePublisher] = ProviderRegistry(
                provider_kind="publisher"
            )
            registry.register("youtube", YouTubePublisher(self.upload_service))
            self._publisher_registry = registry
        return self._publisher_registry

    def _generate_workflow_id(self) -> str:
        """Generate a unique workflow ID."""
        self._workflow_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"wf_{timestamp}_{self._workflow_counter:04d}"

    def _create_step_result(
        self,
        step: WorkflowStep,
        status: WorkflowStatus,
        data: Any = None,
        error: Optional[str] = None,
    ) -> StepResult:
        """Create a StepResult with current timestamp."""
        result = StepResult(
            step=step,
            status=status,
            data=data,
            error=error,
        )
        if status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            result.completed_at = datetime.now()
        return result

    async def _emit_pipeline_event(
        self,
        result: PipelineResult,
        event_type: str,
        step: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[PipelineEvent], Any]] = None,
    ) -> None:
        """Append a channel-neutral event and optionally deliver it to a callback."""
        event = PipelineEvent(
            event_type=event_type,
            step=step,
            message=message,
            metadata=metadata or {},
        )
        result.events.append(event)

        if event_callback:
            callback_result = event_callback(event)
            if inspect.isawaitable(callback_result):
                await callback_result

    async def process_request(
        self,
        request: PipelineRequest,
        event_callback: Optional[Callable[[PipelineEvent], Any]] = None,
        timeout: Optional[int] = None,
    ) -> PipelineResult:
        """
        Execute the generic source-agnostic pipeline for supported sources.

        This initial implementation routes Reddit requests through canonical
        adapters and publisher registries while preserving the legacy services.
        """
        workflow_id = self._generate_workflow_id()
        result = PipelineResult(workflow_id=workflow_id, status=WorkflowStatus.IN_PROGRESS)

        logger.info(
            "Starting generic pipeline %s for source URL: %s",
            workflow_id,
            request.source_url[:100],
        )

        try:
            await self._emit_pipeline_event(
                result,
                event_type="status",
                step="resolve_source",
                message="Resolving source adapter...",
                metadata={"source_url": request.source_url},
                event_callback=event_callback,
            )
            source_adapter = self.source_registry.resolve(request)

            await self._emit_pipeline_event(
                result,
                event_type="status",
                step="fetch_content",
                message=f"Fetching content from {source_adapter.source_name}...",
                metadata={"source_name": source_adapter.source_name},
                event_callback=event_callback,
            )
            content_item = source_adapter.fetch_content(request)
            result.content_item = content_item

            legacy_post = content_item.metadata.get("legacy_post")

            await self._emit_pipeline_event(
                result,
                event_type="status",
                step="generate_script",
                message="Generating script...",
                metadata={"provider": "legacy_script_service"},
                event_callback=event_callback,
            )
            if isinstance(legacy_post, RedditPost):
                script = await self.script_service.generate_script(
                    post=legacy_post,
                    user_opinion=request.user_input,
                )
            else:
                script = await self.script_service.generate_script_from_content_item(
                    content_item=content_item,
                    user_opinion=request.user_input,
                )
            result.script = script

            await self._emit_pipeline_event(
                result,
                event_type="status",
                step="generate_media",
                message="Generating media...",
                metadata={"provider": "legacy_media_service"},
                event_callback=event_callback,
            )
            media_result = await self.media_service.generate_video_from_script(
                script=script,
                avatar_id=request.metadata.get("avatar_id"),
                test_mode=request.metadata.get("test_mode", False),
                wait_for_completion=True,
                timeout=timeout,
            )
            result.media_result = media_result

            for destination in request.destinations:
                await self._emit_pipeline_event(
                    result,
                    event_type="status",
                    step=f"publish_{destination.name}",
                    message=f"Publishing to {destination.name}...",
                    metadata={"destination": destination.name},
                    event_callback=event_callback,
                )

                publisher = self.publisher_registry.get(destination.name)
                publish_result = publisher.publish(
                    PublishRequest(
                        destination=destination.name,
                        media_url=media_result.video_url,
                        script=script,
                        content_item=content_item,
                        additional_description=f"\n\nSource: {content_item.source_url}",
                        keep_local_file=bool(request.metadata.get("keep_local_file", False)),
                        metadata=destination.metadata,
                    )
                )
                result.publish_results.append(publish_result)

            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now()

            await self._emit_pipeline_event(
                result,
                event_type="completed",
                step="completed",
                message="Pipeline completed successfully",
                metadata={"publish_url": result.primary_publish_url},
                event_callback=event_callback,
            )

            logger.info(
                "Generic pipeline %s completed successfully. Primary URL: %s",
                workflow_id,
                result.primary_publish_url,
            )
            return result

        except Exception as exc:
            result.status = WorkflowStatus.FAILED
            result.error = str(exc)
            result.completed_at = datetime.now()

            await self._emit_pipeline_event(
                result,
                event_type="error",
                step="failed",
                message=f"Pipeline failed: {exc}",
                metadata={"error_type": exc.__class__.__name__},
                event_callback=event_callback,
            )
            logger.error("Generic pipeline %s failed: %s", workflow_id, exc, exc_info=True)
            raise

    async def process_reddit_url(
        self,
        url: str,
        user_opinion: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        keep_local_file: bool = False,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> WorkflowResult:
        """
        Execute the complete workflow from Reddit URL to YouTube upload.

        This method orchestrates all services to:
        1. Parse the Reddit URL
        2. Fetch post content and comments
        3. Generate a video script using AI
        4. Create audio and avatar video
        5. Upload to YouTube

        Args:
            url: Reddit post URL.
            user_opinion: Optional user commentary to include.
            avatar_id: Optional HeyGen avatar ID override.
            test_mode: Use HeyGen test mode (watermarked).
            keep_local_file: Keep downloaded video after upload.
            update_callback: Optional async callback for progress updates.
            timeout: Override video generation timeout.

        Returns:
            WorkflowResult with all outputs and status.

        Raises:
            InvalidURLError: If URL cannot be parsed.
            RedditAPIError: If Reddit fetch fails.
            AIGenerationError: If script generation fails.
            TTSError: If audio generation fails.
            VideoGenerationError: If video generation fails.
            YouTubeUploadError: If upload fails.
        """
        workflow_id = self._generate_workflow_id()
        result = WorkflowResult(workflow_id=workflow_id)
        result.status = WorkflowStatus.IN_PROGRESS

        logger.info(f"Starting workflow {workflow_id} for URL: {url[:50]}...")

        try:
            # Step 1: Parse Reddit URL
            result = await self._execute_parse_url(result, url, update_callback)

            # Step 2: Fetch content
            result = await self._execute_fetch_content(result, update_callback)

            # Step 3: Generate script
            result = await self._execute_generate_script(result, user_opinion, update_callback)

            # Step 4: Generate media
            result = await self._execute_generate_media(
                result, avatar_id, test_mode, update_callback, timeout
            )

            # Step 5: Upload to YouTube
            result = await self._execute_upload_video(result, url, keep_local_file, update_callback)

            # Mark workflow as complete
            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now()

            logger.info(
                f"Workflow {workflow_id} completed successfully. "
                f"YouTube URL: {result.youtube_url}"
            )

            if update_callback:
                await update_callback(f"✅ Complete! Video uploaded: {result.youtube_url}")

        except (
            InvalidURLError,
            RedditAPIError,
            ContentError,
            AIGenerationError,
            TTSError,
            VideoGenerationError,
            MediaGenerationError,
            YouTubeUploadError,
        ) as e:
            result.status = WorkflowStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

            logger.error(f"Workflow {workflow_id} failed: {e}")

            if update_callback:
                await update_callback(f"❌ Failed: {e}")

            raise

        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.error = f"Unexpected error: {e}"
            result.completed_at = datetime.now()

            logger.error(f"Workflow {workflow_id} failed unexpectedly: {e}", exc_info=True)

            if update_callback:
                await update_callback(f"❌ Unexpected error: {e}")

            raise RedditFlowError(f"Workflow failed unexpectedly: {e}") from e

        return result

    async def _execute_parse_url(
        self,
        result: WorkflowResult,
        url: str,
        update_callback: Optional[Callable[[str], Any]],
    ) -> WorkflowResult:
        """Execute Step 1: Parse Reddit URL."""
        step = WorkflowStep.PARSE_URL

        if update_callback:
            await update_callback("Step 1/5: Parsing Reddit URL...")

        logger.debug(f"Step 1: Parsing URL - {url[:50]}...")

        try:
            link_info = self.content_service.parse_reddit_url(url)
            result.link_info = link_info

            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.COMPLETED,
                data={
                    "subreddit": link_info.subreddit,
                    "post_id": link_info.post_id,
                },
            )
            result.steps.append(step_result)

            logger.info(f"Step 1 complete: r/{link_info.subreddit}, " f"post={link_info.post_id}")

        except InvalidURLError as e:
            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.FAILED,
                error=str(e),
            )
            result.steps.append(step_result)
            raise

        return result

    async def _execute_fetch_content(
        self,
        result: WorkflowResult,
        update_callback: Optional[Callable[[str], Any]],
    ) -> WorkflowResult:
        """Execute Step 2: Fetch Reddit content."""
        step = WorkflowStep.FETCH_CONTENT

        if update_callback:
            await update_callback("Step 2/5: Fetching Reddit content...")

        link_info = result.link_info
        if link_info is None:
            raise RedditFlowError("Cannot fetch content: link_info is None")

        logger.debug(f"Step 2: Fetching r/{link_info.subreddit}/{link_info.post_id}")

        try:
            post = self.content_service.get_post_content(
                subreddit=link_info.subreddit,
                post_id=link_info.post_id,
            )
            result.post = post

            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.COMPLETED,
                data={
                    "title": post.title[:50] if post.title else "",
                    "comments_count": len(post.comments),
                    "author": post.author,
                },
            )
            result.steps.append(step_result)

            logger.info(
                f"Step 2 complete: '{post.title[:30]}...' " f"with {len(post.comments)} comments"
            )

        except (ContentError, RedditAPIError) as e:
            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.FAILED,
                error=str(e),
            )
            result.steps.append(step_result)
            raise

        return result

    async def _execute_generate_script(
        self,
        result: WorkflowResult,
        user_opinion: Optional[str],
        update_callback: Optional[Callable[[str], Any]],
    ) -> WorkflowResult:
        """Execute Step 3: Generate video script."""
        step = WorkflowStep.GENERATE_SCRIPT

        if update_callback:
            await update_callback("Step 3/5: Generating AI script...")

        post = result.post
        if post is None:
            raise RedditFlowError("Cannot generate script: post is None")

        logger.debug(f"Step 3: Generating script for post '{post.id}'")

        try:
            script = await self.script_service.generate_script(
                post=post,
                user_opinion=user_opinion,
            )
            result.script = script

            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.COMPLETED,
                data={
                    "title": script.title[:50] if script.title else "",
                    "word_count": script.word_count,
                },
            )
            result.steps.append(step_result)

            logger.info(
                f"Step 3 complete: Script '{script.title[:30]}...' " f"({script.word_count} words)"
            )

        except AIGenerationError as e:
            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.FAILED,
                error=str(e),
            )
            result.steps.append(step_result)
            raise

        return result

    async def _execute_generate_media(
        self,
        result: WorkflowResult,
        avatar_id: Optional[str],
        test_mode: bool,
        update_callback: Optional[Callable[[str], Any]],
        timeout: Optional[int],
    ) -> WorkflowResult:
        """Execute Step 4: Generate audio and video."""
        step = WorkflowStep.GENERATE_MEDIA

        if update_callback:
            await update_callback("Step 4/5: Generating audio and video...")

        script = result.script
        if script is None:
            raise RedditFlowError("Cannot generate media: script is None")

        logger.debug(f"Step 4: Generating media for script '{script.title[:30]}...'")

        try:
            media_result = await self.media_service.generate_video_from_script(
                script=script,
                avatar_id=avatar_id,
                test_mode=test_mode,
                wait_for_completion=True,
                update_callback=update_callback,
                timeout=timeout,
            )
            result.media_result = media_result

            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.COMPLETED,
                data={
                    "video_id": media_result.video_id,
                    "video_url": media_result.video_url,
                    "audio_size_bytes": len(media_result.audio_data),
                },
            )
            result.steps.append(step_result)

            video_url_preview = media_result.video_url[:50] if media_result.video_url else "N/A"
            logger.info(f"Step 4 complete: Video generated, URL={video_url_preview}...")

        except (TTSError, VideoGenerationError, MediaGenerationError) as e:
            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.FAILED,
                error=str(e),
            )
            result.steps.append(step_result)
            raise

        return result

    async def _execute_upload_video(
        self,
        result: WorkflowResult,
        source_url: str,
        keep_local_file: bool,
        update_callback: Optional[Callable[[str], Any]],
    ) -> WorkflowResult:
        """Execute Step 5: Upload video to YouTube."""
        step = WorkflowStep.UPLOAD_VIDEO

        if update_callback:
            await update_callback("Step 5/5: Uploading to YouTube...")

        script = result.script
        media_result = result.media_result
        link_info = result.link_info

        if script is None:
            raise RedditFlowError("Cannot upload: script is None")
        if media_result is None or media_result.video_url is None:
            raise RedditFlowError("Cannot upload: media_result or video_url is None")
        if link_info is None:
            raise RedditFlowError("Cannot upload: link_info is None")

        logger.debug("Step 5: Uploading video to YouTube")

        try:
            # Add source URL to description
            additional_description = f"\n\nSource: {source_url}"

            upload_result = self.upload_service.upload_from_url_with_script(
                video_url=media_result.video_url,
                script=script,
                additional_description=additional_description,
                tags=["#Shorts", "Reddit", link_info.subreddit],
                keep_local_file=keep_local_file,
            )
            result.upload_result = upload_result

            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.COMPLETED,
                data={
                    "video_id": upload_result.video_id,
                    "title": upload_result.title,
                    "url": upload_result.url,
                },
            )
            result.steps.append(step_result)

            logger.info(f"Step 5 complete: Uploaded to YouTube - {upload_result.url}")

        except YouTubeUploadError as e:
            step_result = self._create_step_result(
                step=step,
                status=WorkflowStatus.FAILED,
                error=str(e),
            )
            result.steps.append(step_result)
            raise

        return result

    async def process_with_link_info(
        self,
        link_info: LinkInfo,
        user_opinion: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        keep_local_file: bool = False,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> WorkflowResult:
        """
        Execute workflow starting from parsed LinkInfo.

        Use this method when you already have parsed URL information.

        Args:
            link_info: Pre-parsed Reddit link information.
            user_opinion: Optional user commentary to include.
            avatar_id: Optional HeyGen avatar ID override.
            test_mode: Use HeyGen test mode (watermarked).
            keep_local_file: Keep downloaded video after upload.
            update_callback: Optional async callback for progress updates.
            timeout: Override video generation timeout.

        Returns:
            WorkflowResult with all outputs and status.
        """
        workflow_id = self._generate_workflow_id()
        result = WorkflowResult(workflow_id=workflow_id)
        result.status = WorkflowStatus.IN_PROGRESS
        result.link_info = link_info

        # Add completed parse step
        result.steps.append(
            self._create_step_result(
                step=WorkflowStep.PARSE_URL,
                status=WorkflowStatus.COMPLETED,
                data={
                    "subreddit": link_info.subreddit,
                    "post_id": link_info.post_id,
                },
            )
        )

        logger.info(
            f"Starting workflow {workflow_id} from LinkInfo: "
            f"r/{link_info.subreddit}/{link_info.post_id}"
        )

        try:
            # Steps 2-5 (skip URL parsing)
            result = await self._execute_fetch_content(result, update_callback)
            result = await self._execute_generate_script(result, user_opinion, update_callback)
            result = await self._execute_generate_media(
                result, avatar_id, test_mode, update_callback, timeout
            )
            result = await self._execute_upload_video(
                result, link_info.link, keep_local_file, update_callback
            )

            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now()

            logger.info(f"Workflow {workflow_id} completed: {result.youtube_url}")

            if update_callback:
                await update_callback(f"✅ Complete! {result.youtube_url}")

        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

            logger.error(f"Workflow {workflow_id} failed: {e}")

            if update_callback:
                await update_callback(f"❌ Failed: {e}")

            raise

        return result

    async def generate_script_only(
        self,
        url: str,
        user_opinion: Optional[str] = None,
        update_callback: Optional[Callable[[str], Any]] = None,
    ) -> WorkflowResult:
        """
        Execute partial workflow: URL → Script only.

        Useful for previewing scripts before committing to video generation.

        Args:
            url: Reddit post URL.
            user_opinion: Optional user commentary.
            update_callback: Optional progress callback.

        Returns:
            WorkflowResult with post and script (no media/upload).
        """
        workflow_id = self._generate_workflow_id()
        result = WorkflowResult(workflow_id=workflow_id)
        result.status = WorkflowStatus.IN_PROGRESS

        logger.info(f"Starting script-only workflow {workflow_id}")

        try:
            result = await self._execute_parse_url(result, url, update_callback)
            result = await self._execute_fetch_content(result, update_callback)
            result = await self._execute_generate_script(result, user_opinion, update_callback)

            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now()

            script_title = result.script.title if result.script else "Unknown"
            logger.info(
                f"Script-only workflow {workflow_id} complete: " f"'{script_title[:30]}...'"
            )

            if update_callback and result.script:
                await update_callback(f"✅ Script generated: {result.script.title}")

        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

            logger.error(f"Script-only workflow {workflow_id} failed: {e}")

            if update_callback:
                await update_callback(f"❌ Failed: {e}")

            raise

        return result

    def verify_services(self) -> Dict[str, bool]:
        """
        Verify all services are accessible.

        Performs a basic check to ensure all service dependencies
        are properly configured.

        Returns:
            Dictionary with service names and verification status.
        """
        results = {}

        try:
            # Check ContentService has Reddit client
            _ = self.content_service.reddit_client
            results["content_service"] = True
        except Exception as e:
            logger.warning(f"ContentService verification failed: {e}")
            results["content_service"] = False

        try:
            # Check ScriptService has Gemini client
            _ = self.script_service.gemini_client
            results["script_service"] = True
        except Exception as e:
            logger.warning(f"ScriptService verification failed: {e}")
            results["script_service"] = False

        try:
            # Check MediaService has ElevenLabs and HeyGen clients
            _ = self.media_service.elevenlabs_client
            _ = self.media_service.heygen_client
            results["media_service"] = True
        except Exception as e:
            logger.warning(f"MediaService verification failed: {e}")
            results["media_service"] = False

        try:
            # Check UploadService has YouTube client
            _ = self.upload_service.youtube_client
            results["upload_service"] = True
        except Exception as e:
            logger.warning(f"UploadService verification failed: {e}")
            results["upload_service"] = False

        all_ok = all(results.values())
        logger.info(
            f"Service verification: {'all passed' if all_ok else 'some failed'} - " f"{results}"
        )

        return results
