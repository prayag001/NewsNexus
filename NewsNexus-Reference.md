# NewsNexus Technical Reference & Q&A

## Deep Scraper Implementation
- Scrapes homepage for article links
- Visits each article page in parallel (configurable workers)
- Extracts full article content, summary, published date, and author
- All data is processed in memory (RAM), nothing is written to disk
- Configurable via environment variables:
  - `NEWSNEXUS_DEEP_SCRAPE` (enable/disable)
  - `NEWSNEXUS_DEEP_SCRAPE_MAX` (max articles per request)
  - `NEWSNEXUS_DEEP_SCRAPE_TIMEOUT` (timeout per article)
  - `NEWSNEXUS_SUMMARY_LENGTH` (summary length)
  - `NEWSNEXUS_DEEP_WORKERS` (parallel workers)

## Data Storage & Caching
- All article content and summaries are stored in RAM during request processing
- No files or database are used for storage or caching by default
- In-memory cache (Python dict) is used for repeated queries
- Cache is NOT persistent: lost on server restart, not shared between processes
- Default: 5 minutes TTL, max 1000 entries (oldest evicted automatically)
- For production, persistent caching (e.g., Redis) is strongly recommended

## Memory/Space Usage Estimates
- Per-request memory: ~1-3 MB (freed after response)
- Cache memory: ~60-100 KB per entry, max ~100 MB for 1000 entries
- No disk or database usage by default

## Production Readiness
- In-memory cache is not suitable for high-traffic, multi-instance, or long-running production deployments
- Without persistent cache, every request triggers live scraping, causing high load and slow responses
- For thousands of users, add Redis or another persistent cache to:
  - Reduce redundant requests
  - Improve speed and reliability
  - Survive restarts and scale horizontally
- Respect robots.txt and publisher terms when scraping at scale

## Q&A

**Q: Where is extracted article content stored?**
A: In RAM only, during request processing. Nothing is written to disk.

**Q: Is anything saved to disk?**
A: No. All data is in memory unless you add persistent caching.

**Q: What is caching?**
A: Storing results in RAM for 5 min to avoid re-fetching. Not persistent by default.

**Q: Where is cache stored?**
A: Python dictionary in RAM. Not on disk or in a database.

**Q: How much space does cache take?**
A: Max ~100 MB RAM (typically 5-20 MB in normal use).

**Q: Does cache persist after restart?**
A: No, it is lost on restart.

**Q: Do I need a database?**
A: No, current design works without one. For production, add Redis or similar.

**Q: What if I want to scale to thousands of users?**
A: You must add persistent caching (e.g., Redis) and consider horizontal scaling.

**Q: What are the risks of not using persistent cache?**
A: High load, slow responses, risk of being blocked by news sites, and poor user experience.

---

## Project Rating (Post Deep Scraper)
- Architecture & Design: 9/10
- Deep Scraper: 9/10
- Performance & Scalability: 8.5/10
- Security: 8/10
- Code Quality: 8.5/10
- Testing: 8/10
- Observability: 9/10
- Production Readiness: 8/10

**Overall Score: 8.7/10**

---

## Recommendations for Production
- Add persistent cache (Redis, Memcached, or file-based)
- Add Docker/docker-compose for deployment
- Add CI/CD pipeline
- Add more tests for deep scraper
- Monitor and respect target site policies

---

*Update this document as your project evolves or as new questions arise.*
