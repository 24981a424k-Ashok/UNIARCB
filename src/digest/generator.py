from datetime import datetime
import json
import logging
import random
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import VerifiedNews, DailyDigest, RawNews

logger = logging.getLogger(__name__)

class DigestGenerator:
    def __init__(self):
        pass

    async def create_daily_digest(self, session: Session) -> Dict[str, Any]:
        """Generate the comprehensive daily intelligence digest."""
        # 1. Fetch Top 600 Global verified news
        global_news = session.query(VerifiedNews).order_by(VerifiedNews.created_at.desc()).limit(600).all()
        
        # 2. Regional Balanced Fetch: Ensure priority countries have data
        priority_countries = ['in', 'us', 'cn', 'jp', 'gb', 'sg', 'ae', 'ru', 'de', 'fr', 'au']
        regional_news = []
        for code in priority_countries:
            # Fetch top 20 for each country
            country_specific = session.query(VerifiedNews).filter(VerifiedNews.country == code) \
                .order_by(VerifiedNews.created_at.desc()).limit(20).all()
            regional_news.extend(country_specific)
        
        # Merge and deduplicate by ID and Title Similarity
        seen_ids = set()
        seen_titles = set()
        recent_news = []
        for n in global_news + regional_news:
            # Clean title for deduplication
            title_clean = "".join(filter(str.isalnum, (n.title or "").lower()))
            if n.id not in seen_ids and title_clean not in seen_titles:
                recent_news.append(n)
                seen_ids.add(n.id)
                seen_titles.add(title_clean)
        
        logger.info(f"Digest: Fetched {len(recent_news)} articles (Global: {len(global_news)}, Regional: {len(regional_news)}) after deduplication")
        logger.info(f"recent_news count: {len(recent_news)}")
        countries_found = [n.country for n in recent_news if n.country]
        logger.info(f"Countries in recent_news: {set(countries_found)}")
        
        # Generate Breaking News (NEW)
        breaking_news_items = []
        try:
            from src.analysis.breaking_news_analyzer import BreakingNewsAnalyzer
            from src.database.models import BreakingNews
            
            breaking_analyzer = BreakingNewsAnalyzer()
            
            # FIXED: Get most recent news for breaking analysis (last 6 hours only, not 30 days)
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=6)
            fresh_news = session.query(VerifiedNews).filter(
                VerifiedNews.created_at >= cutoff_time
            ).order_by(VerifiedNews.created_at.desc()).limit(100).all()
            
            # Fallback: if last 6h is empty, use last 24h (graceful degradation)
            if not fresh_news:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                fresh_news = session.query(VerifiedNews).filter(
                    VerifiedNews.created_at >= cutoff_time
                ).order_by(VerifiedNews.created_at.desc()).limit(200).all()
            
            if fresh_news:
                articles_to_analyze = []
                for n in fresh_news:
                    articles_to_analyze.append({
                        "id": n.id,
                        "title": n.title,
                        "content": n.content,
                        "source_name": n.raw_news.source_name if n.raw_news else "Unknown",
                        "published_at": n.published_at,
                        "url_to_image": n.raw_news.url_to_image if n.raw_news else None,
                        "url": n.raw_news.url if n.raw_news else "#",
                        "country": n.country
                    })
                
                # breaking_results = await breaking_analyzer.analyze_breaking_batch(articles_to_analyze)
                
                # DIRECT FALLBACK (Bypass LLM for volume)
                breaking_results = []
                breaking_seen_titles = set()  # FIXED: was 'seen_titles' which shadowed outer dedup set
                
                for a in articles_to_analyze:
                    title = a.get("title")
                    if title in breaking_seen_titles:
                        continue
                    breaking_seen_titles.add(title)

                    # Calculate actual recency
                    published_at = a.get("published_at") or datetime.utcnow()
                    recency = int((datetime.utcnow() - published_at).total_seconds() / 60)
                    if recency < 0: recency = 0

                    breaking_results.append({
                        "original_article": a,
                        "classification": "Breaking",
                        "breaking_headline": a.get("title"),
                        "what_happened": [a.get("content")[:200] + "..." if a.get("content") else "No preview available."],
                        "why_matters": "Critical update for immediate release.",
                        "next_updates": ["Developing story."],
                        "confidence_level": "High",
                        "impact_score": 5,
                        "recency_minutes": recency
                    })
                
                # Save to database and prepare for digest
                for result in breaking_results[:150]:  # Up to 150 items
                    original = result.get("original_article", {})
                    news_id = original.get("id")
                    
                    if news_id:
                        # Check if already exists
                        existing = session.query(BreakingNews).filter(
                            BreakingNews.verified_news_id == news_id
                        ).first()
                        
                        if not existing:
                            breaking_entry = BreakingNews(
                                verified_news_id=news_id,
                                classification=result.get("classification"),
                                breaking_headline=result.get("breaking_headline"),
                                what_happened=result.get("what_happened", []),
                                why_matters=result.get("why_matters"),
                                next_updates=result.get("next_updates", []),
                                confidence_level=result.get("confidence_level"),
                                impact_score=result.get("impact_score", 5),
                                recency_minutes=result.get("recency_minutes", 0),
                                url=original.get("url", "#"),
                                image_url=original.get("url_to_image")
                            )
                            session.add(breaking_entry)
                    
                    # Add to digest list
                    breaking_news_items.append({
                        "id": news_id,
                        "classification": result.get("classification"),
                        "headline": result.get("breaking_headline") or original.get("title"),
                        "what_happened": result.get("what_happened", []),
                        "why_matters": result.get("why_matters"),
                        "next_updates": result.get("next_updates", []),
                        "confidence": result.get("confidence_level"),
                        "impact_score": result.get("impact_score", 5),
                        "time_ago": f"{result.get('recency_minutes', 0)} min ago",
                        "url": original.get("url", "#"),
                        "image_url": original.get("url_to_image"),
                        "country": original.get("country") or (original.get("original_article", {}).get("country") if isinstance(original, dict) else None)
                    })
                
                session.commit()
                logger.info(f"Generated {len(breaking_news_items)} breaking news items.")
        except Exception as e:
            logger.error(f"Breaking news generation failed: {e}")
            breaking_news_items = []
        
        if not recent_news:
            logger.info("No news found for digest. Returning empty state.")
            return {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "top_stories": [],
                "twitter_intelligence": [],
                "trending_news": [],
                "brief": [],
                "categories": {},
                "insight": "System Initializing. Collecting global intelligence...",
                "generated_at": datetime.utcnow().isoformat()
            }

        # Ranking logic: Manual articles (score 100) ALWAYS come first.
        def calculate_rank_score(n):
            base_score = n.impact_score or 5
            # Manual articles get a massive boost to stay at the absolute top
            if base_score >= 100:
                return 1000 + base_score 
            
            score = base_score + (n.credibility_score or 0.5) * 2
            if n.published_at:
                age = (datetime.utcnow() - n.published_at).total_seconds() / 3600
                if age < 4: score += 5
            return score

        sorted_news = sorted(recent_news, key=calculate_rank_score, reverse=True)

        # 1. Headlines - Balanced across Categories (Max 4 per category to avoid dominance)
        from collections import defaultdict
        category_buckets = defaultdict(list)
        for n in sorted_news[:150]: # Pool from top 150
            cat = n.category or "General"
            if len(category_buckets[cat]) < 4:
                category_buckets[cat].append(n)
        
        # Flattened balanced pool
        balanced_pool = []
        for cat_list in category_buckets.values():
            balanced_pool.extend(cat_list)
            
        # Sort by impact score again to keep quality high
        balanced_pool = sorted(balanced_pool, key=calculate_rank_score, reverse=True)
        top_10_pool = balanced_pool[:15] # Take top 15 for a rich lead section
        
        # Backfill with original sorted_news if too dry
        if len(top_10_pool) < 10:
             top_10_pool = sorted_news[:10]
        
        # Shuffle slightly for variety
        random.shuffle(top_10_pool)

        # 2. Categories
        mandatory_categories = [
            "Breaking News", "Politics", "Business & Economy", "Sports", 
            "Technology", "AI & Machine Learning", "World News", "India / Local News",
            "Science & Health", "Education", "Entertainment",
            "Environment & Climate", "Lifestyle & Wellness", "Defense & Security"
        ]
        categories = {cat: [] for cat in mandatory_categories}
        countries = {"India": [], "USA": [], "Japan": [], "UK": [], "Singapore": [], "Global": []}

        # 2.A Populate Countries from ALL recent news (not just top 400)
        country_map = {
            "us": "USA", "jp": "Japan", "in": "India", "gb": "UK", 
            "sg": "Singapore", "ru": "Russia", "de": "Germany", 
            "fr": "France"
        }
        
        for n in recent_news:
            country_code = str(n.country).lower().strip() if n.country else None
            if not country_code:
                continue
            
            name = country_map.get(country_code, country_code.capitalize())
            # Debug log
            if country_code in ['in', 'us']:
                logger.info(f"Digest Match Found: {n.title[:30]}... -> Code: {country_code} -> Name: {name}")
            
            item_data = {
                "id": n.id,
                "title": n.title,
                "url": n.raw_news.url if n.raw_news else "#",
                "source_name": n.raw_news.source_name if n.raw_news else "Verified Source",
                "why": n.why_it_matters,
                "affected": n.who_is_affected or "General Industry",
                "tags": n.impact_tags or ["Market"],
                "bias": n.bias_rating or "Neutral",
                "image_url": n.raw_news.url_to_image if n.raw_news else None,
                "bullets": n.summary_bullets or [n.title],
                "country": name
            }
            
            if name not in countries:
                countries[name] = []
            countries[name].append(item_data)
            
            # CRITICAL DEBUG
            if name in ['China', 'UAE']:
                logger.info(f"APPEND SUCCESS: {name} now has {len(countries[name])} stories. Added: {item_data['title'][:30]}")

        # 2.B Populate Categories (Increased pool for better fill)
        for n in sorted_news[:600]:
            cat = n.category or "Breaking News"
            
            item_data = {
                "id": n.id,
                "title": n.title,
                "url": n.raw_news.url if n.raw_news else "#",
                "source_name": n.raw_news.source_name if n.raw_news else "Verified Source",
                "why": n.why_it_matters,
                "affected": n.who_is_affected or "General Industry",
                "tags": n.impact_tags or ["Market"],
                "bias": n.bias_rating or "Neutral",
                "image_url": n.raw_news.url_to_image if n.raw_news else None,
                "bullets": n.summary_bullets or [n.title],
                "country": n.country or "Global"
            }

            # Strict Business Filtering (apply to category only)
            if cat == "Business & Economy":
                text_to_check = ((n.title or "") + " " + (n.raw_news.description or "")).lower()
                business_keywords = [
                    "market", "stock", "economy", "finance", "trade", "bank", "ipo", "startup", 
                    "business", "inflation", "tax", "revenue", "profit", "investment", "shares", 
                    "sensex", "nifty", "gdp", "corporate", "merger", "acquisition", "deal", "funding"
                ]
                if not any(k in text_to_check for k in business_keywords):
                    # If it doesn't look like business, check if it fits Technology or move to General
                    if "tech" in text_to_check or "ai" in text_to_check:
                        cat = "Technology"
                    else:
                        # If it's not business or tech, don't add to a specific category, but still add to country
                        cat = None # Mark as not fitting a specific category for now

            # Add to category
            if cat and cat in categories:
                # Ensure we don't over-fill one category at the expense of others initially
                if len(categories[cat]) < 20:
                    categories[cat].append(item_data)
            
            # Add to Global bucket if no country
            if not n.country:
                countries["Global"].append(item_data)

        # 2.5 Trending in India (New)
        trending_raw = session.query(RawNews).filter(
            (RawNews.source_name.like("%Google News%")) | 
            (RawNews.source_name.like("%Reddit%")) |
            (RawNews.country != None)
        ).order_by(RawNews.published_at.desc()).limit(50).all()

        trending_list = []
        for t in trending_raw:
            trending_list.append({
                "id": t.id,
                "title": t.title,
                "summary": t.description[:200] if t.description else "High momentum news from India.",
                "source_name": t.source_name,
                "engagement": "Trending",
                "time_ago": "Recently",
                "url": t.url,
                "image_url": t.url_to_image,
                "country": t.country
            })

        # 3. Twitter Intelligence
        twitter_news = session.query(VerifiedNews).filter(VerifiedNews.category == "Twitter 𝕏").order_by(VerifiedNews.created_at.desc()).limit(30).all()

        # 4. Premium Business Intelligence — NON-BLOCKING background generation
        # We skip this in the main cycle to avoid stalling the digest for 2-3 minutes.
        # It will be populated from the last cached value or skipped if first run.
        from src.analysis.llm_analyzer import LLMAnalyzer
        import asyncio
        
        premium_intel = []
        # Try to get last cached premium intel from previous digest entry
        try:
            from src.database.models import DailyDigest as _DD
            last_digest = session.query(_DD).filter(
                _DD.content_json.isnot(None)
            ).order_by(_DD.date.desc()).offset(1).first()  # Previous digest
            if last_digest and last_digest.content_json:
                premium_intel = last_digest.content_json.get("premium_intel", [])
                if premium_intel:
                    logger.info(f"Premium Intel: Using cached {len(premium_intel)} items from previous digest.")
        except Exception as e:
            logger.debug(f"Premium intel cache miss: {e}")
        
        # If no cache, generate lightweight fallback without blocking
        if not premium_intel:
            analyzer = LLMAnalyzer()
            business_categories = {
                "Business & Economy", "Technology", "AI & Machine Learning",
                "Science & Health", "India / Local News"
            }
            biz_top = [n for n in sorted_news if n.category in business_categories][:15]
            for n in biz_top:
                try:
                    premium_intel.append({
                        **analyzer._mock_premium_business(n.title),
                        "url": n.raw_news.url if n.raw_news else "#",
                        "image_url": n.raw_news.url_to_image if n.raw_news else None,
                        "source_name": n.raw_news.source_name if n.raw_news else "Source"
                    })
                except Exception:
                    pass


        digest_data = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "breaking_news": breaking_news_items,  # NEW: Top 20 breaking news
            "premium_intel": premium_intel,
            "top_stories": [
                {
                    "id": n.id,
                    "title": n.title,
                    "url": n.raw_news.url if n.raw_news else "#",
                    "source_name": n.raw_news.source_name if n.raw_news else "Source",
                    "image_url": n.raw_news.url_to_image if n.raw_news else None,
                    "bullets": n.summary_bullets or [n.title],
                    "why": n.why_it_matters or "Critical update.",
                    "affected": n.who_is_affected or "Industry Stakeholders",
                    "short_impact": n.short_term_impact or "Immediate awareness.",
                    "long_impact": n.long_term_impact or "Strategic shifts.",
                    "tags": n.impact_tags or ["Intelligence"],
                    "bias": n.bias_rating or "Neutral",
                    "category": n.category
                } for n in top_10_pool[:30]  # Increased to 30 for See More
            ],
            "twitter_intelligence": [
                {
                    "id": n.id,
                    "author": (n.raw_news.author if n.raw_news and n.raw_news.author else "X User").replace("@", ""),
                    "text": n.title,
                    "url": n.raw_news.url if n.raw_news else "https://twitter.com",
                    "image": n.raw_news.url_to_image if n.raw_news else None,
                    "engagement": "High Momentum"
                } for n in twitter_news
            ],
            "trending_news": trending_list[:15],  # Increased to 15
            "brief": [], # Will populate below
            "categories": categories,
            "countries": countries,
            "insight": "Intelligence analysis complete. Major shifts detected in tech and policy sectors.",
            "generated_at": datetime.utcnow().isoformat()
        }

        # Ensure 60-second brief is ALWAYS populated with enough for filtering
        # 1. Start with Top 25 Ranked (Global/High Impact)
        brief_items = [{"id": n.id, "title": n.title, "country": n.country} for n in sorted_news[:25]]
        
        # 2. Add snippets from each country node to ensure filtering works
        for country_name, stories in countries.items():
            if country_name == "Global": continue
            # Add top 5 from each country if not already in brief
            for s in stories[:5]:
                if s["id"] not in [b["id"] for b in brief_items]:
                    brief_items.append({"id": s["id"], "title": s["title"], "country": s.get("country")})

        if len(brief_items) < 100:
            # Fallback to Top Sorted if still dry
            for n in sorted_news[25:100]:
                if n.id not in [b["id"] for b in brief_items]:
                    brief_items.append({"id": n.id, "title": n.title, "country": n.country})

        # Fallback to RawNews if verified is dry
        if len(brief_items) < 100:
            extra_raw = session.query(RawNews).order_by(RawNews.published_at.desc()).limit(100 - len(brief_items)).all()
            for r in extra_raw:
                brief_items.append({"id": f"raw-{r.id}", "title": r.title + " (Raw Feed)", "country": r.country})
        
        digest_data["brief"] = brief_items

        # FINAL DEBUG
        f_countries = digest_data.get("countries", {})
        logger.info(f"FINAL DIGEST STATE: China={len(f_countries.get('China', []))}, UAE={len(f_countries.get('UAE', []))}")

        # UPSERT: Update today's digest instead of always creating a new one
        # This prevents 96 new rows/day accumulation
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing_digest = session.query(DailyDigest).filter(
            DailyDigest.date >= today_start
        ).first()
        
        if existing_digest:
            existing_digest.content_json = digest_data
            existing_digest.is_published = True
            existing_digest.date = datetime.utcnow()
            logger.info("Digest: Upserted existing today's digest.")
        else:
            digest_entry = DailyDigest(
                date=datetime.utcnow(),
                content_json=digest_data,
                is_published=True
            )
            session.add(digest_entry)
            logger.info("Digest: Created new digest entry for today.")
        
        session.commit()
        logger.info(f"Digest complete: {len(digest_data.get('top_stories', []))} stories, {len(digest_data.get('breaking_news', []))} breaking.")
        
        return digest_data

