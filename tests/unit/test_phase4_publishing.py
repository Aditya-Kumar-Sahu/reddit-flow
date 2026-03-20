"""Phase 4 tests for publishing adapters and Instagram export bundles."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from reddit_flow.models import ContentItem, PublishRequest, VideoScript
from reddit_flow.pipeline.publishers import InstagramPublisher, YouTubePublisher
from reddit_flow.services.instagram_export_service import InstagramExportBundleService
from reddit_flow.services.upload_service import UploadResult


@pytest.fixture
def sample_content_item():
    return ContentItem(
        source_type="reddit",
        source_id="abc123",
        source_url="https://reddit.com/r/python/comments/abc123/test",
        title="A Reddit Story",
        body="Body text for the story.",
    )


@pytest.fixture
def sample_video_script():
    return VideoScript(
        script="Hello world! This is a short script that is still long enough.",
        title="A Video Title",
        source_post_id="abc123",
        source_subreddit="python",
        user_opinion="Interesting post",
    )


class TestPublishModels:
    """Canonical publish request/result basics."""

    def test_publish_request_normalizes_destination_and_export_flag(self, sample_content_item):
        request = PublishRequest(
            destination="Instagram",
            media_url="https://example.com/video.mp4",
            script=VideoScript(script="script text", title="Title"),
            content_item=sample_content_item,
            export_only=True,
        )

        assert request.destination == "instagram"
        assert request.export_only is True


class TestYouTubePublisher:
    """YouTube wrapper should remain a thin adapter over UploadService."""

    def test_publish_delegates_to_upload_service(self, sample_content_item, sample_video_script):
        mock_upload_service = MagicMock()
        mock_upload_service.upload_from_url_with_script.return_value = UploadResult(
            video_id="yt_123",
            title="A Video Title",
            url="https://youtube.com/watch?v=yt_123",
            studio_url="https://studio.youtube.com/video/yt_123/edit",
        )
        publisher = YouTubePublisher(mock_upload_service)

        result = publisher.publish(
            PublishRequest(
                destination="youtube",
                media_url="https://example.com/video.mp4",
                script=sample_video_script,
                content_item=sample_content_item,
                additional_description="Extra context",
                metadata={"tags": ["reddit", "python"], "privacy_status": "unlisted"},
            )
        )

        assert result.destination == "youtube"
        assert result.url == "https://youtube.com/watch?v=yt_123"
        mock_upload_service.upload_from_url_with_script.assert_called_once()


class TestInstagramExportBundleService:
    """Instagram export bundles should always be created."""

    def test_create_bundle_writes_required_artifacts(self, tmp_path, sample_video_script):
        media_file = tmp_path / "source.mp4"
        media_file.write_bytes(b"video-bytes")
        service = InstagramExportBundleService(output_dir=tmp_path)

        bundle = service.create_bundle(
            media_source=str(media_file),
            script=sample_video_script,
            metadata={"hashtags": ["python", "reddit"]},
        )

        assert bundle.video_path.exists()
        assert bundle.caption_path.exists()
        assert bundle.hashtags_path.exists()
        assert bundle.manifest_path.exists()

        manifest = json.loads(bundle.manifest_path.read_text())
        assert manifest["destination"] == "instagram"
        assert manifest["source_video"].endswith("reel.mp4")
        assert "python" in bundle.hashtags_path.read_text()


class TestInstagramPublisher:
    """Instagram publisher should support export-only and direct publish flows."""

    def test_publish_export_only_returns_bundle_metadata(
        self, tmp_path, sample_content_item, sample_video_script
    ):
        media_file = tmp_path / "source.mp4"
        media_file.write_bytes(b"video-bytes")
        export_service = InstagramExportBundleService(output_dir=tmp_path)
        mock_client = MagicMock()
        settings = SimpleNamespace(env="prod", enable_instagram_publish=False)
        publisher = InstagramPublisher(
            instagram_client=mock_client,
            export_service=export_service,
            settings=settings,
        )

        result = publisher.publish(
            PublishRequest(
                destination="instagram",
                media_url=str(media_file),
                script=sample_video_script,
                content_item=sample_content_item,
                export_only=True,
            )
        )

        assert result.destination == "instagram"
        assert result.external_id is None
        assert "export_bundle" in result.metadata
        mock_client.publish_reel.assert_not_called()

    def test_publish_direct_uses_client_when_enabled(
        self, tmp_path, sample_content_item, sample_video_script
    ):
        media_file = tmp_path / "source.mp4"
        media_file.write_bytes(b"video-bytes")
        export_service = InstagramExportBundleService(output_dir=tmp_path)
        mock_client = MagicMock()
        mock_client.create_media_container.return_value = "container_123"
        mock_client.publish_media_container.return_value = "ig_123"
        settings = SimpleNamespace(env="prod", enable_instagram_publish=True)
        publisher = InstagramPublisher(
            instagram_client=mock_client,
            export_service=export_service,
            settings=settings,
        )

        result = publisher.publish(
            PublishRequest(
                destination="instagram",
                media_url=str(media_file),
                script=sample_video_script,
                content_item=sample_content_item,
            )
        )

        assert result.external_id == "ig_123"
        assert result.url == "https://instagram.com/reel/ig_123"
        mock_client.create_media_container.assert_called_once()
        mock_client.publish_media_container.assert_called_once()
