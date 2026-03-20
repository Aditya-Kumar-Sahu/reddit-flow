"""
Instagram export bundle generation.

This service always creates a publishable bundle for Instagram Reels even when
direct publishing is disabled.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from reddit_flow.config import Settings, get_logger
from reddit_flow.models import VideoScript

logger = get_logger(__name__)


@dataclass
class InstagramExportBundle:
    """Files generated for an Instagram reel export."""

    bundle_dir: Path
    video_path: Path
    caption_path: Path
    hashtags_path: Path
    manifest_path: Path


class InstagramExportBundleService:
    """Build Instagram-ready asset bundles."""

    def __init__(
        self, output_dir: Optional[Path] = None, settings: Optional[Settings] = None
    ) -> None:
        self.settings = settings or Settings()
        self.output_dir = Path(output_dir or self.settings.temp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_bundle(
        self,
        media_source: str,
        script: VideoScript,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstagramExportBundle:
        """Create an Instagram reel bundle from a local file path or URL."""
        metadata = metadata or {}
        bundle_dir = Path(tempfile.mkdtemp(prefix="instagram_", dir=self.output_dir))
        video_path = bundle_dir / "reel.mp4"
        caption_path = bundle_dir / "caption.txt"
        hashtags_path = bundle_dir / "hashtags.txt"
        manifest_path = bundle_dir / "manifest.json"

        self._materialize_video(media_source, video_path)
        caption = self._build_caption(script, metadata)
        hashtags = self._build_hashtags(script, metadata)

        caption_path.write_text(caption, encoding="utf-8")
        hashtags_path.write_text(hashtags, encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "destination": "instagram",
                    "source_video": str(video_path),
                    "caption_file": str(caption_path),
                    "hashtags_file": str(hashtags_path),
                    "title": script.title,
                    "source_post_id": script.source_post_id,
                    "source_subreddit": script.source_subreddit,
                    "metadata": metadata,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return InstagramExportBundle(
            bundle_dir=bundle_dir,
            video_path=video_path,
            caption_path=caption_path,
            hashtags_path=hashtags_path,
            manifest_path=manifest_path,
        )

    def _materialize_video(self, media_source: str, destination: Path) -> None:
        """Copy or download the media source into the bundle."""
        parsed = urlparse(media_source)
        if parsed.scheme in {"http", "https"}:
            response = requests.get(media_source, stream=True, timeout=300)
            response.raise_for_status()
            with destination.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_handle.write(chunk)
            return

        source_path = Path(media_source)
        if not source_path.exists():
            raise FileNotFoundError(f"Media source not found: {media_source}")
        shutil.copyfile(source_path, destination)

    def _build_caption(self, script: VideoScript, metadata: Dict[str, Any]) -> str:
        """Build a short Instagram caption."""
        parts = [script.title.strip()]
        if script.user_opinion:
            parts.append(script.user_opinion.strip()[:180])
        if metadata.get("caption"):
            parts.append(str(metadata["caption"]).strip())
        if script.source_subreddit:
            parts.append(f"Source: r/{script.source_subreddit}")
        return "\n\n".join(part for part in parts if part)

    def _build_hashtags(self, script: VideoScript, metadata: Dict[str, Any]) -> str:
        """Build a lightweight hashtag block."""
        tags = metadata.get("hashtags") or []
        normalized_tags = [self._normalize_tag(tag) for tag in tags if str(tag).strip()]
        if script.source_subreddit:
            normalized_tags.append(f"r{self._normalize_tag(script.source_subreddit)}")
        normalized_tags.append(self._normalize_tag(script.title))
        return " ".join(dict.fromkeys(tag for tag in normalized_tags if tag))

    def _normalize_tag(self, value: str) -> str:
        """Convert a value into a hashtag-safe token."""
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "", value).lower()
        if not cleaned:
            return ""
        return f"#{cleaned}"
