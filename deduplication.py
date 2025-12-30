"""
Article Deduplication System
Prevents duplicate articles from multiple sources
"""

import hashlib
from difflib import SequenceMatcher
from datetime import datetime, timedelta

class ArticleDeduplicator:
    """
    Detects and removes duplicate articles using multiple strategies:
    1. Exact URL match
    2. Content hash (for same article, different URLs)
    3. Title similarity (for similar articles)
    """
    
    def __init__(self):
        self.seen_urls = set()
        self.seen_hashes = set()
        self.seen_titles = []
        self.title_similarity_threshold = 0.85  # 85% similar = duplicate
        
    def generate_content_hash(self, article):
        """
        Generate unique hash from article content
        Uses: title + first 200 chars of description
        """
        content = f"{article.get('title', '')}{article.get('description', '')[:200]}"
        # Normalize: lowercase, remove extra spaces
        content = ' '.join(content.lower().split())
        return hashlib.md5(content.encode()).hexdigest()
    
    def calculate_title_similarity(self, title1, title2):
        """Calculate similarity between two titles (0-1)"""
        return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
    
    def is_duplicate(self, article):
        """
        Check if article is duplicate
        Returns: (is_duplicate: bool, reason: str)
        """
        url = article.get('url', '')
        title = article.get('title', '')
        
        # Strategy 1: Exact URL match
        if url and url in self.seen_urls:
            return True, "duplicate_url"
        
        # Strategy 2: Content hash match
        content_hash = self.generate_content_hash(article)
        if content_hash in self.seen_hashes:
            return True, "duplicate_content"
        
        # Strategy 3: Title similarity
        for seen_title in self.seen_titles:
            similarity = self.calculate_title_similarity(title, seen_title)
            if similarity >= self.title_similarity_threshold:
                return True, f"similar_title_{similarity:.2f}"
        
        return False, "unique"
    
    def add_article(self, article):
        """Mark article as seen"""
        self.seen_urls.add(article.get('url', ''))
        self.seen_hashes.add(self.generate_content_hash(article))
        self.seen_titles.append(article.get('title', ''))
    
    def deduplicate_articles(self, articles):
        """
        Remove duplicates from article list
        Returns: (unique_articles, duplicate_stats)
        """
        unique_articles = []
        duplicate_stats = {
            'total': len(articles),
            'unique': 0,
            'duplicate_url': 0,
            'duplicate_content': 0,
            'similar_title': 0
        }
        
        for article in articles:
            is_dup, reason = self.is_duplicate(article)
            
            if not is_dup:
                unique_articles.append(article)
                self.add_article(article)
                duplicate_stats['unique'] += 1
            else:
                if reason == 'duplicate_url':
                    duplicate_stats['duplicate_url'] += 1
                elif reason == 'duplicate_content':
                    duplicate_stats['duplicate_content'] += 1
                elif reason.startswith('similar_title'):
                    duplicate_stats['similar_title'] += 1
        
        return unique_articles, duplicate_stats


# Advanced: Database-backed deduplication (for production)
class DatabaseDeduplicator:
    """
    Production-ready deduplication using database
    Stores article fingerprints for 30 days
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
        self._create_table()
    
    def _create_table(self):
        """Create deduplication table"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS article_fingerprints (
                id SERIAL PRIMARY KEY,
                url_hash VARCHAR(32) UNIQUE,
                content_hash VARCHAR(32),
                title_normalized VARCHAR(500),
                first_seen TIMESTAMP DEFAULT NOW(),
                INDEX idx_content_hash (content_hash),
                INDEX idx_first_seen (first_seen)
            )
        """)
    
    def is_duplicate_db(self, article):
        """Check if article exists in database"""
        url_hash = hashlib.md5(article['url'].encode()).hexdigest()
        
        result = self.db.query(
            "SELECT id FROM article_fingerprints WHERE url_hash = %s",
            (url_hash,)
        )
        
        return result is not None
    
    def add_article_db(self, article):
        """Add article fingerprint to database"""
        url_hash = hashlib.md5(article['url'].encode()).hexdigest()
        content_hash = self.generate_content_hash(article)
        title = article.get('title', '')[:500]
        
        self.db.execute("""
            INSERT INTO article_fingerprints (url_hash, content_hash, title_normalized)
            VALUES (%s, %s, %s)
            ON CONFLICT (url_hash) DO NOTHING
        """, (url_hash, content_hash, title))
    
    def cleanup_old_fingerprints(self, days=30):
        """Remove fingerprints older than N days"""
        self.db.execute("""
            DELETE FROM article_fingerprints
            WHERE first_seen < NOW() - INTERVAL '%s days'
        """, (days,))


# Example Usage
if __name__ == "__main__":
    # Sample articles (some duplicates)
    articles = [
        {
            "title": "OpenAI Launches GPT-5",
            "url": "https://techcrunch.com/gpt5-launch",
            "description": "OpenAI today announced GPT-5..."
        },
        {
            "title": "OpenAI Launches GPT-5",  # Exact duplicate
            "url": "https://techcrunch.com/gpt5-launch",
            "description": "OpenAI today announced GPT-5..."
        },
        {
            "title": "OpenAI Unveils GPT-5",  # Similar title
            "url": "https://theverge.com/openai-gpt5",
            "description": "OpenAI today announced GPT-5..."
        },
        {
            "title": "Google Releases Gemini 2.0",  # Unique
            "url": "https://techcrunch.com/gemini-2",
            "description": "Google announced Gemini 2.0..."
        }
    ]
    
    # Deduplicate
    deduplicator = ArticleDeduplicator()
    unique_articles, stats = deduplicator.deduplicate_articles(articles)
    
    print(f"Total articles: {stats['total']}")
    print(f"Unique articles: {stats['unique']}")
    print(f"Duplicate URLs: {stats['duplicate_url']}")
    print(f"Duplicate content: {stats['duplicate_content']}")
    print(f"Similar titles: {stats['similar_title']}")
    print(f"\nUnique articles:")
    for article in unique_articles:
        print(f"  - {article['title']}")
