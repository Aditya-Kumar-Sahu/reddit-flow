"""Unit tests for Medium client parsing helpers."""

from reddit_flow.clients.medium_client import MediumClient
from reddit_flow.models import ContentCandidate, ContentItem


class TestMediumClientFeedHelpers:
    """Tests for Medium feed URL handling."""

    def test_build_feed_url_for_profile(self):
        """Profile URLs should map to their RSS feed URL."""
        client = MediumClient()

        result = client.build_feed_url("https://medium.com/@writer")

        assert result == "https://medium.com/feed/@writer"

    def test_build_feed_url_for_publication(self):
        """Publication URLs should map to their RSS feed URL."""
        client = MediumClient()

        result = client.build_feed_url("https://medium.com/towards-data-science")

        assert result == "https://medium.com/feed/towards-data-science"

    def test_parse_feed_returns_candidates(self):
        """RSS items should be parsed into canonical content candidates."""
        client = MediumClient()
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <title>Medium Feed</title>
            <item>
              <title>First Story</title>
              <link>https://medium.com/@writer/first-story-abc123</link>
              <guid>first-story-abc123</guid>
              <description><![CDATA[<p>Short summary.</p>]]></description>
              <dc:creator>Writer One</dc:creator>
            </item>
            <item>
              <title>Second Story</title>
              <link>https://medium.com/@writer/second-story-def456</link>
              <guid>second-story-def456</guid>
              <description><![CDATA[<p>Another summary.</p>]]></description>
              <dc:creator>Writer Two</dc:creator>
            </item>
          </channel>
        </rss>"""

        result = client.parse_feed(xml_text)

        assert len(result) == 2
        assert all(isinstance(item, ContentCandidate) for item in result)
        assert result[0].title == "First Story"
        assert result[0].summary == "Short summary."
        assert result[0].author == "Writer One"


class TestMediumClientArticleParsing:
    """Tests for Medium article extraction."""

    def test_parse_article_html_returns_content_item(self):
        """HTML article parsing should produce a canonical content item."""
        client = MediumClient()
        html_text = """
        <html>
          <head>
            <meta property="og:title" content="A Medium Story" />
            <meta name="author" content="Medium Author" />
            <meta name="description" content="A concise article summary." />
          </head>
          <body>
            <article>
              <p>Paragraph one.</p>
              <p>Paragraph two.</p>
            </article>
          </body>
        </html>
        """

        result = client.parse_article_html(
            "https://medium.com/@writer/a-medium-story-123456",
            html_text,
        )

        assert isinstance(result, ContentItem)
        assert result.source_type == "medium_article"
        assert result.title == "A Medium Story"
        assert result.author == "Medium Author"
        assert result.summary == "A concise article summary."
        assert result.body == "Paragraph one.\n\nParagraph two."
