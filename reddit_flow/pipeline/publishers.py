"""Built-in publisher adapters for the generic pipeline."""

from __future__ import annotations

from typing import Any, Optional

from reddit_flow.config import Settings
from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models.pipeline import PublishRequest, PublishResult
from reddit_flow.pipeline.contracts import Publisher
from reddit_flow.services.instagram_export_service import InstagramExportBundleService
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


class InstagramPublisher(Publisher):
    """Publisher adapter for Instagram exports and direct reel publish."""

    destination_name = "instagram"

    def __init__(
        self,
        instagram_client: Optional[Any] = None,
        export_service: Optional[InstagramExportBundleService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._instagram_client = instagram_client
        self.settings = settings or Settings()
        self._export_service = export_service or InstagramExportBundleService(
            settings=self.settings
        )

    def publish(self, request: PublishRequest) -> PublishResult:
        """Create an export bundle and optionally publish directly to Instagram."""
        if not request.media_url:
            raise ValueError("Cannot publish to Instagram without a media URL")

        bundle = self._export_service.create_bundle(
            media_source=request.media_url,
            script=request.script,
            metadata=request.metadata,
        )

        result_metadata = {
            "export_bundle": {
                "bundle_dir": str(bundle.bundle_dir),
                "video_path": str(bundle.video_path),
                "caption_path": str(bundle.caption_path),
                "hashtags_path": str(bundle.hashtags_path),
                "manifest_path": str(bundle.manifest_path),
            },
            "caption": bundle.caption_path.read_text(encoding="utf-8"),
            "hashtags": bundle.hashtags_path.read_text(encoding="utf-8"),
        }

        direct_publish_enabled = bool(getattr(self.settings, "enable_instagram_publish", False))
        if request.export_only or not direct_publish_enabled:
            return PublishResult(
                destination=self.destination_name,
                title=request.script.title,
                metadata=result_metadata,
            )

        client = self._instagram_client
        if client is None:
            raise ValueError("Instagram direct publishing requires a client")

        if hasattr(client, "create_media_container"):
            container_id = client.create_media_container(
                media_path=str(bundle.video_path),
                caption=result_metadata["caption"],
                hashtags=result_metadata["hashtags"],
                metadata=request.metadata,
            )
        elif hasattr(client, "publish_reel"):
            container_id = client.publish_reel(
                media_path=str(bundle.video_path),
                caption=result_metadata["caption"],
                hashtags=result_metadata["hashtags"],
                metadata=request.metadata,
            )
        else:
            raise ValueError("Instagram client does not support direct publishing")

        publish_id = container_id
        if hasattr(client, "publish_media_container"):
            publish_id = client.publish_media_container(container_id)
        elif hasattr(client, "publish_container"):
            publish_id = client.publish_container(container_id)

        url = f"https://instagram.com/reel/{publish_id}"
        permalink_builder = getattr(client, "build_permalink", None)
        if callable(permalink_builder):
            candidate_url = permalink_builder(publish_id)
            if isinstance(candidate_url, str) and candidate_url.strip():
                url = candidate_url

        return PublishResult(
            destination=self.destination_name,
            external_id=publish_id,
            title=request.script.title,
            url=url,
            metadata=result_metadata,
        )
