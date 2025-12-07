"""
Unit tests for NewsNexus MCP Server.
Run with: pytest tests/test_main.py -v
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    validate_domain,
    validate_url,
    validate_last_n_days,
    sanitize_string,
    sanitize_for_filter,
    parse_date,
    normalize_url,
    filter_articles,
    parse_rss_feed,
    parse_html_scraper,
    get_health,
    handle_request,
    RateLimiter,
    SimpleCache,
    Metrics,
)


class TestValidateDomain:
    """Tests for domain validation."""
    
    def test_valid_domains(self):
        assert validate_domain("example.com")[0] is True
        assert validate_domain("sub.example.com")[0] is True
        assert validate_domain("techcrunch.com")[0] is True
        assert validate_domain("bbc.co.uk")[0] is True
        assert validate_domain("news.ycombinator.com")[0] is True
    
    def test_invalid_domains(self):
        assert validate_domain("")[0] is False
        assert validate_domain(None)[0] is False
        assert validate_domain(123)[0] is False
        assert validate_domain("not a domain")[0] is False
        assert validate_domain("http://example.com")[0] is False
        assert validate_domain("-invalid.com")[0] is False
        assert validate_domain("a" * 300 + ".com")[0] is False


class TestValidateUrl:
    """Tests for URL validation."""
    
    def test_valid_urls(self):
        assert validate_url("https://example.com")[0] is True
        assert validate_url("http://example.com/path")[0] is True
        assert validate_url("https://sub.example.com/path?query=1")[0] is True
    
    def test_invalid_urls(self):
        assert validate_url("")[0] is False
        assert validate_url("file:///etc/passwd")[0] is False
        assert validate_url("javascript:alert(1)")[0] is False
        assert validate_url("http://localhost/")[0] is False
        assert validate_url("http://127.0.0.1/")[0] is False
        assert validate_url("http://192.168.1.1/")[0] is False
        assert validate_url("ftp://example.com")[0] is False


class TestValidateLastNDays:
    """Tests for lastNDays validation."""
    
    def test_valid_values(self):
        assert validate_last_n_days(1)[0] == 1
        assert validate_last_n_days(7)[0] == 7
        assert validate_last_n_days(30)[0] == 30
        assert validate_last_n_days(365)[0] == 365
        assert validate_last_n_days("7")[0] == 7
    
    def test_invalid_values(self):
        assert validate_last_n_days(0)[0] is None
        assert validate_last_n_days(-1)[0] is None
        assert validate_last_n_days(366)[0] is None
        assert validate_last_n_days("abc")[0] is None
        assert validate_last_n_days(None)[0] is None


class TestSanitizeString:
    """Tests for string sanitization."""
    
    def test_basic_sanitization(self):
        assert sanitize_string("Hello World") == "Hello World"
        assert sanitize_string("  spaced  ") == "spaced"
        assert sanitize_string(None) == ""
        assert sanitize_string(123) == "123"
    
    def test_html_encoding(self):
        assert "&lt;" in sanitize_string("<script>")
        assert "&gt;" in sanitize_string("</script>")
        assert "&amp;" in sanitize_string("a&b")
    
    def test_control_characters(self):
        assert sanitize_string("hello\x00world") == "helloworld"
        assert sanitize_string("line\x0bbreak") == "linebreak"
    
    def test_length_limit(self):
        long_string = "a" * 1000
        assert len(sanitize_string(long_string, max_length=100)) == 100


class TestSanitizeForFilter:
    """Tests for filter sanitization."""
    
    def test_lowercase(self):
        assert sanitize_for_filter("HELLO") == "hello"
        assert sanitize_for_filter("MiXeD") == "mixed"
    
    def test_preserves_special_chars(self):
        # Filter sanitization is more permissive
        result = sanitize_for_filter("AI & ML")
        assert "ai" in result
        assert "ml" in result


class TestParseDate:
    """Tests for date parsing."""
    
    def test_iso_format(self):
        result = parse_date("2024-12-05T10:30:00Z")
        assert result is not None
        assert "2024-12-05" in result
    
    def test_various_formats(self):
        assert parse_date("2024-12-05") is not None
        assert parse_date("05 Dec 2024") is not None
        assert parse_date("December 5, 2024") is not None
        assert parse_date("05/12/2024") is not None
    
    def test_invalid_dates(self):
        assert parse_date("") is None
        assert parse_date("not a date") is None
        assert parse_date("99/99/9999") is None


class TestNormalizeUrl:
    """Tests for URL normalization."""
    
    def test_absolute_urls(self):
        assert normalize_url("https://example.com/path", "example.com", "https://example.com") == "https://example.com/path"
    
    def test_relative_urls(self):
        result = normalize_url("/path/to/article", "example.com", "https://example.com")
        assert result == "https://example.com/path/to/article"
    
    def test_protocol_relative(self):
        result = normalize_url("//cdn.example.com/image.jpg", "example.com", "https://example.com")
        assert result == "https://cdn.example.com/image.jpg"
    
    def test_invalid_urls(self):
        assert normalize_url("#anchor", "example.com", "https://example.com") is None
        assert normalize_url("javascript:void(0)", "example.com", "https://example.com") is None
        assert normalize_url("", "example.com", "https://example.com") is None


class TestFilterArticles:
    """Tests for article filtering."""
    
    @pytest.fixture
    def sample_articles(self):
        now = datetime.now(timezone.utc)
        return [
            {
                "title": "AI advances in technology",
                "url": "https://example.com/ai-article",
                "published_at": now.isoformat(),
                "summary": "Latest AI developments",
                "tags": ["AI", "tech"]
            },
            {
                "title": "Sports news from London",
                "url": "https://example.com/sports",
                "published_at": (now - timedelta(days=5)).isoformat(),
                "summary": "Football updates",
                "tags": ["sports"]
            },
            {
                "title": "Old news article",
                "url": "https://example.com/old",
                "published_at": (now - timedelta(days=30)).isoformat(),
                "summary": "Ancient history",
                "tags": []
            },
            {
                "title": "AI advances in technology",  # Duplicate title
                "url": "https://example.com/ai-duplicate",
                "published_at": now.isoformat(),
                "summary": "Duplicate article",
                "tags": []
            }
        ]
    
    def test_no_filters(self, sample_articles):
        result = filter_articles(sample_articles, None, None, None)
        # Should deduplicate by title
        assert len(result) == 3
    
    def test_topic_filter(self, sample_articles):
        result = filter_articles(sample_articles, "AI", None, None)
        assert len(result) >= 1
        assert all("ai" in a['title'].lower() or "ai" in a['summary'].lower() for a in result)
    
    def test_location_filter(self, sample_articles):
        result = filter_articles(sample_articles, None, "London", None)
        assert len(result) == 1
        assert "London" in result[0]['title']
    
    def test_date_filter(self, sample_articles):
        result = filter_articles(sample_articles, None, None, 7)
        # Should exclude article older than 7 days
        assert all("old" not in a['title'].lower() for a in result)
    
    def test_combined_filters(self, sample_articles):
        result = filter_articles(sample_articles, "AI", None, 7)
        assert len(result) >= 1
        assert all("ai" in a['title'].lower() for a in result)


class TestRateLimiter:
    """Tests for rate limiting."""
    
    def test_allows_within_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for i in range(5):
            assert limiter.is_allowed("test-domain") is True
    
    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("test-domain") is True
        assert limiter.is_allowed("test-domain") is True
        assert limiter.is_allowed("test-domain") is False
    
    def test_separate_domains(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("domain1") is True
        assert limiter.is_allowed("domain2") is True
        assert limiter.is_allowed("domain1") is False


class TestSimpleCache:
    """Tests for caching."""
    
    def test_set_and_get(self):
        c = SimpleCache(ttl_seconds=300)
        c.set("example.com", {"articles": []})
        result = c.get("example.com")
        assert result is not None
        assert "articles" in result
    
    def test_cache_miss(self):
        c = SimpleCache(ttl_seconds=300)
        result = c.get("nonexistent.com")
        assert result is None
    
    def test_with_filters(self):
        c = SimpleCache(ttl_seconds=300)
        c.set("example.com", {"topic": "AI"}, topic="AI")
        
        # Same filter should hit
        assert c.get("example.com", topic="AI") is not None
        # Different filter should miss
        assert c.get("example.com", topic="sports") is None
    
    def test_clear(self):
        c = SimpleCache(ttl_seconds=300)
        c.set("example.com", {"articles": []})
        c.clear()
        assert c.get("example.com") is None


class TestMetrics:
    """Tests for metrics collection."""
    
    def test_increment(self):
        m = Metrics()
        m.increment("test_counter")
        m.increment("test_counter")
        stats = m.get_stats()
        assert stats['counters']['test_counter'] == 2
    
    def test_duration_recording(self):
        m = Metrics()
        m.record_duration("test_duration", 100.5)
        m.record_duration("test_duration", 200.5)
        stats = m.get_stats()
        assert 'test_duration' in stats['histograms']
        assert stats['histograms']['test_duration']['count'] == 2


class TestMCPProtocol:
    """Tests for MCP protocol handling."""
    
    def test_initialize(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = handle_request(request)
        
        assert response['jsonrpc'] == "2.0"
        assert response['id'] == 1
        assert 'result' in response
        assert response['result']['protocolVersion'] == "2024-11-05"
    
    def test_tools_list(self):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = handle_request(request)
        
        assert 'result' in response
        assert 'tools' in response['result']
        
        tool_names = [t['name'] for t in response['result']['tools']]
        assert 'get_articles' in tool_names
        assert 'health_check' in tool_names
        assert 'get_metrics' in tool_names
    
    def test_unknown_method(self):
        request = {"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}}
        response = handle_request(request)
        
        assert 'error' in response
        assert response['error']['code'] == -32601
    
    def test_health_check(self):
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}}
        }
        response = handle_request(request)
        
        assert 'result' in response
        content = json.loads(response['result']['content'][0]['text'])
        assert content['status'] == 'healthy'


class TestGetHealth:
    """Tests for health check endpoint."""
    
    def test_health_structure(self):
        health = get_health()
        
        assert 'status' in health
        assert 'version' in health
        assert 'configuredDomains' in health
        assert 'timestamp' in health
        assert health['status'] == 'healthy'


class TestRSSParsing:
    """Tests for RSS feed parsing."""
    
    def test_parse_valid_rss(self):
        rss_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                    <pubDate>Thu, 05 Dec 2024 10:00:00 GMT</pubDate>
                    <description>Test summary</description>
                </item>
            </channel>
        </rss>
        """
        
        articles = parse_rss_feed(rss_content, "example.com")
        
        assert len(articles) == 1
        assert articles[0]['title'] == "Test Article"
        assert articles[0]['url'] == "https://example.com/article1"
        assert articles[0]['source_domain'] == "example.com"
    
    def test_parse_empty_rss(self):
        rss_content = b"""<?xml version="1.0"?><rss><channel></channel></rss>"""
        articles = parse_rss_feed(rss_content, "example.com")
        assert articles == []


class TestHTMLScraping:
    """Tests for HTML scraping."""
    
    def test_parse_article_elements(self):
        html_content = b"""
        <html>
            <body>
                <article class="post">
                    <h2><a href="/article1">Article Title</a></h2>
                    <time datetime="2024-12-05T10:00:00Z">Dec 5, 2024</time>
                    <p>This is the summary.</p>
                </article>
            </body>
        </html>
        """
        
        articles = parse_html_scraper(html_content, "example.com", "https://example.com")
        
        assert len(articles) >= 1
        assert "Article Title" in articles[0]['title']
    
    def test_parse_headline_links(self):
        html_content = b"""
        <html>
            <body>
                <h2><a href="/news/story1">Breaking News Story</a></h2>
                <h3><a href="/news/story2">Another Story</a></h3>
            </body>
        </html>
        """
        
        articles = parse_html_scraper(html_content, "example.com", "https://example.com")
        
        assert len(articles) >= 1


# Integration tests
class TestIntegration:
    """Integration tests with mocked HTTP."""
    
    @patch('main.fetch_with_retry')
    @patch('main.config', [{"domain": "test.com", "sources": [
        {"type": "official_rss", "url": "https://test.com/feed", "priority": 1, "timeout_ms": 1000}
    ]}])
    def test_get_articles_with_mock(self, mock_fetch):
        from main import get_articles
        
        # Mock response
        mock_response = Mock()
        mock_response.content = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Test Article</title>
                    <link>https://test.com/article</link>
                    <description>Test description</description>
                </item>
            </channel>
        </rss>
        """
        mock_fetch.return_value = mock_response
        
        result = get_articles("test.com")
        
        assert 'articles' in result
        assert result['sourceUsed'] != 'none'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
