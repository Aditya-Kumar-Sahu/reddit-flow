"""Built-in source adapters for the generic pipeline."""

from reddit_flow.clients.medium_client import MediumClient
from reddit_flow.models import LinkInfo, RedditPost
from reddit_flow.models.pipeline import ContentItem, PipelineRequest
from reddit_flow.pipeline.contracts import SourceAdapter
from reddit_flow.services.content_service import ContentService


class RedditSourceAdapter(SourceAdapter):
    """Canonical adapter for the existing Reddit content pipeline."""

    source_name = "reddit"

    def __init__(self, content_service: ContentService) -> None:
        self._content_service = content_service

    def supports(self, request: PipelineRequest) -> bool:
        """Support explicit Reddit requests or Reddit URLs."""
        if request.source_type and request.source_type != "reddit":
            return False
        url = request.source_url.lower()
        return "reddit.com/" in url or "redd.it/" in url

    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        """Fetch canonical content while preserving legacy Reddit models."""
        link_info: LinkInfo = self._content_service.parse_reddit_url(request.source_url)
        post: RedditPost = self._content_service.get_post_content(
            subreddit=link_info.subreddit,
            post_id=link_info.post_id,
        )

        comments = [
            {
                "id": comment.id,
                "author": comment.author,
                "body": comment.body,
                "score": comment.score,
                "depth": comment.depth,
            }
            for comment in post.comments
        ]

        return ContentItem(
            source_type="reddit",
            source_id=post.id,
            source_url=post.url,
            title=post.title,
            body=post.selftext,
            author=post.author,
            summary=post.title,
            partial=False,
            metadata={
                "subreddit": post.subreddit,
                "score": post.score,
                "comments_count": len(post.comments),
                "link_info": link_info,
                "legacy_post": post,
            },
            comments=comments,
        )


class MediumFeedSourceAdapter(SourceAdapter):
    """Canonical adapter for Medium feeds and feed-like profile URLs."""

    source_name = "medium_feed"

    def __init__(self, medium_client: MediumClient) -> None:
        self._medium_client = medium_client

    def supports(self, request: PipelineRequest) -> bool:
        """Support explicit feed requests and feed-like Medium URLs."""
        url = request.source_url.lower()
        if request.source_type == "medium_feed":
            return True
        if "medium.com" not in url:
            return False
        return "/feed/" in url or self._looks_like_feed_source(url)

    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        """Fetch the latest article from a Medium feed source."""
        content = self._medium_client.fetch_latest_feed_article(request.source_url)
        content.metadata["feed_source"] = True
        return content

    def _looks_like_feed_source(self, url: str) -> bool:
        """Infer whether a Medium URL represents a feed source rather than an article."""
        normalized = self._medium_client.normalize_url(url)
        path = normalized.replace("https://medium.com", "")
        if not path or path == "/":
            return False
        if path.startswith("/tag/") or path.startswith("/topic/"):
            return True
        parts = [part for part in path.split("/") if part]
        return len(parts) == 1


class MediumArticleSourceAdapter(SourceAdapter):
    """Canonical adapter for individual Medium articles."""

    source_name = "medium_article"

    def __init__(self, medium_client: MediumClient) -> None:
        self._medium_client = medium_client

    def supports(self, request: PipelineRequest) -> bool:
        """Support explicit article requests and non-feed Medium article URLs."""
        url = request.source_url.lower()
        if request.source_type == "medium_article":
            return True
        if "medium.com" not in url:
            return False
        return "/feed/" not in url

    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        """Fetch a Medium article and map it into canonical content."""
        return self._medium_client.fetch_article_content(request.source_url)
