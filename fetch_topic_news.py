#!/usr/bin/env python3
"""
Flexible news fetcher for ANY topic with priority domain fallback.
Supports: AI news, Tech news, Cricket news, Finance news, etc.

Usage:
  python fetch_topic_news.py --topic "cricket" --json
  python fetch_topic_news.py --topic "technology" --json
  python fetch_topic_news.py --topic "finance" --json
"""

import sys
import os
import html
import re
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import get_articles, config as main_config

# Global flag to suppress logs when outputting JSON
QUIET_MODE = False

def log(*args, **kwargs):
    """Print only if not in quiet mode."""
    if not QUIET_MODE:
        print(*args, **kwargs)

def fetch_from_domains_parallel(domains, topic_keywords, location, limit_per_domain, days=10, max_workers=8, topic=None):
    """Helper to fetch from multiple domains in parallel."""
    all_articles = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_domain = {}
        for domain in domains:
            # Smart Location Filtering:
            # If requesting "India" news from a known Indian domain, DISABLE location filtering
            # This prevents finding 0 articles because "India" isn't explicitly mentioned in every title
            effective_location = location
            if location and location.lower() in ['india', 'in']:
                indian_domains = [
                    'ndtv.com', 'indianexpress.com', 'timesofindia.indiatimes.com',
                    'hindustantimes.com', 'gadgets360.com', 'economictimes.indiatimes.com',
                    'analyticsindiamag.com', 'indiatechnologynews.in', 'devshorts.in',
                    'analyticsvidhya.com', 'livemint.com', 'moneycontrol.com', 'thehindu.com',
                    'business-standard.com', 'financialexpress.com', 'deccanherald.com'
                ]
                if any(d in domain for d in indian_domains) or domain.endswith('.in'):
                    effective_location = None
            
            future_to_domain[executor.submit(
                get_articles, 
                domain, 
                topic=topic,  # FIXED: Pass topic to get_articles for better filtering
                location=effective_location, 
                lastNDays=days, 
                count=limit_per_domain
            )] = domain
        
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                result = future.result()
                if result.get('articles'):
                    all_articles.extend(result['articles'])
            except Exception as e:
                # Fail silently for individual domains to keep going
                pass
    
    # Filter by topic keywords
    filtered = [
        article for article in all_articles
        if is_topic_related(article, topic_keywords)
    ]
    
    # Sort by date (newest first)
    filtered.sort(
        key=lambda x: x.get('published_at') or '1970-01-01',
        reverse=True
    )
    
    # STRICT: Limit to requested count to avoid over-fetching
    return filtered[:limit_per_domain]

# Topic keyword mappings - comprehensive list for daily news filtering
TOPIC_KEYWORDS = {
    'ai': [
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'gpt', 'llm', 'large language model', 'chatgpt', 
        'claude', 'gemini', 'openai', 'anthropic', 'google ai', 'ai model',
        'agent', 'agentic', 'generative ai', 'transformer', 'nlp',
        'natural language', 'computer vision', 'chatbot', 'copilot',
        'ai assistant', 'prompt engineering', 'fine-tuning', 'embedding',
        'video generation', 'audio generation', 'generative text', 'speech recognition',
        'google deepmind', 'nvidia', 'microsoft ai', 'amazon ai', 'apple intelligence',
        'meta ai', 'baidu', 'deepseek', 'mistral', 'adobe firefly', 'hugging face',
        'alibaba', 'glm', 'kimi', 'sora', 'runway', 'midjourney', 'stable diffusion',
        'diffusion model', 'text to image', 'text to video', 'ai safety', 'agi',
        'cursor', 'windsurf', 'replit', 'github copilot', 'codeium', 'tabnine'
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
        'cricket world cup', 'cricket match', 'virat kohli', 'rohit sharma',
        'ms dhoni', 'cricket series', 'cricketer', 'cricket team', 'century',
        'half century', 'hat trick', 'lbw', 'catch', 'boundary', 'pitch',
        'world cup', 'asia cup', 'border gavaskar trophy', 'ashes', 'icc',
        'champions trophy', 'ranji trophy', 'cwc', 'sachin tendulkar'
    ],
    'finance': [
        'finance', 'stock', 'market', 'investment', 'banking', 'rupee',
        'dollar', 'share', 'sensex', 'nifty', 'portfolio', 'mutual fund',
        'dividend', 'ipo', 'trading', 'financial', 'economy', 'economics',
        'fiscal', 'budget', 'commodity', 'gold', 'silver', 'bond', 'forex',
        'rbi', 'reserve bank', 'interest rate', 'inflation', 'gdp', 'recession',
        'bull market', 'bear market', 'nasdaq', 'dow jones', 's&p', 'bse', 'nse',
        'hedge fund', 'private equity', 'venture capital', 'vc funding', 'fintech',
        'upi', 'digital payment', 'wallet', 'tax', 'gst', 'income tax'
    ],
    'sports': [
        'sports', 'cricket', 'football', 'soccer', 'tennis', 'badminton',
        'hockey', 'basketball', 'volleyball', 'athlete', 'tournament',
        'championship', 'medal', 'olympics', 'match', 'game', 'team',
        'player', 'coach', 'sport news', 'premier league', 'la liga',
        'bundesliga', 'serie a', 'nba', 'nfl', 'mlb', 'fifa', 'uefa',
        'formula 1', 'f1', 'grand prix', 'racing', 'golf', 'boxing', 'mma', 'ufc',
        'wrestling', 'swimming', 'athletics', 'marathon', 'asian games',
        'commonwealth games', 'world championship', 'pro kabaddi'
    ],
    'politics': [
        'politics', 'election', 'parliament', 'government', 'minister',
        'political', 'policy', 'vote', 'democracy', 'law', 'bill',
        'state', 'national', 'congress', 'bjp', 'political party',
        'election commission', 'lok sabha', 'rajya sabha', 'pm', 'prime minister',
        'president', 'cabinet', 'opposition', 'ruling party', 'manifesto',
        'campaign', 'rally', 'constituency', 'mp', 'mla', 'governor', 'chief minister',
        'supreme court', 'high court', 'judiciary', 'legislation', 'amendment',
        'foreign policy', 'diplomacy', 'g20', 'brics', 'united nations', 'nato'
    ],
    'health': [
        'health', 'medical', 'doctor', 'hospital', 'disease', 'vaccine',
        'covid', 'pandemic', 'wellness', 'fitness', 'nutrition', 'medicine',
        'health news', 'healthcare', 'virus', 'treatment', 'patient',
        'symptom', 'disease outbreak', 'who', 'aiims', 'surgery', 'diagnosis',
        'mental health', 'anxiety', 'depression', 'therapy', 'counseling',
        'diet', 'exercise', 'yoga', 'meditation', 'workout', 'gym',
        'cancer', 'diabetes', 'heart disease', 'stroke', 'blood pressure',
        'ayurveda', 'homeopathy', 'pharma', 'drug', 'clinical trial'
    ],
    'entertainment': [
        'entertainment', 'movie', 'film', 'cinema', 'bollywood', 'hollywood',
        'actor', 'actress', 'celebrity', 'music', 'concert', 'album',
        'netflix', 'amazon prime', 'ott', 'web series', 'tv show',
        'box office', 'premiere', 'trailer', 'award', 'oscar', 'grammy',
        'emmy', 'golden globe', 'filmfare', 'iifa', 'director', 'producer',
        'streaming', 'disney', 'hotstar', 'sony liv', 'zee5', 'jio cinema',
        'tollywood', 'kollywood', 'south indian', 'anime', 'k-drama',
        'podcast', 'spotify', 'youtube', 'influencer', 'viral'
    ],
    'education': [
        'education', 'school', 'college', 'university', 'student', 'teacher',
        'exam', 'admission', 'scholarship', 'degree', 'course', 'learning',
        'neet', 'jee', 'upsc', 'cbse', 'icse', 'academic', 'graduation',
        'entrance exam', 'study', 'curriculum', 'iit', 'iim', 'nit', 'bits',
        'gate', 'cat', 'gmat', 'gre', 'toefl', 'ielts', 'sat', 'board exam',
        'online learning', 'edtech', 'byju', 'unacademy', 'coaching',
        'phd', 'masters', 'bachelor', 'diploma', 'skill development'
    ],
    'crypto': [
        'crypto', 'cryptocurrency', 'bitcoin', 'btc', 'ethereum', 'eth',
        'blockchain', 'web3', 'nft', 'defi', 'token', 'wallet', 'mining',
        'altcoin', 'stablecoin', 'usdt', 'usdc', 'binance', 'coinbase',
        'solana', 'cardano', 'dogecoin', 'shiba', 'xrp', 'ripple', 'polygon',
        'smart contract', 'dapp', 'dao', 'metaverse', 'airdrop', 'ico',
        'crypto exchange', 'cold wallet', 'hot wallet', 'ledger', 'trezor'
    ],
    'startup': [
        'startup', 'unicorn', 'funding', 'seed round', 'series a', 'series b',
        'venture capital', 'vc', 'angel investor', 'accelerator', 'incubator',
        'entrepreneur', 'founder', 'ceo', 'cto', 'pivot', 'acquisition',
        'merger', 'ipo', 'valuation', 'burn rate', 'runway', 'mvp',
        'product market fit', 'scale up', 'growth hacking', 'b2b', 'b2c',
        'saas', 'fintech', 'edtech', 'healthtech', 'agritech', 'proptech',
        'y combinator', 'techstars', 'sequoia', 'accel', 'tiger global'
    ],
    'gaming': [
        'gaming', 'video game', 'esports', 'playstation', 'xbox', 'nintendo',
        'steam', 'pc gaming', 'mobile gaming', 'pubg', 'fortnite', 'call of duty',
        'gta', 'minecraft', 'valorant', 'league of legends', 'dota', 'csgo',
        'twitch', 'streaming', 'gamer', 'console', 'gpu', 'graphics card',
        'game pass', 'ps5', 'switch', 'vr gaming', 'game developer', 'indie game',
        'bgmi', 'free fire', 'mobile legends', 'gaming tournament'
    ],
    'auto': [
        'auto', 'automobile', 'car', 'bike', 'motorcycle', 'electric vehicle', 'ev',
        'tesla', 'tata', 'mahindra', 'maruti', 'hyundai', 'toyota', 'honda',
        'bmw', 'mercedes', 'audi', 'porsche', 'ferrari', 'lamborghini',
        'suv', 'sedan', 'hatchback', 'truck', 'bus', 'scooter', 'moped',
        'petrol', 'diesel', 'hybrid', 'charging station', 'battery',
        'self driving', 'autonomous', 'adas', 'car launch', 'auto expo'
    ],
    'travel': [
        'travel', 'tourism', 'vacation', 'holiday', 'flight', 'airline',
        'hotel', 'resort', 'booking', 'destination', 'trip', 'tour',
        'passport', 'visa', 'airport', 'railway', 'train', 'cruise',
        'backpacking', 'adventure', 'beach', 'mountain', 'heritage',
        'makemytrip', 'goibibo', 'airbnb', 'oyo', 'indigo', 'air india',
        'tourist', 'travel guide', 'itinerary', 'travel ban', 'travel advisory'
    ],
    'weather': [
        'weather', 'rain', 'rainfall', 'monsoon', 'storm', 'cyclone', 'hurricane',
        'flood', 'drought', 'heatwave', 'cold wave', 'snow', 'snowfall',
        'temperature', 'humidity', 'forecast', 'imd', 'meteorological',
        'climate', 'climate change', 'global warming', 'el nino', 'la nina',
        'thunderstorm', 'lightning', 'fog', 'smog', 'pollution', 'aqi'
    ],
    'realestate': [
        'real estate', 'property', 'housing', 'apartment', 'flat', 'villa',
        'builder', 'developer', 'construction', 'rera', 'home loan',
        'mortgage', 'rent', 'tenant', 'landlord', 'lease', 'commercial',
        'residential', 'plot', 'land', 'infrastructure', 'smart city',
        'affordable housing', 'luxury', 'township', 'square feet', 'carpet area'
    ],
    'jobs': [
        'jobs', 'job', 'employment', 'hiring', 'recruitment', 'vacancy',
        'career', 'resume', 'interview', 'salary', 'layoff', 'fired',
        'fresher', 'experienced', 'remote work', 'work from home', 'hybrid',
        'linkedin', 'naukri', 'indeed', 'glassdoor', 'appraisal', 'promotion',
        'internship', 'placement', 'campus recruitment', 'job fair', 'gig economy',
        'freelance', 'contract', 'full time', 'part time', 'workforce'
    ],
}

EXCLUDE_KEYWORDS = [
    'ukraine', 'russia', 'war', 'paint', 'painter', 'painting'
]

def is_topic_related(article, topic_keywords):
    """Check if article is related to the given topic using word boundaries."""
    if not article:
        return False
    
    # If no keywords provided (e.g. general news), return True
    if not topic_keywords:
        return True
    
    title = article.get('title', '').lower()
    description = article.get('summary', '') or article.get('description', '')
    description = description.lower()
    text = title + ' ' + description
    
    # Check if any topic keyword appears with word boundaries
    for keyword in topic_keywords:
        if re.search(r'\b' + re.escape(keyword) + r'\b', text):
            # Check if it's not an excluded keyword
            for exclude in EXCLUDE_KEYWORDS:
                if re.search(r'\b' + re.escape(exclude) + r'\b', text):
                    return False
            return True
    
    return False

def fetch_from_priority_domains(topic_keywords, location=None, limit=8, days=10, topic=None):
    """Fetch from priority domains using parallel fetcher."""
    log(f"Fetching from priority domains (parallel, last {days} days)...")
    
    # Use loaded config
    priority_domains = [
        site['domain'] for site in main_config
        if site.get('priority', 999) <= 6
    ][:20]  # increased limit slightly for better coverage
    
    result = fetch_from_domains_parallel(priority_domains, topic_keywords, location, limit * 3, days=days, topic=topic)
    result = result[:limit]
    
    log(f"Got {len(result)} relevant articles from priority domains")
    
    return result

def fetch_from_nonpriority_fallback(topic_keywords, location=None, limit=8, days=10, topic=None):
    """Fallback to non-priority domains using parallel fetcher."""
    log(f"Priority domains insufficient, fetching from fallback sources (parallel, last {days} days)...")
    
    # Use loaded config
    nonpriority_domains = [
        site['domain'] for site in main_config
        if site.get('priority', 999) > 6
    ][:12]
    
    result = fetch_from_domains_parallel(nonpriority_domains, topic_keywords, location, limit * 3, days=days, topic=topic)
    result = result[:limit]
    
    log(f"Got {len(result)} relevant articles from fallback sources")
    
    return result

def fetch_topic_news(topic, location=None, limit=8, days=10, domain=None):
    """Main function to fetch news for any topic."""
    topic_lower = topic.lower().strip()
    
    # Topic Aliases
    aliases = {
        'technology': 'tech',
        'artificial intelligence': 'ai',
        'genai': 'ai'
    }
    if topic_lower in aliases:
        topic_lower = aliases[topic_lower]
    
    keywords = None
    if topic_lower != 'general':
        # Get keywords for the topic
        if topic_lower not in TOPIC_KEYWORDS:
            available_topics = ', '.join(TOPIC_KEYWORDS.keys())
            log(f"ERROR: Topic '{topic}' not found.")
            log(f"Available topics: {available_topics}, general")
            return []
        
        keywords = TOPIC_KEYWORDS[topic_lower]
        log(f"\nFetching {topic.upper()} news...")
        log(f"Keywords: {', '.join(keywords[:5])}... (+{len(keywords)-5} more)")
    else:
        log(f"\nFetching GENERAL news...")
    
    if location:
        log(f"Location: {location}")
        
    # If specific domain provided, fetch only from there
    if domain:
        log(f"Fetching from specific domain: {domain}")
        result = get_articles(domain, location=location, lastNDays=days, count=limit)
        if result and result.get('articles'):
            return result['articles'][:limit]
        return []
    
    # Try priority domains first
    articles = fetch_from_priority_domains(keywords, location, limit, days, topic=topic_lower)
    
    # If we don't have enough, use fallback
    if len(articles) < limit:
        remaining_needed = limit - len(articles)
        fallback_articles = fetch_from_nonpriority_fallback(keywords, location, remaining_needed, days, topic=topic_lower)
        articles.extend(fallback_articles)
    
    # STRICT: Triple-check limit enforcement
    final_articles = articles[:limit]
    log(f"Returning {len(final_articles)} articles (limit was {limit})")
    return final_articles

def main():
    parser = argparse.ArgumentParser(
        description='Fetch news for any topic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python fetch_topic_news.py --topic cricket --json
  python fetch_topic_news.py --topic "technology" --json
  python fetch_topic_news.py --topic general --location pune
  python fetch_topic_news.py --topic sports

Available topics: {', '.join(TOPIC_KEYWORDS.keys())}, general
        """
    )
    parser.add_argument('--topic', type=str, default='ai',
                       help='Topic to fetch news for (default: ai). Use "general" for no topic filter.')
    parser.add_argument('--location', type=str,
                       help='Location to filter by (e.g. pune, india)')
    parser.add_argument('--domain', type=str,
                       help='Specific domain to fetch from (optional, overrides topic lookup)')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--limit', type=int, default=8,
                       help='Number of articles to fetch (default: 8)')
    parser.add_argument('--days', type=int, default=10,
                       help='Number of days to look back (1-15, default: 10)')
    
    args = parser.parse_args()
    
    # Set quiet mode if JSON output
    global QUIET_MODE
    if args.json:
        QUIET_MODE = True
    
    articles = fetch_topic_news(args.topic, args.location, args.limit, args.days, args.domain)
    
    if args.json:
        print(json.dumps(articles, indent=2, ensure_ascii=False))
    else:
        if not articles:
            print(f"No articles found for topic: {args.topic}" + (f" in {args.location}" if args.location else ""))
        else:
            print(f"\n{'='*80}")
            print(f"TOP {len(articles)} {args.topic.upper()} NEWS" + (f" FROM {args.location.upper()}" if args.location else ""))
            print(f"{'='*80}\n")
            for i, article in enumerate(articles, 1):
                print(f"{i}. {article.get('title', 'No Title')}")
                print(f"   Source: {article.get('source_domain', 'Unknown')}")
                print(f"   {(article.get('summary', '') or article.get('description', 'No description'))[:150]}...")
                print()

if __name__ == '__main__':
    main()
