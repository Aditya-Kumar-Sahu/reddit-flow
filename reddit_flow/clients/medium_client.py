"""Medium content client for public article and RSS feed retrieval."""

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List, Optional
from urllib.parse import urlparse

import requests

from reddit_flow.clients.base import BaseClient, HTTPClientMixin
from reddit_flow.config import get_logger
from reddit_flow.exceptions import ContentError
from reddit_flow.models import ContentCandidate, ContentItem

logger = get_logger(__name__)


class MediumClient(BaseClient, HTTPClientMixin):
    """Client for Medium article pages and RSS feeds."""

    service_name = "Medium"
    base_url = "https://medium.com"
    default_timeout = 30

    def _initialize(self) -> None:
        """Initialize public Medium access settings."""
        self.default_headers = {
            "User-Agent": self._config.get("user_agent", "reddit-flow/0.1"),
        }
        self._timeout = int(self._config.get("timeout", self.default_timeout))

    def _health_check(self) -> bool:
        """Verify Medium is reachable."""
        try:
            response = requests.get(
                self.base_url,
                headers=self.default_headers,
                timeout=self._timeout,
            )
            return response.status_code == 200
        except Exception:
            return False

    def normalize_url(self, url: str) -> str:
        """Normalize Medium URLs for feed/article routing."""
        parsed = urlparse(url.strip())
        if not parsed.scheme:
            parsed = urlparse(f"https://{url.strip()}")
        netloc = parsed.netloc.lower() or "medium.com"
        path = parsed.path.rstrip("/")
        if not path:
            path = ""
        return f"https://{netloc}{path}"

    def build_feed_url(self, url: str) -> str:
        """Build a Medium RSS feed URL from a profile/publication/topic URL."""
        normalized = self.normalize_url(url)
        parsed = urlparse(normalized)
        path = parsed.path.rstrip("/")

        if path.startswith("/feed/"):
            return normalized
        if not path:
            raise ContentError(f"Cannot infer Medium feed URL from: {url}")

        return f"https://{parsed.netloc}/feed{path}"

    def parse_feed(self, xml_text: str) -> List[ContentCandidate]:
        """Parse RSS XML into canonical content candidates."""
        channel_match = re.search(r"<channel\b[^>]*>(.*?)</channel>", xml_text, flags=re.I | re.S)
        if channel_match is None:
            raise ContentError("Medium feed is missing channel data")

        candidates: List[ContentCandidate] = []
        for item_html in re.findall(
            r"<item\b[^>]*>(.*?)</item>", channel_match.group(1), flags=re.I | re.S
        ):
            title = self._extract_xml_text(item_html, "title") or ""
            link = self._extract_xml_text(item_html, "link") or ""
            guid = self._extract_xml_text(item_html, "guid") or link
            description = self._extract_xml_text(item_html, "description") or ""
            author = self._extract_xml_text(item_html, "dc:creator")
            published_at: Optional[datetime] = None

            pub_date = self._extract_xml_text(item_html, "pubDate")
            if pub_date:
                try:
                    published_at = parsedate_to_datetime(pub_date)
                except (TypeError, ValueError):
                    published_at = None

            candidates.append(
                ContentCandidate(
                    source_type="medium_feed",
                    candidate_id=guid,
                    url=self.normalize_url(link),
                    title=title,
                    summary=self._clean_html_text(self._strip_cdata(description)),
                    author=author,
                    published_at=published_at,
                )
            )

        return candidates

    def parse_article_html(self, url: str, html_text: str) -> ContentItem:
        """Parse Medium article HTML into a canonical content item."""
        normalized_url = self.normalize_url(url)
        title = self._extract_meta_content(
            html_text, "property", "og:title"
        ) or self._extract_title(html_text)
        author = self._extract_meta_content(html_text, "name", "author")
        summary = self._extract_meta_content(html_text, "name", "description")

        article_html = self._extract_article_html(html_text)
        paragraph_matches = re.findall(
            r"<p[^>]*>(.*?)</p>", article_html, flags=re.IGNORECASE | re.DOTALL
        )
        if not paragraph_matches:
            paragraph_matches = re.findall(
                r"<p[^>]*>(.*?)</p>", html_text, flags=re.IGNORECASE | re.DOTALL
            )

        body = "\n\n".join(
            paragraph
            for paragraph in (
                self._clean_html_text(paragraph_html) for paragraph_html in paragraph_matches
            )
            if paragraph
        )

        path = urlparse(normalized_url).path.rstrip("/")
        source_id = path.split("/")[-1] if path else normalized_url
        partial = not bool(body.strip())

        return ContentItem(
            source_type="medium_article",
            source_id=source_id,
            source_url=normalized_url,
            title=title or "Untitled Medium article",
            body=body,
            summary=summary,
            author=author,
            partial=partial,
            metadata={"feed_source": False},
        )

    def fetch_feed_candidates(self, url: str) -> List[ContentCandidate]:
        """Fetch and parse feed candidates from Medium."""
        feed_url = self.build_feed_url(url)
        response = requests.get(
            feed_url,
            headers=self.default_headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return self.parse_feed(response.text)

    def fetch_article_content(self, url: str) -> ContentItem:
        """Fetch and parse a Medium article."""
        normalized_url = self.normalize_url(url)
        response = requests.get(
            normalized_url,
            headers=self.default_headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return self.parse_article_html(normalized_url, response.text)

    def fetch_latest_feed_article(self, url: str) -> ContentItem:
        """Fetch the latest article from a Medium profile/publication/topic feed."""
        candidates = self.fetch_feed_candidates(url)
        if not candidates:
            raise ContentError(f"No Medium feed candidates found for: {url}")
        return self.fetch_article_content(candidates[0].url)

    def _extract_meta_content(
        self, html_text: str, attr_name: str, attr_value: str
    ) -> Optional[str]:
        """Extract content from a meta tag by attribute name/value."""
        pattern = (
            rf'<meta[^>]*{attr_name}=["\']{re.escape(attr_value)}["\']'
            rf'[^>]*content=["\'](.*?)["\'][^>]*>'
        )
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return unescape(match.group(1)).strip()
        return None

    def _extract_title(self, html_text: str) -> Optional[str]:
        """Extract title text from the HTML title tag."""
        match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return self._clean_html_text(match.group(1))

    def _extract_article_html(self, html_text: str) -> str:
        """Extract the article block when present."""
        match = re.search(
            r"<article[^>]*>(.*?)</article>", html_text, flags=re.IGNORECASE | re.DOTALL
        )
        if not match:
            return html_text
        return match.group(1)

    def _clean_html_text(self, html_text: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        text = re.sub(r"<[^>]+>", " ", html_text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_xml_text(self, xml_text: str, tag_name: str) -> Optional[str]:
        """Extract a simple XML element value from a constrained Medium feed."""
        pattern = rf"<{re.escape(tag_name)}\b[^>]*>(.*?)</{re.escape(tag_name)}>"
        match = re.search(pattern, xml_text, flags=re.I | re.S)
        if not match:
            return None
        return self._strip_cdata(match.group(1)).strip()

    def _strip_cdata(self, text: str) -> str:
        """Remove CDATA wrappers when present."""
        cleaned = text.strip()
        if cleaned.startswith("<![CDATA[") and cleaned.endswith("]]>"):
            cleaned = cleaned[9:-3]
        return cleaned
