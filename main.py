"""
NewsNexus MCP Server
A production-ready STDIO MCP server for 4-layer news aggregation.

Features:
- 4-layer fallback: Official RSS → RSSHub → Google News → Scraper
- Parallel fetching with concurrent.futures
- Rate limiting per domain
- Comprehensive input validation
- Structured logging with metrics
- Health monitoring
- Caching support
"""
import sys
import os
import io
import json
import logging
import re
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List, Tuple
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from collections import defaultdict
from functools import lru_cache
from collections import OrderedDict
import threading

# Fix Windows console encoding for Unicode output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import feedparser
import requests
from requests.exceptions import Timeout, RequestException, SSLError, ConnectionError as ReqConnectionError
from bs4 import BeautifulSoup

# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variables with defaults
LOG_LEVEL = os.environ.get('NEWSNEXUS_LOG_LEVEL', 'INFO')
MAX_ARTICLES_PER_REQUEST = int(os.environ.get('NEWSNEXUS_MAX_ARTICLES', '50'))
CACHE_TTL_SECONDS = int(os.environ.get('NEWSNEXUS_CACHE_TTL', '300'))
RATE_LIMIT_REQUESTS = int(os.environ.get('NEWSNEXUS_RATE_LIMIT', '10'))
RATE_LIMIT_WINDOW = int(os.environ.get('NEWSNEXUS_RATE_WINDOW', '60'))
PARALLEL_FETCH = os.environ.get('NEWSNEXUS_PARALLEL', 'true').lower() == 'true'

# Resolve config path relative to script location
CONFIG_PATH = os.environ.get(
    'NEWSNEXUS_CONFIG_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sites.json')
)

# Retry settings - OPTIMIZED: No retries for faster failure/fallback
MAX_RETRIES = 0  # No retries - fail fast and move to next source
RETRY_BACKOFF = 0.3

# Request settings - BALANCED: Allow 2.5s for slower feeds but still fast overall
DEFAULT_TIMEOUT_MS = 2500  # Increased from 1500ms - some feeds are slow but working
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Deep scraper settings
DEEP_SCRAPE_ENABLED = os.environ.get('NEWSNEXUS_DEEP_SCRAPE', 'true').lower() == 'true'
DEEP_SCRAPE_MAX_ARTICLES = int(os.environ.get('NEWSNEXUS_DEEP_SCRAPE_MAX', '10'))
DEEP_SCRAPE_TIMEOUT_MS = int(os.environ.get('NEWSNEXUS_DEEP_SCRAPE_TIMEOUT', '2000'))  # Reduced from 3000
DEEP_SCRAPE_SUMMARY_LENGTH = int(os.environ.get('NEWSNEXUS_SUMMARY_LENGTH', '500'))
DEEP_SCRAPE_PARALLEL_WORKERS = int(os.environ.get('NEWSNEXUS_DEEP_WORKERS', '5'))

# Recent news settings
MAX_RECENT_DAYS = 10  # Hard cap: Articles older than 10 days are not considered "recent"
DEFAULT_ARTICLE_COUNT = 8  # Default number of articles when user doesn't specify
MIN_ARTICLES_THRESHOLD = 3  # Reduced from 5 - faster to accept results and skip fallback

# =============================================================================
# LOGGING SETUP
# =============================================================================

class StructuredFormatter(logging.Formatter):
    """JSON-structured logging formatter for observability."""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, 'domain'):
            log_data['domain'] = record.domain
        if hasattr(record, 'source_type'):
            log_data['source_type'] = record.source_type
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'article_count'):
            log_data['article_count'] = record.article_count
        if hasattr(record, 'error_type'):
            log_data['error_type'] = record.error_type
            
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)


# Configure logging to STDERR with structured format
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(StructuredFormatter())
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    handlers=[handler]
)
logger = logging.getLogger('newsnexus')

# =============================================================================
# METRICS COLLECTION
# =============================================================================

class Metrics:
    """Thread-safe metrics collector for observability."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._start_time = datetime.now(timezone.utc)
    
    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value
    
    def record_duration(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._histograms[name].append(duration_ms)
            # Keep only last 1000 samples
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]
    
    def get_stats(self) -> Dict:
        with self._lock:
            stats = {
                'uptime_seconds': (datetime.now(timezone.utc) - self._start_time).total_seconds(),
                'counters': dict(self._counters),
                'histograms': {}
            }
            for name, values in self._histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    stats['histograms'][name] = {
                        'count': len(values),
                        'min': min(values),
                        'max': max(values),
                        'avg': sum(values) / len(values),
                        'p50': sorted_vals[len(sorted_vals) // 2],
                        'p95': sorted_vals[int(len(sorted_vals) * 0.95)] if len(sorted_vals) > 20 else sorted_vals[-1],
                        'p99': sorted_vals[int(len(sorted_vals) * 0.99)] if len(sorted_vals) > 100 else sorted_vals[-1],
                    }
            return stats


metrics = Metrics()

# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """Thread-safe rate limiter per domain."""
    
    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW):
        self._lock = threading.Lock()
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._max_requests = max_requests
        self._window = window_seconds
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed under rate limit."""
        now = time.time()
        
        with self._lock:
            # Clean old requests
            self._requests[key] = [t for t in self._requests[key] if now - t < self._window]
            
            if len(self._requests[key]) >= self._max_requests:
                return False
            
            self._requests[key].append(now)
            return True
    
    def get_retry_after(self, key: str) -> int:
        """Get seconds until next request is allowed."""
        now = time.time()
        
        with self._lock:
            if not self._requests[key]:
                return 0
            oldest = min(self._requests[key])
            return max(0, int(self._window - (now - oldest)))


rate_limiter = RateLimiter()

# =============================================================================
# CACHING
# =============================================================================

class SimpleCache:
    """Thread-safe in-memory cache with TTL and LRU eviction."""
    
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._lock = threading.Lock()
        self._cache = OrderedDict()
        self._ttl = ttl_seconds
    
    def _make_key(self, domain: str, topic: Optional[str], location: Optional[str], days: Optional[int]) -> str:
        key_parts = [domain, topic or '', location or '', str(days or '')]
        return hashlib.md5('|'.join(key_parts).encode()).hexdigest()
    
    def get(self, domain: str, topic: Optional[str] = None, 
            location: Optional[str] = None, days: Optional[int] = None) -> Optional[Dict]:
        key = self._make_key(domain, topic, location, days)
        
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    metrics.increment('cache_hits')
                    return value
                else:
                    del self._cache[key]
            metrics.increment('cache_misses')
            return None
    
    def set(self, domain: str, result: Dict, topic: Optional[str] = None,
            location: Optional[str] = None, days: Optional[int] = None) -> None:
        key = self._make_key(domain, topic, location, days)
        
        with self._lock:
            # If exists, update and move to end
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (result, time.time())
            
            # Evict oldest if cache is too large (O(1))
            if len(self._cache) > 1000:
                self._cache.popitem(last=False)
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def stats(self) -> Dict:
        with self._lock:
            return {
                'size': len(self._cache),
                'ttl_seconds': self._ttl
            }


cache = SimpleCache()

# =============================================================================
# CONFIGURATION LOADER
# =============================================================================

def load_config() -> List[Dict]:
    """Load site configuration from JSON file with validation."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate configuration
        if not isinstance(data, list):
            logger.error("Config must be a JSON array")
            return []
        
        validated = []
        for site in data:
            if not isinstance(site, dict):
                continue
            if 'domain' not in site or 'sources' not in site:
                logger.warning("Skipping invalid site config: missing domain or sources")
                continue
            if not isinstance(site['sources'], list):
                continue
            validated.append(site)
        
        logger.info("Loaded %d site configurations from %s", len(validated), CONFIG_PATH)
        return validated
        
    except FileNotFoundError:
        logger.error("Config file not found: %s", CONFIG_PATH)
        return []
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config file: %s", str(e))
        return []
    except PermissionError:
        logger.error("Permission denied reading config: %s", CONFIG_PATH)
        return []


config = load_config()

# Build O(1) domain lookup map
DOMAIN_MAP = {}
for site in config:
    d = site.get('domain', '').lower()
    if d:
        DOMAIN_MAP[d] = site
        # Handle www variations
        if d.startswith('www.'):
            DOMAIN_MAP[d[4:]] = site
        else:
            DOMAIN_MAP['www.' + d] = site

# =============================================================================
# INPUT VALIDATION
# =============================================================================

# Dangerous URL patterns to block
BLOCKED_URL_PATTERNS = [
    r'file://',
    r'javascript:',
    r'data:',
    r'vbscript:',
    r'localhost',
    r'127\.0\.0\.',
    r'0\.0\.0\.0',
    r'::1',
    r'169\.254\.',  # Link-local
    r'10\.\d+\.\d+\.\d+',  # Private
    r'172\.(1[6-9]|2\d|3[01])\.',  # Private
    r'192\.168\.',  # Private
]


def validate_domain(domain: str) -> Tuple[bool, str]:
    """Validate domain format with detailed error message. Supports partial domain names."""
    if not domain:
        return False, "Domain is required"
    
    if not isinstance(domain, str):
        return False, "Domain must be a string"
    
    if len(domain) > 253:
        return False, "Domain too long (max 253 characters)"
    
    # Relaxed domain validation - allows partial names like 'openai' or 'wired'
    # Also accepts full domains like 'openai.com' or 'www.openai.com'
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9-]+)*$'
    if not re.match(pattern, domain):
        return False, "Invalid domain format"
    
    return True, ""


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate URL for security issues."""
    if not url:
        return False, "URL is required"
    
    # Check for blocked patterns
    for pattern in BLOCKED_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return False, f"URL contains blocked pattern"
    
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False, "Only HTTP(S) URLs allowed"
        if not parsed.netloc:
            return False, "Invalid URL structure"
    except Exception:
        return False, "URL parsing failed"
    
    return True, ""


def validate_last_n_days(last_n_days: Any) -> Tuple[Optional[int], str]:
    """Validate and convert lastNDays parameter."""
    if last_n_days is None:
        return None, ""
    
    try:
        days = int(last_n_days)
        if days < 1:
            return None, "lastNDays must be at least 1"
        if days > 365:
            return None, "lastNDays cannot exceed 365"
        return days, ""
    except (ValueError, TypeError):
        return None, "lastNDays must be an integer"


def sanitize_string(s: Any, max_length: int = 500, allow_html: bool = False) -> str:
    """Sanitize string input with XSS prevention."""
    if s is None:
        return ''
    
    if not isinstance(s, str):
        s = str(s)
    
    # Remove control characters
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', s)
    
    if not allow_html:
        # Basic HTML entity encoding for XSS prevention
        s = s.replace('&', '&amp;')
        s = s.replace('<', '&lt;')
        s = s.replace('>', '&gt;')
        s = s.replace('"', '&quot;')
        s = s.replace("'", '&#x27;')
    
    # Normalize whitespace
    s = ' '.join(s.split())
    
    return s[:max_length].strip()


def sanitize_for_filter(s: Any, max_length: int = 100) -> str:
    """Sanitize filter keywords - more permissive than display sanitization."""
    if s is None:
        return ''
    
    if not isinstance(s, str):
        s = str(s)
    
    # Only remove control characters, keep other chars for matching
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', s)
    s = ' '.join(s.split())
    
    return s[:max_length].strip().lower()



def find_site_by_domain(domain: str, config: List[Dict]) -> Optional[Dict]:
    """
    Find site config by domain name with O(1) lookup preferred.
    """
    domain = domain.lower().strip()
    
    # fast lookup
    if domain in DOMAIN_MAP:
        return DOMAIN_MAP[domain]
        
    # Remove www. prefix if present for lookup
    search_domain = domain[4:] if domain.startswith('www.') else domain
    if search_domain in DOMAIN_MAP:
        return DOMAIN_MAP[search_domain]
    
    # Try partial match (domain contains input or input contains domain)
    # This is slower but necessary for partial inputs
    for site in config:
        site_domain = site.get('domain', '').lower()
        if site_domain.startswith('www.'):
            site_domain = site_domain[4:]
        
        if search_domain in site_domain or site_domain.startswith(search_domain + '.'):
            return site
    
    return None

# =============================================================================
# DATE PARSING
# =============================================================================

# Comprehensive date formats
DATE_FORMATS = [
    '%Y-%m-%dT%H:%M:%S%z',
    '%Y-%m-%dT%H:%M:%SZ',
    '%Y-%m-%dT%H:%M:%S.%f%z',
    '%Y-%m-%dT%H:%M:%S.%fZ',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S%z',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d',
    '%d %b %Y %H:%M:%S %z',
    '%d %b %Y %H:%M:%S',
    '%d %b %Y',
    '%d %B %Y',
    '%B %d, %Y',
    '%b %d, %Y',
    '%d/%m/%Y %H:%M:%S',
    '%d/%m/%Y',
    '%m/%d/%Y %H:%M:%S',
    '%m/%d/%Y',
    '%Y/%m/%d',
    '%a, %d %b %Y %H:%M:%S %z',  # RFC 2822
    '%a, %d %b %Y %H:%M:%S %Z',
]


@lru_cache(maxsize=1000)
def parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to ISO format with caching."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Handle common timezone abbreviations
    date_str = date_str.replace('GMT', '+0000').replace('UTC', '+0000')
    
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    
    # Try fromisoformat as fallback
    try:
        normalized = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        pass
    
    return None

# =============================================================================
# HTTP FETCHING
# =============================================================================

# Session with connection pooling
_session = None
_session_lock = threading.Lock()


def get_session() -> requests.Session:
    """Get or create a requests session with connection pooling."""
    global _session
    
    with _session_lock:
        if _session is None:
            _session = requests.Session()
            _session.headers.update({
                'User-Agent': USER_AGENT,
                'Accept': 'application/rss+xml, application/xml, application/atom+xml, text/xml, text/html, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
            })
            # Configure connection pooling
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=0  # We handle retries ourselves
            )
            _session.mount('http://', adapter)
            _session.mount('https://', adapter)
        return _session


def fetch_and_parse_source(source: Dict, domain: str) -> Tuple[List[Dict], str, str]:
    """
    Fetch and parse a single source. Returns (articles, source_type, url).
    Used for parallel fetching of same-priority sources.
    """
    source_type = source.get('type', 'unknown')
    url = source.get('url', '')
    timeout = source.get('timeout_ms', DEFAULT_TIMEOUT_MS) / 1000
    
    if not url:
        return ([], source_type, url)
    
    response = fetch_with_retry(url, timeout)
    if not response:
        return ([], source_type, url)
    
    articles = []
    try:
        if source_type in ['official_rss', 'rsshub', 'google_news']:
            articles = parse_rss_feed(response.content, domain)
            
            # Note: Google News redirect URLs are kept as-is and work when clicked
            # The old quality check was removed because it incorrectly rejected valid redirect URLs
                    
        elif source_type == 'scraper':
            articles = parse_html_scraper_deep(response.content, domain, url, enable_deep_scrape=True)
            
    except Exception as e:
        logger.error("Error parsing %s response from %s: %s", source_type, url, str(e))
        articles = []
    
    return (articles, source_type, url)



def fetch_with_retry(url: str, timeout: float, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
    """Fetch URL with retry logic, connection pooling, and metrics."""
    start_time = time.time()
    
    # Validate URL
    valid, error = validate_url(url)
    if not valid:
        logger.warning("Invalid URL rejected: %s - %s", url, error)
        metrics.increment('fetch_rejected')
        return None
    
    session = get_session()
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_duration('fetch_duration_ms', duration_ms)
            metrics.increment('fetch_success')
            
            logger.debug("Fetched %s in %.1fms", url, duration_ms,
                        extra={'duration_ms': duration_ms})
            
            return response
            
        except Timeout:
            last_error = "timeout"
            logger.warning("Timeout fetching %s (attempt %d/%d)", 
                          url, attempt + 1, retries + 1)
            metrics.increment('fetch_timeout')
            
        except SSLError as e:
            last_error = "ssl_error"
            logger.warning("SSL error fetching %s: %s", url, str(e))
            metrics.increment('fetch_ssl_error')
            break  # Don't retry SSL errors
            
        except ReqConnectionError as e:
            last_error = "connection_error"
            logger.warning("Connection error fetching %s: %s (attempt %d/%d)",
                          url, str(e), attempt + 1, retries + 1)
            metrics.increment('fetch_connection_error')
            
        except RequestException as e:
            last_error = "request_error"
            logger.warning("Request error fetching %s: %s (attempt %d/%d)",
                          url, str(e), attempt + 1, retries + 1)
            metrics.increment('fetch_error')
        
        if attempt < retries:
            sleep_time = RETRY_BACKOFF * (2 ** attempt)  # Exponential backoff
            time.sleep(sleep_time)
    
    duration_ms = (time.time() - start_time) * 1000
    metrics.record_duration('fetch_failed_duration_ms', duration_ms)
    metrics.increment('fetch_failed')
    
    logger.error("Failed to fetch %s after %d attempts: %s",
                url, retries + 1, last_error,
                extra={'error_type': last_error})
    
    return None

# =============================================================================
# RSS PARSING
# =============================================================================

def parse_rss_feed(content: bytes, domain: str) -> List[Dict]:
    """Parse RSS/Atom feed content into normalized articles."""
    articles = []
    
    try:
        feed = feedparser.parse(content)
    except Exception as e:
        logger.error("Failed to parse RSS feed: %s", str(e))
        return []
    
    if feed.bozo and not feed.entries:
        logger.warning("Malformed feed for %s: %s", domain, 
                      getattr(feed, 'bozo_exception', 'unknown error'))
    
    for entry in feed.entries[:MAX_ARTICLES_PER_REQUEST]:
        try:
            title = sanitize_string(getattr(entry, 'title', ''), max_length=300)
            link = getattr(entry, 'link', '')
            
            if not title or not link:
                continue
            
            # For Google News URLs, keep the redirect link as-is
            # The redirect URLs are unique per article and will work when clicked
            # Note: entry.source.href only contains the domain, not the full article URL
            # so we cannot use it for deduplication - keep the Google redirect URL instead
            
            # Validate URL
            valid, _ = validate_url(link)
            if not valid:
                continue
            
            # Parse published date
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                except (ValueError, TypeError, IndexError):
                    pass
            
            if not published_at and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                try:
                    published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc).isoformat()
                except (ValueError, TypeError, IndexError):
                    pass
            
            if not published_at:
                for attr in ('published', 'updated', 'created'):
                    if hasattr(entry, attr) and getattr(entry, attr):
                        published_at = parse_date(str(getattr(entry, attr)))
                        if published_at:
                            break
            
            # Get summary
            summary = ''
            if hasattr(entry, 'summary'):
                summary = sanitize_string(entry.summary, max_length=1000)
            elif hasattr(entry, 'description'):
                summary = sanitize_string(entry.description, max_length=1000)
            
            # Get author
            author = ''
            if hasattr(entry, 'author'):
                author = sanitize_string(entry.author, max_length=100)
            
            # Get categories/tags
            tags = []
            if hasattr(entry, 'tags'):
                for tag in entry.tags[:5]:
                    if hasattr(tag, 'term'):
                        tags.append(sanitize_string(tag.term, max_length=50))
            
            articles.append({
                'title': title,
                'url': link,
                'published_at': published_at,
                'summary': summary,
                'author': author,
                'tags': tags,
                'source_domain': domain
            })
            
        except Exception as e:
            logger.debug("Error parsing RSS entry: %s", str(e))
            continue
    
    return articles

# =============================================================================
# HTML SCRAPING
# =============================================================================

# Selectors for finding articles
ARTICLE_SELECTORS = [
    'article',
    '[itemtype*="Article"]',
    '[class*="post-"]:not([class*="post-nav"])',
    '[class*="article-"]:not([class*="article-nav"])',
    '[class*="entry-"]',
    '[class*="story-"]',
    '[class*="news-item"]',
    '[class*="card-"]:has(h2, h3)',
    '.post',
    '.article',
    '.entry',
    '.story',
    '.news-card',
    'li:has(h2 a, h3 a)',
]

# Selectors for finding titles
TITLE_SELECTORS = ['h1', 'h2', 'h3', 'h4', '[class*="title"]', '[class*="headline"]']

# Selectors for finding dates
DATE_SELECTORS = [
    'time[datetime]',
    'time',
    '[class*="date"]',
    '[class*="time"]',
    '[class*="published"]',
    '[class*="posted"]',
    '[itemprop="datePublished"]',
    '[itemprop="dateCreated"]',
]


def parse_html_scraper(content: bytes, domain: str, base_url: str) -> List[Dict]:
    """Parse HTML page for articles using multiple strategies."""
    articles = []
    seen_urls = set()
    
    try:
        # Use lxml for speed if available, otherwise fallback
        soup = BeautifulSoup(content, 'lxml')
    except Exception:
        # Fallback to html.parser if lxml fails or isn't installed (though it should be)
        try:
            soup = BeautifulSoup(content, 'html.parser')
        except Exception as e:
            logger.error("Failed to parse HTML: %s", str(e))
            return []
    
    # Remove unwanted elements
    for elem in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'noscript']):
        elem.decompose()
    
    # Strategy 1: Look for semantic article elements
    for selector in ARTICLE_SELECTORS:
        try:
            items = soup.select(selector)
            for item in items[:30]:
                article = extract_article_from_element(item, domain, base_url)
                if article and article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    articles.append(article)
                    
                    if len(articles) >= MAX_ARTICLES_PER_REQUEST:
                        break
        except Exception as e:
            logger.debug("Selector %s failed: %s", selector, str(e))
            continue
        
        if len(articles) >= MAX_ARTICLES_PER_REQUEST:
            break
    
    # Strategy 2: Look for headline links if no articles found
    if len(articles) < 5:
        for tag_name in ['h1', 'h2', 'h3']:
            for tag in soup.find_all(tag_name, limit=50):
                try:
                    link = tag.find('a')
                    if not link:
                        parent = tag.parent
                        if parent and parent.name == 'a':
                            link = parent
                    
                    if not link or not link.get('href'):
                        continue
                    
                    url = normalize_url(str(link.get('href')), domain, base_url)
                    if not url or url in seen_urls:
                        continue
                    
                    title = sanitize_string(tag.get_text(), max_length=300)
                    if not title or len(title) < 10:
                        continue
                    
                    seen_urls.add(url)
                    articles.append({
                        'title': title,
                        'url': url,
                        'published_at': None,
                        'summary': '',
                        'author': '',
                        'tags': [],
                        'source_domain': domain
                    })
                    
                    if len(articles) >= MAX_ARTICLES_PER_REQUEST:
                        break
                except Exception:
                    continue
            
            if len(articles) >= MAX_ARTICLES_PER_REQUEST:
                break
    
    return articles


def extract_article_from_element(item, domain: str, base_url: str) -> Optional[Dict]:
    """Extract article data from a DOM element."""
    try:
        # Find title
        title_elem = None
        for selector in TITLE_SELECTORS:
            title_elem = item.find(selector)
            if title_elem:
                break
        
        if not title_elem:
            title_elem = item.find('a')
        
        if not title_elem:
            return None
        
        title = sanitize_string(title_elem.get_text(), max_length=300)
        if not title or len(title) < 10:
            return None
        
        # Find URL
        link_elem = title_elem if title_elem.name == 'a' else title_elem.find('a')
        if not link_elem:
            link_elem = item.find('a')
        
        if not link_elem or not link_elem.get('href'):
            return None
        
        url = normalize_url(str(link_elem.get('href', '')), domain, base_url)
        if not url:
            return None
        
        # Validate URL
        valid, _ = validate_url(url)
        if not valid:
            return None
        
        # Find published date
        published_at = None
        for selector in DATE_SELECTORS:
            date_elem = item.select_one(selector)
            if date_elem:
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    published_at = parse_date(str(datetime_attr))
                else:
                    published_at = parse_date(date_elem.get_text())
                
                if published_at:
                    break
        
        # Find summary
        summary = ''
        summary_elem = item.find('p')
        if summary_elem:
            summary = sanitize_string(summary_elem.get_text(), max_length=500)
        
        # Find author
        author = ''
        author_elem = item.find(class_=re.compile(r'author|byline', re.I))
        if author_elem:
            author = sanitize_string(author_elem.get_text(), max_length=100)
        
        return {
            'title': title,
            'url': url,
            'published_at': published_at,
            'summary': summary,
            'author': author,
            'tags': [],
            'source_domain': domain
        }
        
    except Exception as e:
        logger.debug("Error extracting article: %s", str(e))
        return None


def normalize_url(url: str, domain: str, base_url: str) -> Optional[str]:
    """Normalize a URL to absolute form with validation."""
    if not url:
        return None
    
    url = url.strip()
    
    # Skip non-HTTP URLs
    if url.startswith('#') or url.startswith('javascript:') or url.startswith('mailto:'):
        return None
    
    try:
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            parsed = urlparse(base_url)
            url = f"{parsed.scheme}://{parsed.netloc}{url}"
        elif not url.startswith('http'):
            url = f"https://{domain}/{url.lstrip('/')}"
        
        # Validate final URL
        valid, _ = validate_url(url)
        if not valid:
            return None
        
        return url
        
    except Exception:
        return None


# =============================================================================
# DEEP SCRAPER - FETCHES FULL ARTICLE CONTENT
# =============================================================================

# Selectors for finding main article content on individual article pages
ARTICLE_CONTENT_SELECTORS = [
    'article',
    '[itemprop="articleBody"]',
    '[class*="article-body"]',
    '[class*="article-content"]',
    '[class*="post-content"]',
    '[class*="entry-content"]',
    '[class*="story-body"]',
    '[class*="content-body"]',
    '.prose',
    'main',
    '[role="main"]',
]

# Elements to exclude from article content
CONTENT_EXCLUDE_SELECTORS = [
    'nav', 'header', 'footer', 'aside', 'script', 'style', 'noscript',
    '[class*="sidebar"]', '[class*="comment"]', '[class*="related"]',
    '[class*="share"]', '[class*="social"]', '[class*="newsletter"]',
    '[class*="advertisement"]', '[class*="promo"]', '[class*="author-bio"]',
    '[class*="nav"]', '[class*="menu"]', '[class*="footer"]',
]


def fetch_article_content(url: str, timeout: float = None) -> Optional[Dict]:
    """
    Fetch a single article page and extract full content.
    
    Args:
        url: The article URL to fetch
        timeout: Request timeout in seconds
    
    Returns:
        Dict with full_content, summary, published_at, author, or None on failure
    """
    if timeout is None:
        timeout = DEEP_SCRAPE_TIMEOUT_MS / 1000
    
    start_time = time.time()
    
    try:
        response = fetch_with_retry(url, timeout, retries=1)
        if not response:
            return None
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Remove unwanted elements first
        for selector in CONTENT_EXCLUDE_SELECTORS:
            for elem in soup.select(selector):
                elem.decompose()
        
        # Find article content container
        content_elem = None
        for selector in ARTICLE_CONTENT_SELECTORS:
            content_elem = soup.select_one(selector)
            if content_elem:
                break
        
        if not content_elem:
            # Fallback to body
            content_elem = soup.find('body')
        
        if not content_elem:
            return None
        
        # Extract text content
        paragraphs = content_elem.find_all('p')
        text_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 30:  # Filter out short fragments
                text_parts.append(text)
        
        full_content = ' '.join(text_parts)
        
        if not full_content or len(full_content) < 100:
            # Try extracting all text if paragraphs didn't work
            full_content = content_elem.get_text(separator=' ', strip=True)
        
        # Generate summary (first N characters of meaningful content)
        summary = generate_summary(full_content, DEEP_SCRAPE_SUMMARY_LENGTH)
        
        # Try to extract published date from the article page
        published_at = extract_article_date(soup)
        
        # Try to extract author
        author = extract_article_author(soup)
        
        duration_ms = (time.time() - start_time) * 1000
        logger.debug("Deep scraped %s in %.1fms, content length: %d", 
                    url, duration_ms, len(full_content))
        
        return {
            'full_content': full_content,
            'summary': summary,
            'published_at': published_at,
            'author': author,
            'content_length': len(full_content)
        }
        
    except Exception as e:
        logger.warning("Failed to deep scrape %s: %s", url, str(e))
        return None


def generate_summary(content: str, max_length: int = 500) -> str:
    """
    Generate a summary from article content.
    
    Uses first meaningful sentences up to max_length characters.
    """
    if not content:
        return ''
    
    # Clean up the content
    content = re.sub(r'\s+', ' ', content).strip()
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    summary_parts = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Skip very short sentences (likely noise)
        if len(sentence) < 20:
            continue
        
        # Skip sentences that look like navigation/UI text
        if any(skip in sentence.lower() for skip in [
            'click here', 'read more', 'subscribe', 'sign up', 
            'cookie', 'privacy policy', 'terms of service'
        ]):
            continue
        
        if current_length + len(sentence) + 1 <= max_length:
            summary_parts.append(sentence)
            current_length += len(sentence) + 1
        else:
            # Add partial sentence if we have room
            remaining = max_length - current_length
            if remaining > 50:
                truncated = sentence[:remaining-3].rsplit(' ', 1)[0] + '...'
                summary_parts.append(truncated)
            break
    
    return ' '.join(summary_parts)


def extract_article_date(soup: BeautifulSoup) -> Optional[str]:
    """Extract publication date from article page."""
    
    # Try structured data first (JSON-LD)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0] if data else {}
            
            for key in ['datePublished', 'dateCreated', 'publishedTime']:
                if key in data:
                    return parse_date(str(data[key]))
        except Exception:
            pass
    
    # Try meta tags
    meta_date_props = [
        'article:published_time', 'og:published_time', 'datePublished',
        'date', 'DC.date.issued', 'publish-date'
    ]
    for prop in meta_date_props:
        meta = soup.find('meta', property=prop) or soup.find('meta', attrs={'name': prop})
        if meta and meta.get('content'):
            parsed = parse_date(str(meta['content']))
            if parsed:
                return parsed
    
    # Try time elements
    for selector in DATE_SELECTORS:
        elem = soup.select_one(selector)
        if elem:
            datetime_attr = elem.get('datetime')
            if datetime_attr:
                parsed = parse_date(str(datetime_attr))
                if parsed:
                    return parsed
            else:
                parsed = parse_date(elem.get_text())
                if parsed:
                    return parsed
    
    return None


def extract_article_author(soup: BeautifulSoup) -> str:
    """Extract author from article page."""
    
    # Try structured data first (JSON-LD)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0] if data else {}
            
            author = data.get('author', {})
            if isinstance(author, dict):
                name = author.get('name', '')
                if name:
                    return sanitize_string(name, max_length=100)
            elif isinstance(author, str):
                return sanitize_string(author, max_length=100)
        except Exception:
            pass
    
    # Try meta tags
    meta = soup.find('meta', attrs={'name': 'author'})
    if meta and meta.get('content'):
        return sanitize_string(str(meta['content']), max_length=100)
    
    # Try common author selectors
    author_selectors = [
        '[itemprop="author"]',
        '[class*="author-name"]',
        '[class*="byline"]',
        '.author',
        '[rel="author"]',
    ]
    for selector in author_selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text and len(text) < 100:
                return sanitize_string(text, max_length=100)
    
    return ''


def deep_scrape_article(article: Dict, domain: str) -> Dict:
    """
    Enhance a single article with full content from its page.
    
    Args:
        article: Basic article dict with at least 'url' and 'title'
        domain: The source domain
    
    Returns:
        Enhanced article dict with full_content and improved summary
    """
    url = article.get('url', '')
    if not url:
        return article
    
    # Fetch full content
    content_data = fetch_article_content(url)
    
    if content_data:
        # Enhance the article with full content
        article['full_content'] = content_data.get('full_content', '')
        article['content_length'] = content_data.get('content_length', 0)
        
        # Update summary if we got a better one
        if content_data.get('summary') and len(content_data['summary']) > len(article.get('summary', '')):
            article['summary'] = content_data['summary']
        
        # Update published_at if not already set
        if not article.get('published_at') and content_data.get('published_at'):
            article['published_at'] = content_data['published_at']
        
        # Update author if not already set
        if not article.get('author') and content_data.get('author'):
            article['author'] = content_data['author']
        
        article['deep_scraped'] = True
    else:
        article['deep_scraped'] = False
    
    return article


def deep_scrape_articles_parallel(articles: List[Dict], domain: str, 
                                   max_articles: int = None, 
                                   max_workers: int = None) -> List[Dict]:
    """
    Deep scrape multiple articles in parallel.
    
    Args:
        articles: List of basic article dicts
        domain: The source domain
        max_articles: Maximum number of articles to deep scrape
        max_workers: Number of parallel workers
    
    Returns:
        List of enhanced article dicts
    """
    if max_articles is None:
        max_articles = DEEP_SCRAPE_MAX_ARTICLES
    if max_workers is None:
        max_workers = DEEP_SCRAPE_PARALLEL_WORKERS
    
    # Limit articles to process
    articles_to_scrape = articles[:max_articles]
    remaining_articles = articles[max_articles:]
    
    if not articles_to_scrape:
        return articles
    
    start_time = time.time()
    enhanced_articles = []
    
    logger.info("Deep scraping %d articles from %s with %d workers",
               len(articles_to_scrape), domain, max_workers)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_article = {
            executor.submit(deep_scrape_article, article, domain): article
            for article in articles_to_scrape
        }
        
        for future in as_completed(future_to_article, timeout=30):
            try:
                enhanced_article = future.result()
                enhanced_articles.append(enhanced_article)
            except FuturesTimeoutError:
                # Use original article on timeout
                original = future_to_article[future]
                original['deep_scraped'] = False
                enhanced_articles.append(original)
            except Exception as e:
                logger.warning("Deep scrape error: %s", str(e))
                original = future_to_article[future]
                original['deep_scraped'] = False
                enhanced_articles.append(original)
    
    # Sort back by original order (by title to maintain consistency)
    title_order = {a['title']: i for i, a in enumerate(articles_to_scrape)}
    enhanced_articles.sort(key=lambda x: title_order.get(x.get('title', ''), 999))
    
    # Add back remaining articles (not deep scraped)
    for art in remaining_articles:
        art['deep_scraped'] = False
    enhanced_articles.extend(remaining_articles)
    
    duration_ms = (time.time() - start_time) * 1000
    success_count = sum(1 for a in enhanced_articles if a.get('deep_scraped'))
    
    logger.info("Deep scraping completed in %.1fms. Success: %d/%d",
               duration_ms, success_count, len(articles_to_scrape))
    metrics.record_duration('deep_scrape_batch_duration_ms', duration_ms)
    metrics.increment('deep_scrape_success', success_count)
    metrics.increment('deep_scrape_failed', len(articles_to_scrape) - success_count)
    
    return enhanced_articles


def parse_html_scraper_deep(content: bytes, domain: str, base_url: str, 
                            enable_deep_scrape: bool = True) -> List[Dict]:
    """
    Enhanced HTML scraper with optional deep scraping.
    
    1. First scrapes homepage for article links (like original)
    2. Then visits each article page to extract full content
    
    Args:
        content: Homepage HTML content
        domain: Source domain
        base_url: Base URL for resolving relative links
        enable_deep_scrape: Whether to fetch individual article pages
    
    Returns:
        List of articles with full content and summaries
    """
    # First, get basic articles from homepage
    articles = parse_html_scraper(content, domain, base_url)
    
    if not articles:
        return []
    
    # If deep scraping is enabled, fetch full content
    if enable_deep_scrape and DEEP_SCRAPE_ENABLED:
        articles = deep_scrape_articles_parallel(articles, domain)
    
    return articles

# =============================================================================
# ARTICLE FILTERING
# =============================================================================

# Topic keyword expansion - maps common topics to related keywords
# (Synced from fetch_topic_news.py)
TOPIC_KEYWORDS = {
    'ai': [
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'gpt', 'llm', 'large language model', 'chatgpt', 
        'claude', 'gemini', 'openai', 'anthropic', 'google ai', 'ai model',
        'agent', 'agentic', 'generative ai', 'transformer', 'nlp',
        'natural language', 'computer vision', 'chatbot', 'copilot',
        'ai assistant', 'prompt engineering', 'fine-tuning', 'embedding',
        'video generation', 'audio generation', 'speech recognition',
        'google deepmind', 'nvidia', 'microsoft ai', 'amazon ai', 'apple intelligence',
        'meta ai', 'baidu', 'deepseek', 'mistral', 'adobe firefly', 'hugging face',
        'sora', 'runway', 'midjourney', 'stable diffusion', 'diffusion model',
        'text to image', 'text to video', 'ai safety', 'agi',
        'cursor', 'windsurf', 'github copilot', 'codeium', 'tabnine'
    ],
    'tech': [
        'technology', 'tech', 'software', 'hardware', 'startup', 'gadget',
        'smartphone', 'laptop', 'cloud', 'cyber', 'programming', 'developer',
        'app', 'web', 'digital', 'innovation', 'tech industry', 'tech news',
        'blockchain', 'metaverse', 'virtual reality', 'augmented reality', 'vr', 'ar',
        'mobile', 'tablet', 'wearable', 'smartwatch', 'smart home', 'iot',
        'internet of things', '5g', '6g', 'wifi', 'browser', 'operating system',
        'android', 'ios', 'windows', 'macos', 'linux', 'chrome', 'safari',
        'data center', 'server', 'database', 'api', 'saas', 'paas', 'devops',
        'cybersecurity', 'hacking', 'malware', 'ransomware', 'phishing', 'data breach',
        'silicon valley', 'techcrunch', 'product launch', 'tech giant'
    ],
    'cricket': [
        'cricket', 'ipl', 'test match', 'odi', 't20', 'bcci', 'wicket',
        'batsman', 'batter', 'bowler', 'innings', 'stumps', 'run', 'six', 'four',
        'cricket world cup', 'virat kohli', 'rohit sharma', 'ms dhoni', 'century',
        'half century', 'hat trick', 'lbw', 'catch', 'boundary', 'pitch',
        'world cup', 'asia cup', 'border gavaskar trophy', 'ashes', 'icc',
        'champions trophy', 'ranji trophy', 'sachin tendulkar'
    ],
    'finance': [
        'finance', 'stock', 'market', 'investment', 'banking', 'rupee',
        'dollar', 'share', 'sensex', 'nifty', 'portfolio', 'mutual fund',
        'dividend', 'ipo', 'trading', 'financial', 'economy', 'economics',
        'fiscal', 'budget', 'commodity', 'gold', 'silver', 'bond', 'forex',
        'rbi', 'reserve bank', 'interest rate', 'inflation', 'gdp', 'recession',
        'bull market', 'bear market', 'nasdaq', 'dow jones', 'bse', 'nse',
        'hedge fund', 'private equity', 'venture capital', 'fintech',
        'upi', 'digital payment', 'wallet', 'tax', 'gst', 'income tax'
    ],
    'sports': [
        'sports', 'cricket', 'football', 'soccer', 'tennis', 'badminton',
        'hockey', 'basketball', 'volleyball', 'athlete', 'tournament',
        'championship', 'medal', 'olympics', 'match', 'game', 'team',
        'player', 'coach', 'premier league', 'la liga', 'bundesliga',
        'nba', 'nfl', 'fifa', 'uefa', 'formula 1', 'f1', 'grand prix',
        'boxing', 'mma', 'ufc', 'wrestling', 'swimming', 'marathon',
        'asian games', 'commonwealth games', 'world championship'
    ],
    'politics': [
        'politics', 'election', 'parliament', 'government', 'minister',
        'political', 'policy', 'vote', 'democracy', 'law', 'bill',
        'congress', 'bjp', 'lok sabha', 'rajya sabha', 'pm', 'prime minister',
        'president', 'cabinet', 'opposition', 'ruling party', 'manifesto',
        'campaign', 'rally', 'mp', 'mla', 'governor', 'chief minister',
        'supreme court', 'high court', 'judiciary', 'legislation',
        'foreign policy', 'diplomacy', 'g20', 'brics', 'united nations'
    ],
    'health': [
        'health', 'medical', 'doctor', 'hospital', 'disease', 'vaccine',
        'covid', 'pandemic', 'wellness', 'fitness', 'nutrition', 'medicine',
        'healthcare', 'virus', 'treatment', 'patient', 'surgery', 'diagnosis',
        'mental health', 'anxiety', 'depression', 'therapy', 'counseling',
        'diet', 'exercise', 'yoga', 'meditation', 'workout', 'gym',
        'cancer', 'diabetes', 'heart disease', 'blood pressure', 'pharma'
    ],
    'entertainment': [
        'entertainment', 'movie', 'film', 'cinema', 'bollywood', 'hollywood',
        'actor', 'actress', 'celebrity', 'music', 'concert', 'album',
        'netflix', 'amazon prime', 'ott', 'web series', 'tv show',
        'box office', 'premiere', 'trailer', 'award', 'oscar', 'grammy',
        'emmy', 'golden globe', 'filmfare', 'director', 'producer',
        'streaming', 'disney', 'hotstar', 'youtube', 'influencer', 'viral'
    ],
    'education': [
        'education', 'school', 'college', 'university', 'student', 'teacher',
        'exam', 'admission', 'scholarship', 'degree', 'course', 'learning',
        'neet', 'jee', 'upsc', 'cbse', 'icse', 'academic', 'graduation',
        'iit', 'iim', 'nit', 'gate', 'cat', 'gmat', 'gre', 'board exam',
        'online learning', 'edtech', 'byju', 'unacademy', 'coaching'
    ],
    'crypto': [
        'crypto', 'cryptocurrency', 'bitcoin', 'btc', 'ethereum', 'eth',
        'blockchain', 'web3', 'nft', 'defi', 'token', 'wallet', 'mining',
        'altcoin', 'stablecoin', 'binance', 'coinbase', 'solana', 'dogecoin',
        'smart contract', 'dapp', 'dao', 'airdrop', 'ico', 'crypto exchange'
    ],
    'startup': [
        'startup', 'unicorn', 'funding', 'seed round', 'series a', 'series b',
        'venture capital', 'vc', 'angel investor', 'accelerator', 'incubator',
        'entrepreneur', 'founder', 'ceo', 'cto', 'pivot', 'acquisition',
        'merger', 'ipo', 'valuation', 'burn rate', 'mvp', 'scale up',
        'fintech', 'edtech', 'healthtech', 'y combinator', 'sequoia'
    ],
    'gaming': [
        'gaming', 'video game', 'esports', 'playstation', 'xbox', 'nintendo',
        'steam', 'pc gaming', 'mobile gaming', 'pubg', 'fortnite', 'call of duty',
        'gta', 'minecraft', 'valorant', 'league of legends', 'dota',
        'twitch', 'gamer', 'console', 'gpu', 'graphics card', 'ps5',
        'bgmi', 'free fire', 'gaming tournament'
    ],
    'auto': [
        'auto', 'automobile', 'car', 'bike', 'motorcycle', 'electric vehicle', 'ev',
        'tesla', 'tata', 'mahindra', 'maruti', 'hyundai', 'toyota', 'honda',
        'bmw', 'mercedes', 'audi', 'suv', 'sedan', 'hatchback',
        'petrol', 'diesel', 'hybrid', 'charging station', 'battery',
        'self driving', 'autonomous', 'car launch', 'auto expo'
    ],
    'travel': [
        'travel', 'tourism', 'vacation', 'holiday', 'flight', 'airline',
        'hotel', 'resort', 'booking', 'destination', 'trip', 'tour',
        'passport', 'visa', 'airport', 'railway', 'train', 'cruise',
        'makemytrip', 'airbnb', 'oyo', 'indigo', 'air india', 'travel advisory'
    ],
    'weather': [
        'weather', 'rain', 'rainfall', 'monsoon', 'storm', 'cyclone', 'hurricane',
        'flood', 'drought', 'heatwave', 'cold wave', 'snow', 'snowfall',
        'temperature', 'forecast', 'imd', 'climate', 'climate change',
        'global warming', 'thunderstorm', 'fog', 'smog', 'pollution', 'aqi'
    ],
    'realestate': [
        'real estate', 'property', 'housing', 'apartment', 'flat', 'villa',
        'builder', 'developer', 'construction', 'rera', 'home loan',
        'mortgage', 'rent', 'tenant', 'landlord', 'commercial', 'residential',
        'plot', 'land', 'infrastructure', 'smart city', 'affordable housing'
    ],
    'jobs': [
        'jobs', 'job', 'employment', 'hiring', 'recruitment', 'vacancy',
        'career', 'resume', 'interview', 'salary', 'layoff', 'fired',
        'fresher', 'remote work', 'work from home', 'hybrid',
        'linkedin', 'naukri', 'appraisal', 'promotion', 'internship',
        'placement', 'campus recruitment', 'gig economy', 'freelance'
    ],
}

def filter_articles(articles: List[Dict], topic: Optional[str], 
                   location: Optional[str], last_n_days: Optional[int]) -> List[Dict]:
    """Filter articles by topic, location, and date with deduplication."""
    filtered = []
    now = datetime.now(timezone.utc)
    seen_urls = set()
    seen_titles = set()  # Additional dedup by title
    
    # Prepare filter keywords
    topic_lower = sanitize_for_filter(topic) if topic else None
    location_lower = sanitize_for_filter(location) if location else None
    
    for art in articles:
        # Deduplication by URL
        url_normalized = art['url'].lower().rstrip('/')
        if url_normalized in seen_urls:
            continue
        seen_urls.add(url_normalized)
        
        # Deduplication by title (fuzzy)
        title_normalized = re.sub(r'\s+', ' ', art.get('title', '').lower().strip())
        if title_normalized in seen_titles:
            continue
        seen_titles.add(title_normalized)
        
        # Build searchable text
        text = ' '.join([
            art.get('title', ''),
            art.get('summary', ''),
            ' '.join(art.get('tags', []))
        ]).lower()
        
        # Topic filter with word boundary matching to avoid false positives
        if topic_lower:
            # Expand topic to related keywords if available
            keywords = TOPIC_KEYWORDS.get(topic_lower, [topic_lower])
            
            # Check if any keyword matches
            matched = False
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', text):
                    matched = True
                    break
            
            if not matched:
                continue
        
        # Location filter with word boundary matching
        if location_lower:
            if not re.search(r'\b' + re.escape(location_lower) + r'\b', text):
                continue
        
        # Date filter
        if last_n_days and art.get('published_at'):
            try:
                pub_str = art['published_at']
                if isinstance(pub_str, str):
                    pub_date = datetime.fromisoformat(pub_str.replace('Z', '+00:00'))
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    
                    age_days = (now - pub_date).days
                    if age_days > last_n_days:
                        continue
            except (ValueError, TypeError):
                pass
        
        filtered.append(art)
        
        if len(filtered) >= MAX_ARTICLES_PER_REQUEST:
            break
    
    # Sort by date (newest first)
    filtered.sort(
        key=lambda x: x.get('published_at') or '1970-01-01',
        reverse=True
    )
    
    return filtered




# =============================================================================
# PARALLEL FETCHING
# =============================================================================

def fetch_source_parallel(source: Dict, domain: str) -> Tuple[str, List[Dict]]:
    """Fetch and parse a single source (for parallel execution)."""
    source_type = source.get('type', 'unknown')
    url = source.get('url', '')
    timeout = source.get('timeout_ms', DEFAULT_TIMEOUT_MS) / 1000
    
    response = fetch_with_retry(url, timeout)
    if not response:
        return source_type, []
    
    articles = []
    try:
        if source_type in ['official_rss', 'rsshub', 'google_news']:
            articles = parse_rss_feed(response.content, domain)
        elif source_type == 'scraper':
            # Use deep scraper for priority 4 (scraper type)
            articles = parse_html_scraper_deep(response.content, domain, url, enable_deep_scrape=True)
    except Exception as e:
        logger.error("Error parsing %s response: %s", source_type, str(e))
    
    return source_type, articles


def fetch_all_sources_parallel(sources: List[Dict], domain: str, max_workers: int = 4) -> Dict[str, List[Dict]]:
    """Fetch all sources in parallel."""
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_source = {
            executor.submit(fetch_source_parallel, source, domain): source
            for source in sources
        }
        
        for future in as_completed(future_to_source, timeout=10):
            source = future_to_source[future]
            try:
                source_type, articles = future.result()
                results[source_type] = articles
            except FuturesTimeoutError:
                logger.warning("Parallel fetch timed out for %s", source.get('type'))
            except Exception as e:
                logger.error("Parallel fetch error: %s", str(e))
    
    return results

# =============================================================================
# MAIN ARTICLE RETRIEVAL
# =============================================================================

def get_articles(domain: str, topic: Optional[str] = None, 
                location: Optional[str] = None, lastNDays: Optional[int] = None,
                fast_mode: bool = False, count: Optional[int] = None) -> Dict:
    """
    Main function to retrieve articles using 4-layer fallback strategy.
    
    IMPORTANT RULES:
    1. "Recent" means maximum 15 days old (MAX_RECENT_DAYS)
    2. Default is 10 articles when count not specified
    3. Articles returned in reverse chronological order (newest first)
    4. If a priority source has insufficient articles, try next priority
    5. If no articles found in 15 days after all priorities, return empty with explanation
    
    Args:
        domain: The domain to fetch articles from
        topic: Optional topic keyword filter
        location: Optional location keyword filter
        lastNDays: Days to look back (capped at MAX_RECENT_DAYS=15 for "recent" news)
        fast_mode: If True, skip straight to Google News RSS (fastest source)
        count: Number of articles to return (default: DEFAULT_ARTICLE_COUNT=10)
    
    Returns:
        Dict with sourceUsed, articles list, metadata, and user-friendly messages
    """
    start_time = time.time()
    metrics.increment('get_articles_requests')
    
    # Set defaults and enforce caps
    if count is None:
        count = DEFAULT_ARTICLE_COUNT
    
    # Enforce 15-day cap for "recent" news
    if lastNDays is None:
        lastNDays = MAX_RECENT_DAYS  # Default to 15 days for recent news
    elif lastNDays > MAX_RECENT_DAYS:
        logger.info("Capping lastNDays from %d to %d (MAX_RECENT_DAYS)", lastNDays, MAX_RECENT_DAYS)
        lastNDays = MAX_RECENT_DAYS
    
    # Input validation
    valid, error = validate_domain(domain)
    if not valid:
        logger.warning("Invalid domain provided: %s - %s", domain, error)
        metrics.increment('get_articles_invalid_domain')
        return {
            "sourceUsed": "none",
            "articles": [],
            "error": error,
            "cached": False
        }
    
    # Validate lastNDays
    last_n_days, days_error = validate_last_n_days(lastNDays)
    if days_error:
        logger.warning("Invalid lastNDays: %s", days_error)
    
    # Sanitize filter inputs
    topic_clean = sanitize_for_filter(topic) if topic else None
    location_clean = sanitize_for_filter(location) if location else None
    
    # Check rate limit
    if not rate_limiter.is_allowed(domain):
        retry_after = rate_limiter.get_retry_after(domain)
        logger.warning("Rate limit exceeded for domain: %s", domain)
        metrics.increment('get_articles_rate_limited')
        return {
            "sourceUsed": "none",
            "articles": [],
            "error": f"Rate limit exceeded. Retry after {retry_after} seconds.",
            "retryAfter": retry_after,
            "cached": False
        }
    
    # Check cache
    cached_result = cache.get(domain, topic_clean, location_clean, last_n_days)
    if cached_result:
        logger.info("Cache hit for domain: %s", domain)
        cached_result['cached'] = True
        return cached_result
    
    # Find site config with flexible domain matching
    site = find_site_by_domain(domain, config)
    if not site:
        logger.info("Domain not found in config: %s", domain)
        metrics.increment('get_articles_domain_not_found')
        return {
            "sourceUsed": "none",
            "articles": [],
            "error": f"Domain '{domain}' not configured",
            "cached": False
        }
    
    # Sort sources by priority
    sources = sorted(site.get('sources', []), key=lambda x: x.get('priority', 99))
    
    # Fast mode: Try official RSS first (fresher data), fallback to Google News if it fails
    if fast_mode:
        official_rss = next((s for s in sources if s.get('type') == 'official_rss' and s.get('url')), None)
        google_source = next((s for s in sources if s.get('type') == 'google_news' and s.get('url')), None)
        
        if official_rss and google_source:
            # Try both, official RSS first with quick fallback to Google News
            sources = [official_rss, google_source]
            logger.info(f"Fast mode: Trying official RSS with Google News fallback for {domain}")
        elif official_rss:
            sources = [official_rss]
            logger.info(f"Fast mode: Using official RSS only for {domain}")
        elif google_source:
            sources = [google_source]
            logger.info(f"Fast mode: Using Google News RSS only for {domain}")
    
    # Fetch articles using PARALLEL PRIORITY FETCHING (OPTIMIZED)
    # All priority levels are fetched simultaneously for faster response
    result = None
    
    # Group sources by priority level
    sources_by_priority = defaultdict(list)
    for source in sources:
        priority = source.get('priority', 99)
        sources_by_priority[priority].append(source)
    
    priority_levels = sorted(sources_by_priority.keys())
    logger.info("Starting PARALLEL priority fetch for %d sources across %d priority levels", 
               len(sources), len(sources_by_priority),
               extra={'domain': domain, 'source_count': len(sources)})
    
    # OPTIMIZATION: Fetch ALL priority levels in parallel
    # Each priority level runs its own parallel fetch
    def fetch_priority_level(priority_level: int) -> Tuple[int, List[Dict], List[Tuple]]:
        """Fetch all sources at a given priority level and return results."""
        priority_sources = sources_by_priority[priority_level]
        all_articles = []
        source_info = []
        
        if len(priority_sources) > 1:
            # Parallel fetch for multiple sources - reduced timeout
            with ThreadPoolExecutor(max_workers=min(6, len(priority_sources))) as inner_executor:
                future_to_source = {
                    inner_executor.submit(fetch_and_parse_source, src, domain): src
                    for src in priority_sources
                }
                
                try:
                    for future in as_completed(future_to_source, timeout=5):  # 5s timeout per priority (allows slower feeds)
                        try:
                            articles, src_type, src_url = future.result(timeout=3)  # 3s per source
                            if articles:
                                all_articles.extend(articles)
                                source_info.append((src_type, src_url, len(articles)))
                        except Exception:
                            pass
                except FuturesTimeoutError:
                    pass  # Use partial results
        else:
            # Single source
            source = priority_sources[0]
            try:
                articles, src_type, src_url = fetch_and_parse_source(source, domain)
                if articles:
                    all_articles.extend(articles)
                    source_info.append((src_type, src_url, len(articles)))
            except Exception:
                pass
        
        return (priority_level, all_articles, source_info)
    
    # Launch all priority levels in parallel with overall 10-second timeout
    priority_results = {}
    with ThreadPoolExecutor(max_workers=len(priority_levels)) as executor:
        future_to_priority = {
            executor.submit(fetch_priority_level, pl): pl
            for pl in priority_levels
        }
        
        try:
            for future in as_completed(future_to_priority, timeout=10):  # 10s overall timeout
                pl = future_to_priority[future]
                try:
                    priority_level, articles, source_info = future.result(timeout=6)  # 6s per priority
                    if articles:
                        priority_results[priority_level] = (articles, source_info)
                        logger.info("Priority %d returned %d articles", priority_level, len(articles))
                    else:
                        logger.info("Priority %d returned 0 articles", priority_level)
                except Exception as e:
                    logger.warning("Priority %d fetch error: %s", pl, str(e))
        except FuturesTimeoutError:
            logger.warning("Parallel priority fetch timeout (10s), got %d of %d priorities", 
                          len(priority_results), len(priority_levels))
    
    logger.info("Collected results from priorities: %s", list(priority_results.keys()))
    
    # Process results in priority order (lower = higher priority)
    # FIXED: Aggregate articles from multiple priorities if needed to reach requested count
    aggregated_articles = []
    aggregated_sources = []
    seen_urls = set()  # Global dedup across all priorities
    
    for priority_level in priority_levels:
        if priority_level not in priority_results:
            continue
        
        all_articles, source_info = priority_results[priority_level]
        
        # Deduplicate against already collected articles
        new_articles = []
        for article in all_articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                new_articles.append(article)
        
        if not new_articles:
            continue
        
        # Filter by topic, location, date
        filtered = filter_articles(new_articles, topic_clean, location_clean, last_n_days)
        
        logger.info("Priority %d: %d articles (deduplicated to %d, filtered to %d)", 
                   priority_level, len(all_articles), len(new_articles), len(filtered))
        
        if filtered:
            aggregated_articles.extend(filtered)
            aggregated_sources.append((priority_level, source_info, len(filtered)))
            
            logger.info("Aggregated total: %d articles (need %d)", len(aggregated_articles), count)
            
            # If we have enough articles, stop looking at more priorities
            if len(aggregated_articles) >= count:
                logger.info("Reached requested count %d, stopping priority scan", count)
                break
    
    # Build result from aggregated articles
    if aggregated_articles:
        # Build source description
        sources_desc_parts = []
        for plevel, sinfo, scount in aggregated_sources:
            src_types = ", ".join([f"{st}" for st, su, _ in sinfo[:2]])
            if len(sinfo) > 2:
                src_types += f" +{len(sinfo)-2}"
            sources_desc_parts.append(f"p{plevel}[{src_types}]({scount})")
        
        result = {
            "sourceUsed": " + ".join(sources_desc_parts),
            "articles": aggregated_articles,
            "cached": False
        }
    
    # Build final result with user-friendly messaging
    if result is None:
        logger.info("All sources exhausted for domain: %s", domain)
        metrics.increment('get_articles_no_results')
        result = {
            "sourceUsed": "none",
            "articles": [],
            "cached": False,
            "message": f"No articles found from {domain} in the last {lastNDays} days. "
                      f"Tried all available sources (official RSS, RSSHub, Google News, scraper). "
                      f"This site may not have published recent content or may be blocking our requests."
        }
    else:
        # Sort articles by date (reverse chronological - newest first)
        articles = result.get('articles', [])
        if articles:
            articles.sort(key=lambda x: x.get('published_at') or '', reverse=True)
            # Limit to requested count
            result['articles'] = articles[:count]
        
        metrics.increment('get_articles_success')
        metrics.increment('articles_returned', len(result['articles']))
        
        # Add helpful message if we found fewer than requested
        if len(result['articles']) < count:
            result['message'] = (f"Found {len(result['articles'])} articles (requested {count}) "
                                f"from last {lastNDays} days. This is all the recent content available.")
        
        # Cache successful results
        cache.set(domain, result, topic_clean, location_clean, last_n_days)
    
    # Add metadata
    duration_ms = (time.time() - start_time) * 1000
    result['durationMs'] = round(duration_ms, 2)
    metrics.record_duration('get_articles_duration_ms', duration_ms)
    
    logger.info("get_articles completed for %s in %.1fms", domain, duration_ms,
               extra={'domain': domain, 'duration_ms': duration_ms, 
                      'article_count': len(result['articles'])})
    
    return result

# =============================================================================
# HEALTH & METRICS
# =============================================================================

def get_top_news(count: Optional[int] = None, topic: Optional[str] = None, location: Optional[str] = None, 
                  lastNDays: Optional[int] = None) -> Dict:
    """
    Aggregate top news from ALL configured domains.
    Fetches from each domain and merges results sorted by date (reverse chronological).
    
    Args:
        count: Number of articles to return (default: DEFAULT_ARTICLE_COUNT=10)
        topic: Optional topic filter
        location: Optional location filter
        lastNDays: Days to look back (capped at MAX_RECENT_DAYS=15)
    """
    start_time = time.time()
    metrics.increment('get_top_news_requests')
    
    # Set defaults and enforce caps
    if count is None:
        count = DEFAULT_ARTICLE_COUNT
    
    # Enforce 15-day cap for recent news
    if lastNDays is None:
        lastNDays = MAX_RECENT_DAYS
    elif lastNDays > MAX_RECENT_DAYS:
        logger.info("Capping lastNDays from %d to %d for top news", lastNDays, MAX_RECENT_DAYS)
        lastNDays = MAX_RECENT_DAYS
    
    # Validate count
    if count < 1:
        count = DEFAULT_ARTICLE_COUNT
    if count > MAX_ARTICLES_PER_REQUEST:
        count = MAX_ARTICLES_PER_REQUEST
    
    all_articles = []
    sources_used = []
    errors = []
    
    # For top news, only fetch from top priority sites (faster response)
    # Filter sites by priority field (lower number = higher priority)
    TOP_NEWS_SITE_LIMIT = 12  # Only fetch from top 12 sites
    
    # FIXED: Only include sites with numeric priority 1-12, exclude null priority sites
    priority_sites = [
        s for s in config 
        if s.get('domain') 
        and s.get('priority') is not None 
        and isinstance(s.get('priority'), int)
        and 1 <= s.get('priority') <= 12
    ]
    
    sites_to_fetch = sorted(priority_sites, key=lambda x: x.get('priority'))[:TOP_NEWS_SITE_LIMIT]
    
    logger.info(f"Fetching top news from {len(sites_to_fetch)} priority sites")
    
    # Parallel domain fetching for top news - use fewer workers for faster response
    max_workers = min(4, len(sites_to_fetch))  # Reduced from 8 to 4 for faster response
    
    def fetch_domain(site_config):
        domain = site_config.get('domain')
        if not domain:
            return None
        
        try:
            result = get_articles(
                domain=domain,
                topic=topic,
                location=location,
                lastNDays=lastNDays,
                fast_mode=True  # Skip to Google News RSS for speed
            )
            
            if result.get('articles'):
                for article in result['articles']:
                    article['_fetch_source'] = result.get('sourceUsed', 'unknown')
                
                return {
                    'domain': domain,
                    'articles': result['articles'],
                    'source_info': {
                        'domain': domain,
                        'source': result.get('sourceUsed', 'unknown'),
                        'count': len(result['articles']),
                        'cached': result.get('cached', False)
                    }
                }
            else:
                return {
                    'domain': domain,
                    'error': 'no articles found'
                }
        except Exception as e:
            logger.error("Error fetching from %s: %s", domain, str(e))
            return {
                'domain': domain,
                'error': str(e)
            }
    
    # Use ThreadPoolExecutor for parallel domain fetching with overall 15-second timeout
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_domain, site_config): site_config 
                   for site_config in sites_to_fetch}
        
        # Process futures as they complete with 15-second overall timeout for all domains
        try:
            for future in as_completed(futures, timeout=15):
                try:
                    result = future.result(timeout=5)  # 5-second max per domain
                    if result:
                        if 'articles' in result and result['articles']:
                            all_articles.extend(result['articles'])
                            sources_used.append(result['source_info'])
                        elif 'error' in result:
                            errors.append({'domain': result['domain'], 'error': result['error']})
                except Exception as e:
                    site = futures[future]
                    domain = site.get('domain', 'unknown')
                    logger.error("Error fetching from domain %s: %s", domain, str(e))
                    errors.append({'domain': domain, 'error': str(e)})
        except FuturesTimeoutError:
            logger.warning("get_top_news overall timeout (15s) reached, returning partial results")
            # Cancel remaining futures
            for future in futures:
                future.cancel()
    
    # Sort all articles by published date (newest first)
    def get_sort_key(article):
        pub_date = article.get('published_at', '')
        if pub_date:
            try:
                return parse_date(pub_date) or datetime.min.replace(tzinfo=timezone.utc)
            except:
                return datetime.min.replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)
    
    all_articles.sort(key=get_sort_key, reverse=True)
    
    # Take top N articles
    top_articles = all_articles[:count]
    
    # Remove internal field
    for article in top_articles:
        article.pop('_fetch_source', None)
    
    duration_ms = (time.time() - start_time) * 1000
    metrics.record_duration('get_top_news_duration_ms', duration_ms)
    
    if top_articles:
        metrics.increment('get_top_news_success')
    
    return {
        "articles": top_articles,
        "totalFetched": len(all_articles),
        "sourcesQueried": len(sources_used),
        "sources": sources_used,
        "errors": errors if errors else None,
        "durationMs": round(duration_ms, 2)
    }


def get_health() -> Dict:
    """Health check - returns server status and diagnostics."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "configuredDomains": [s.get('domain') for s in config],
        "domainCount": len(config),
        "cache": cache.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def get_metrics() -> Dict:
    """Get detailed metrics for observability."""
    return {
        "metrics": metrics.get_stats(),
        "cache": cache.stats(),
        "config": {
            "maxArticles": MAX_ARTICLES_PER_REQUEST,
            "cacheTtl": CACHE_TTL_SECONDS,
            "rateLimit": f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s",
            "parallelFetch": PARALLEL_FETCH
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# =============================================================================
# MCP REQUEST HANDLER
# =============================================================================

def handle_request(request: Dict) -> Optional[Dict]:
    """Handle incoming MCP JSON-RPC requests."""
    method = request.get('method')
    id_ = request.get('id')
    params = request.get('params', {})
    
    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True}
                },
                "serverInfo": {
                    "name": "news-aggregator",
                    "version": "2.0.0"
                }
            }
        }
    
    elif method == 'notifications/initialized':
        return None
    
    elif method == 'tools/list':
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "tools": [
                    {
                        "name": "get_articles",
                        "description": "Retrieve RECENT articles from a domain (max 15 days old). Uses 4-layer fallback (Official RSS → RSSHub → Google News → Scraper). Returns newest first in reverse chronological order. Default: 10 articles from last 15 days.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "domain": {
                                    "type": "string",
                                    "description": "The domain to fetch articles from (e.g., 'techcrunch.com')"
                                },
                                "topic": {
                                    "type": "string",
                                    "description": "Optional topic keyword to filter articles by title/summary"
                                },
                                "location": {
                                    "type": "string",
                                    "description": "Optional location keyword to filter articles"
                                },
                                "lastNDays": {
                                    "type": "integer",
                                    "description": "Days to look back (1-15, default: 15). For 'recent' news, capped at 15 days max",
                                    "minimum": 1,
                                    "maximum": 15,
                                    "default": 15
                                },
                                "count": {
                                    "type": "integer",
                                    "description": "Number of articles to return (default: 10 when user says 'recent/top/latest' without number)",
                                    "minimum": 1,
                                    "maximum": 50,
                                    "default": 10
                                },
                                "fast_mode": {
                                    "type": "boolean",
                                    "description": "Skip to Google News directly (faster but may miss some articles)",
                                    "default": False
                                }
                            },
                            "required": ["domain"]
                        }
                    },
                    {
                        "name": "health_check",
                        "description": "Check server health and list configured domains",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_metrics",
                        "description": "Get detailed server metrics for monitoring and observability",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_top_news",
                        "description": "Aggregate top RECENT news from ALL configured domains. Returns newest first. Default: 8 articles from last 15 days across all priority sites.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "count": {
                                    "type": "integer",
                                    "description": "Number of articles to return (default: 10, max: 50)",
                                    "default": 10,
                                    "minimum": 1,
                                    "maximum": 50
                                },
                                "topic": {
                                    "type": "string",
                                    "description": "Optional topic keyword to filter articles"
                                },
                                "location": {
                                    "type": "string",
                                    "description": "Optional location keyword to filter articles"
                                },
                                "lastNDays": {
                                    "type": "integer",
                                    "description": "Days to look back (1-15, default: 15). Capped at 15 for recent news",
                                    "default": 15,
                                    "minimum": 1,
                                    "maximum": 15
                                }
                            },
                            "required": []
                        }
                    }
                ]
            }
        }
    
    elif method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments', {})
        
        if tool_name == 'get_articles':
            result = get_articles(**arguments)
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False)
                        }
                    ]
                }
            }
        
        elif tool_name == 'health_check':
            result = get_health()
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }
        
        elif tool_name == 'get_metrics':
            result = get_metrics()
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }
        
        elif tool_name == 'get_top_news':
            result = get_top_news(**arguments)
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False)
                        }
                    ]
                }
            }
        
        else:
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point - STDIO MCP server loop."""
    logger.info("NewsNexus MCP Server v2.0.0 started")
    logger.info("Configuration: %d sites, cache TTL=%ds, rate limit=%d/%ds",
               len(config), CACHE_TTL_SECONDS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            response = handle_request(request)
            
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
        
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON received: %s", str(e))
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
            }
            print(json.dumps(error_response), flush=True)
        
        except KeyError as e:
            logger.error("Missing required field: %s", str(e))
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": f"Invalid request: missing field {e}"}
            }
            print(json.dumps(error_response), flush=True)
        
        except Exception as e:
            logger.exception("Unexpected error processing request")
            metrics.increment('server_errors')
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": "Internal server error"}
            }
            print(json.dumps(error_response), flush=True)


if __name__ == '__main__':
    main()
