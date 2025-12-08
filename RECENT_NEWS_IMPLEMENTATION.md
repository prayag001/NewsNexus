# NewsNexus Recent News Implementation

## Summary of Changes (December 8, 2025)

### 🎯 **Core Requirements Implemented:**

1. **15-Day Hard Cap for "Recent" News**
   - Maximum age: 15 days (MAX_RECENT_DAYS constant)
   - Articles older than 15 days are NOT returned for "recent" queries
   - User can still override with explicit parameters

2. **Default Article Count: 10**
   - When user says "recent/top/latest" without specifying a number
   - Default: 10 articles (DEFAULT_ARTICLE_COUNT)
   - Explicit number (e.g., "15 recent news") overrides default

3. **Reverse Chronological Order**
   - Articles sorted newest-first (like RSS feeds)
   - Most recent article appears at position #1

4. **Smart Multi-Priority Fallback**
   - Tries all 4 priorities (official RSS → RSSHub → Google News → Scraper)
   - Continues to next priority if current has < 5 articles (MIN_ARTICLES_THRESHOLD)
   - Returns best available result after trying all sources

5. **User-Friendly Messaging**
   - Clear explanation when no articles found
   - Message when fewer articles returned than requested
   - Lists which sources were tried

---

## 📋 **Configuration Constants**

```python
MAX_RECENT_DAYS = 15           # Hard cap for "recent" news
DEFAULT_ARTICLE_COUNT = 10     # Default when user doesn't specify count
MIN_ARTICLES_THRESHOLD = 5     # Minimum before trying next priority
```

---

## 🔄 **Workflow Examples**

### Example 1: Sufficient Articles from Priority 1
```
User: "Fetch 10 recent news from TechCrunch"
1. Try Official RSS → 50 articles found → Filter by 15 days → 25 recent
2. 25 > MIN_THRESHOLD (5) → Return top 10 (newest first)
✅ Returns 10 articles from official RSS
```

### Example 2: Insufficient from Priority 1, Try Next
```
User: "Fetch 10 recent news from MoneyControl"
1. Try Official RSS → 403 Forbidden ❌
2. Try RSSHub → No URL configured ❌
3. Try Google News → 1 article found (< 5 threshold)
4. Save as fallback, continue...
5. Try Scraper → 403 Forbidden ❌
6. Return fallback (Google News with 1 article)
📢 Message: "Found 1 articles (requested 10) from last 15 days"
```

### Example 3: No Recent Articles
```
User: "Fetch recent news from OldSite"
1-4. Try all priorities → All articles are 60+ days old
5. Filter by 15 days → 0 articles
❌ Returns empty with message:
"No articles found from oldsite.com in the last 15 days.
Tried all available sources. This site may not have published recent content."
```

---

## 🛠️ **API Changes**

### `get_articles()` Function
**Before:**
```python
def get_articles(domain, topic=None, location=None, lastNDays=None, fast_mode=False)
# No count parameter, no defaults, no caps
```

**After:**
```python
def get_articles(domain, topic=None, location=None, lastNDays=None, 
                fast_mode=False, count=None)
# Added count parameter
# lastNDays defaults to 15 (capped at 15 max)
# count defaults to 10
# Returns articles in reverse chronological order
# Includes user-friendly messages
```

### `get_top_news()` Function
**Before:**
```python
def get_top_news(count=8, topic=None, location=None, lastNDays=None)
# Default count was 8
```

**After:**
```python
def get_top_news(count=None, topic=None, location=None, lastNDays=None)
# Default count is 10
# lastNDays defaults to 15, capped at 15
```

---

## 📊 **MCP Tool Definitions Updated**

### `get_articles` Tool
```json
{
  "name": "get_articles",
  "description": "Retrieve RECENT articles from a domain (max 15 days old). 
                 Returns newest first. Default: 10 articles from last 15 days.",
  "parameters": {
    "domain": "required",
    "count": "optional, default 10, max 50",
    "lastNDays": "optional, default 15, max 15 for recent news",
    "topic": "optional filter",
    "location": "optional filter",
    "fast_mode": "optional, skip to Google News"
  }
}
```

---

## ✅ **Test Results**

### Test 1: MoneyControl (Limited Recent Content)
```
Command: python fetch_moneycontrol.py
Result: 1 article from Google News
Message: "Found 1 articles (requested 10) from last 15 days. 
          This is all the recent content available."
Sources Tried: Official RSS (403), RSSHub (no URL), Google News (✓), Scraper (403)
✅ PASS: Tries all priorities, returns best available with helpful message
```

### Test 2: NDTV (Some Recent Articles)
```
Command: python test_no_results.py (1 day filter)
Result: 2 articles from Google News
Message: "Found 2 articles (requested 10) from last 1 days."
✅ PASS: Respects custom day filter, tries all sources
```

### Test 3: Default Settings
```
Command: python test_defaults.py
Result: Uses 15-day default, 10-article default
✅ PASS: Defaults applied correctly
```

---

## 🎯 **Key Behaviors**

| Scenario | Behavior |
|----------|----------|
| User says "recent news" | Fetch 10 articles, max 15 days old |
| User says "15 recent news" | Fetch 15 articles, max 15 days old |
| User says "news from last 2 days" | Fetch 10 articles, max 2 days old (capped at 15) |
| Priority 1 has 3 articles | Try priorities 2, 3, 4 (threshold = 5) |
| No articles in 15 days | Return empty with explanation |
| Articles found | Sort newest-first, limit to count |

---

## 🚀 **User Experience Improvements**

1. **Predictable Defaults**: Always 10 articles, 15 days for "recent"
2. **Clear Messaging**: Users know why they got fewer articles
3. **Exhaustive Search**: Tries all sources before giving up
4. **Freshness Guarantee**: "Recent" truly means recent (≤ 15 days)
5. **Sorted Results**: Newest articles always appear first

---

## 📝 **Future Considerations**

- Consider adding a `--days-cap-override` flag for power users who need > 15 days
- Add article age warnings (e.g., "⚠️ Oldest article is 14 days old")
- Implement adaptive threshold (try more sources if count high, e.g., requesting 50 articles)
- Add source quality metrics to prefer faster/more reliable sources

---

## 🔧 **Files Modified**

1. `main.py`:
   - Added MAX_RECENT_DAYS, DEFAULT_ARTICLE_COUNT, MIN_ARTICLES_THRESHOLD
   - Updated `get_articles()` with count parameter and date capping
   - Updated `get_top_news()` with new defaults
   - Added user-friendly messaging
   - Added reverse chronological sorting
   - Updated MCP tool definitions

2. `fetch_moneycontrol.py`:
   - Added message display for user feedback

3. Created test files:
   - `test_defaults.py`
   - `test_no_results.py`
   - `test_moneycontrol_2days.py`

---

**Implementation Complete! ✅**
All requirements successfully implemented and tested.
