# Topic-Based News Filtering Guide

## Overview

You can now fetch news by specific topics like **mobile**, **laptop**, **AI**, **tech**, and many more. The system uses intelligent keyword matching to find relevant articles.

## Available Topics

### **Technology & Gadgets**
- `mobile` - Smartphones, Android, iOS, Samsung, iPhone, etc.
- `laptop` - Notebooks, MacBook, gaming laptops, Chromebook, etc.
- `tech` - General technology news
- `ai` - Artificial Intelligence, ML, GPT, ChatGPT, etc.

### **Other Topics**
- `cricket` - Cricket news, IPL, matches, players
- `finance` - Stock market, banking, investment
- `sports` - General sports news
- `politics` - Political news, elections, government
- `health` - Medical, wellness, fitness
- `entertainment` - Movies, music, celebrities
- `education` - Schools, exams, courses
- `crypto` - Bitcoin, Ethereum, blockchain
- `startup` - Startup funding, unicorns, VC
- `gaming` - Video games, esports, consoles
- `auto` - Cars, EVs, Tesla, bikes
- `travel` - Tourism, flights, hotels
- `weather` - Weather forecasts, climate
- `realestate` - Property, housing
- `jobs` - Employment, hiring, careers

## Usage Examples

### **Mobile News**

```python
# Basic mobile news
get_top_news(count=8, topic="mobile")

# High-quality mobile news only
get_top_news(count=8, topic="mobile", min_quality_score=40)

# Specific mobile brands
get_top_news(count=5, topic="iphone")
get_top_news(count=5, topic="samsung")
get_top_news(count=5, topic="android")
```

**What it matches:**
- "Samsung Galaxy S24 launched with AI features"
- "iPhone 16 Pro review: Best camera yet"
- "OnePlus 12 gets Android 15 update"
- "Xiaomi announces budget 5G phone at ₹15,000"

### **Laptop News**

```python
# Basic laptop news
get_top_news(count=8, topic="laptop")

# Gaming laptop news
get_top_news(count=5, topic="gaming laptop")

# Specific laptop brands
get_top_news(count=5, topic="macbook")
get_top_news(count=5, topic="dell")
get_top_news(count=5, topic="thinkpad")
```

**What it matches:**
- "Dell XPS 15 review: Premium ultrabook"
- "MacBook Pro M3 announced with 20% faster performance"
- "ASUS ROG gaming laptop with RTX 4090 launched"
- "Lenovo ThinkPad X1 Carbon gets Intel Core Ultra"

### **AI News**

```python
# High-quality AI news
get_top_news(count=8, topic="ai", min_quality_score=45)

# Specific AI topics
get_top_news(count=5, topic="chatgpt")
get_top_news(count=5, topic="gemini")
```

**What it matches:**
- "OpenAI launches GPT-5 with breakthrough reasoning"
- "Google Gemini 2.0 achieves 95% on coding benchmarks"
- "Microsoft Copilot Pro adds advanced AI features"

### **Combined Filters**

```python
# Mobile news from India
get_top_news(count=8, topic="mobile", location="india")

# Recent laptop launches (last 3 days)
get_top_news(count=8, topic="laptop", lastNDays=3)

# High-quality tech news
get_top_news(count=10, topic="tech", min_quality_score=40)
```

## How Topic Matching Works

The system uses **keyword expansion** to find relevant articles:

### **Mobile Topic Keywords**
When you search for `topic="mobile"`, it matches articles containing:
- mobile, smartphone, phone
- android, ios, iphone, samsung, pixel
- oneplus, xiaomi, oppo, vivo, realme
- 5g phone, flagship phone, budget phone
- mobile camera, mobile processor, snapdragon
- mobile launch, mobile review, mobile specs
- And 30+ more mobile-related keywords

### **Laptop Topic Keywords**
When you search for `topic="laptop"`, it matches articles containing:
- laptop, notebook, ultrabook, macbook
- chromebook, gaming laptop, business laptop
- dell, hp, lenovo, asus, acer, msi
- laptop processor, intel, amd, ryzen
- laptop gpu, nvidia, rtx, gtx
- laptop review, laptop launch, laptop deal
- And 30+ more laptop-related keywords

## Quality Filtering with Topics

Combine topic filtering with quality filtering for best results:

```python
# Get only high-quality mobile news
get_top_news(count=8, topic="mobile", min_quality_score=40)
```

**This will:**
1. Fetch articles from 20 priority sites
2. Filter for mobile-related keywords
3. Score each article for quality (0-100)
4. Remove low-quality/vague articles (score < 40)
5. Return top 8 high-quality mobile news articles

## Response Format

```json
{
  "articles": [
    {
      "heading": "Samsung Galaxy S24 Ultra launched with AI features",
      "summary": "Samsung announced the Galaxy S24 Ultra today with...",
      "date": "2025-12-26T18:00:00Z",
      "source_link": "https://...",
      "quality_score": 75.5
    }
  ],
  "total": 8,
  "durationMs": 4532.12,
  "qualityFilterEnabled": true,
  "minQualityScore": 35.0,
  "filteredOut": 23
}
```

## Tips for Best Results

### ✅ **Do's**
- Use specific topics: `"mobile"`, `"laptop"`, `"ai"`
- Combine with quality filtering for better results
- Use brand names for specific news: `"iphone"`, `"macbook"`
- Adjust `min_quality_score` based on your needs (30-50)

### ❌ **Don'ts**
- Don't use very generic terms (already covered by default)
- Don't set quality score too high (>50) - may get fewer results
- Don't use multiple topics in one request (use separate calls)

## Examples of Good Queries

```python
# 1. Latest mobile launches
get_top_news(count=8, topic="mobile", lastNDays=7)

# 2. Premium laptop news only
get_top_news(count=5, topic="laptop", min_quality_score=45)

# 3. AI news from last 3 days
get_top_news(count=10, topic="ai", lastNDays=3)

# 4. Gaming laptop deals
get_top_news(count=5, topic="gaming laptop")

# 5. iPhone news
get_top_news(count=5, topic="iphone", min_quality_score=40)

# 6. Budget phone news
get_top_news(count=8, topic="budget phone")

# 7. MacBook reviews
get_top_news(count=5, topic="macbook review")
```

## Performance

Topic filtering is **very fast** because:
- Keyword matching happens in-memory
- No additional API calls needed
- Works with existing quality filtering
- Same 3-8 second response time

## Summary

✅ **Yes, you can fetch mobile and laptop news!**
✅ Use `topic="mobile"` or `topic="laptop"`
✅ Combine with quality filtering for best results
✅ 30+ keywords per topic for comprehensive matching
✅ Works with all 20 priority sites
✅ Fast and efficient filtering

Try it now:
```python
get_top_news(count=8, topic="mobile", min_quality_score=35)
```
