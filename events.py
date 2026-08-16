import feedparser
from google import genai

# ---------------------------------------------------------------------------
# RSS Feed library — organized by category for easy expansion.
# To add a new source: just append its RSS URL to the right category list.
# To add a new category: create a new key and add URLs under it.
# ---------------------------------------------------------------------------

RSS_FEEDS_BY_CATEGORY = {

    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.skysports.com/rss/12040",
        "https://sports.yahoo.com/rss/",
        "https://www.espn.com/espn/rss/news",
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
        "https://api.foxsports.com/v1/rss",
    ],

    "world_news": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.cnn.com/rss/edition.rss",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://feeds.reuters.com/reuters/worldNews",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.theguardian.com/theguardian/world/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],

    "business_finance": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/companyNews",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    ],

    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.wired.com/wired/index",
        "https://arstechnica.com/feed/",
        "https://www.engadget.com/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],

    "entertainment_culture": [
        "https://variety.com/feed/",
        "https://www.rollingstone.com/feed/",
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
        "https://feeds.skynews.com/feeds/rss/entertainment.xml",
        "https://deadline.com/feed/",
    ],

    "health_science": [
        "https://feeds.bbci.co.uk/news/health/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://feeds.reuters.com/reuters/healthNews",
        "https://www.sciencedaily.com/rss/all.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    ],

    "lifestyle_trends": [
        "https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Travel.xml",
        "https://www.theguardian.com/lifeandstyle/rss",
        "https://feeds.reuters.com/reuters/lifestyle",
    ],

}

# Flat list for easy iteration — derived automatically from the dict above
ALL_RSS_FEEDS = [url for urls in RSS_FEEDS_BY_CATEGORY.values() for url in urls]


# ---------------------------------------------------------------------------
# Headline fetcher
# ---------------------------------------------------------------------------

def get_all_headlines(max_per_feed=4, max_total=60):
    """
    Pulls headlines from every feed in RSS_FEEDS_BY_CATEGORY.
    Returns a list of dicts: {title, category} so Gemini knows
    what domain each headline comes from.
    max_per_feed: how many entries to take from each individual feed
    max_total: hard cap on total headlines sent to Gemini
    """
    headlines = []

    for category, feed_urls in RSS_FEEDS_BY_CATEGORY.items():
        for feed_url in feed_urls:
            if len(headlines) >= max_total:
                break
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:max_per_feed]:
                    if hasattr(entry, "title") and entry.title.strip():
                        headlines.append({
                            "title": entry.title.strip(),
                            "category": category
                        })
            except Exception as e:
                print(f"[events] Skipped feed {feed_url}: {e}")
                continue

    print(f"[events] Fetched {len(headlines)} headlines from {len(ALL_RSS_FEEDS)} feeds")
    return headlines[:max_total]


# ---------------------------------------------------------------------------
# Event picker — context-aware with general fallback
# ---------------------------------------------------------------------------

def pick_best_event(company_name, company_details, client):
    """
    Selects the best current event to tie the ad to.

    Priority order:
    1. An event directly relevant to the company's industry, audience,
       or brand — makes the ad feel timely AND targeted
    2. If nothing relevant exists, the single most impactful/exciting
       trending event globally — ensures the ad still feels current

    Args:
        company_name:    str — company name
        company_details: dict — full company data from scraper
                         (what_they_do, services, brand_tone,
                          target_audience, key_values, tagline)
        client:          Gemini client instance

    Returns:
        str — one-sentence event context for the ad writer
    """
    from generator import call_counter

    headlines = get_all_headlines()

    if not headlines:
        print("[events] No headlines fetched — using generic fallback")
        return "current global events and cultural moments"

    # Build company context string from whatever details are available
    what_they_do    = company_details.get("what_they_do", "")
    services        = company_details.get("services", "")
    brand_tone      = company_details.get("brand_tone", "")
    target_audience = company_details.get("target_audience", "")
    key_values      = company_details.get("key_values", "")
    tagline         = company_details.get("tagline", "")

    company_context_block = f"""Company: {company_name}
What they do: {what_they_do}
Services / products: {services}
Brand tone: {brand_tone}
Target audience: {target_audience}
Key values: {key_values}
Tagline: {tagline}"""

    # Format headlines with category labels so Gemini can reason about relevance
    headlines_block = "\n".join(
        [f"[{h['category'].upper()}] {h['title']}" for h in headlines]
    )

    prompt = f"""You are a senior advertising strategist specializing in real-time cultural marketing.

Your task is to choose the single best current news event to tie a {company_name} ad campaign to.

---
COMPANY CONTEXT:
{company_context_block}

---
CURRENT HEADLINES (categorized by topic):
{headlines_block}

---
YOUR DECISION PROCESS:

STEP 1 — RELEVANCE SCAN:
Look for any headline that connects naturally to this company's industry, 
target audience, brand values, or what they do. 
A connection can be direct (a finance company + stock market news), 
aspirational (a sportswear brand + a major sports championship), 
or cultural (a youth brand + a major pop culture moment).

STEP 2 — QUALITY FILTER:
Prefer big, exciting, emotionally resonant events — championships, record-breaking moments,
major product launches, cultural milestones, global competitions, historic firsts.
Avoid minor or niche news unless it is extremely relevant to the company.

STEP 3 — DECISION:
- If you found a relevant, high-quality event: use it.
- If nothing connects well to this company, or the best available headlines are too niche or negative:
  fall back to the single most trending, exciting, universally appealing headline regardless of industry fit.

STEP 4 — OUTPUT:
Write ONE sentence describing the chosen event as context for an ad copywriter.
The sentence should capture what the event IS and why it is culturally exciting right now.

Format: "[RELEVANT] Your sentence here." if you found a company-relevant event
Format: "[TRENDING] Your sentence here." if you used the general fallback

Examples of good output:
"[RELEVANT] The FIFA Club World Cup is underway, captivating global football fans with top clubs competing for the world title."
"[TRENDING] The 2026 World Athletics Championships is breaking viewership records as sprinters chase historic times on the global stage."

Respond with ONLY that one labelled sentence. Nothing else."""

    call_counter["count"] += 1
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    result = response.text.strip()

    # Strip the label prefix for the ad generator — it's only used for our logging
    if result.startswith("[RELEVANT]"):
        print(f"[events] Context-matched event found")
        return result.replace("[RELEVANT]", "").strip()
    elif result.startswith("[TRENDING]"):
        print(f"[events] No relevant match — using trending fallback")
        return result.replace("[TRENDING]", "").strip()
    else:
        # Gemini didn't follow format — use as-is, still valid event context
        return result