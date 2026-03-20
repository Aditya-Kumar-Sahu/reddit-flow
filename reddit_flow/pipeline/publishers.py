"""Built-in publisher adapters for the generic pipeline."""

from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models.pipeline import PublishRequest, PublishResult
from reddit_flow.pipeline.contracts import Publisher
from reddit_flow.services.upload_service import UploadService


class YouTubePublisher(Publisher):
    """Publisher adapter for the existing YouTube upload flow."""

    destination_name = "youtube"

    def __init__(self, upload_service: UploadService) -> None:
        self._upload_service = upload_service

    def publish(self, request: PublishRequest) -> PublishResult:
        """Publish rendered media to YouTube using the existing upload service."""
        if not request.media_url:
            raise YouTubeUploadError("Cannot publish to YouTube without a media URL")

        tags = request.metadata.get("tags")
        privacy_status = request.metadata.get("privacy_status")

        upload_result = self._upload_service.upload_from_url_with_script(
            video_url=request.media_url,
            script=request.script,
            additional_description=request.additional_description,
            tags=tags,
            privacy_status=privacy_status,
            keep_local_file=request.keep_local_file,
        )

        return PublishResult(
            destination=self.destination_name,
            external_id=upload_result.video_id,
            title=upload_result.title,
            url=upload_result.url,
            metadata={
                "studio_url": upload_result.studio_url,
                "local_file_path": upload_result.local_file_path,
            },
        )
