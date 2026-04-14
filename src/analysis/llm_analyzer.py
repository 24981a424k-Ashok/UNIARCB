import os
import json
from loguru import logger
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import openai
from src.config import settings
from src.config.settings import OPENAI_API_KEY, GROQ_API_KEY, TRANSLATION_KEYS, GROQ_API_KEYS

# logger = logging.getLogger(__name__) # Removed standard logging

class LLMAnalyzer:
    def __init__(self):
        # 1. Gather unique non-empty keys from settings pools
        self.openai_keys = list(dict.fromkeys([k for k in settings.OPENAI_API_KEYS if k]))
        self.groq_keys = list(dict.fromkeys([k for k in settings.GROQ_API_KEYS if k]))
        
        if not self.openai_keys and not self.groq_keys:
            logger.warning("All LLM API Keys missing! LLM analysis will be skipped/mocked.")
            self.client = None
            self.semaphore = asyncio.Semaphore(1) 
        else:
            logger.info(f"LLMAnalyzer initialized with {len(self.openai_keys)} OpenAI keys and {len(self.groq_keys)} Groq keys for rotation.")
            # Restored managed parallelization to avoid saturation
            self.semaphore = asyncio.Semaphore(20)


    def _get_openai_client(self, index=0):
        """Get an OpenAI client for a specific key in the pool."""
        if not self.openai_keys: return None
        key = self.openai_keys[index % len(self.openai_keys)]
        return openai.OpenAI(api_key=key)

    async def _get_async_client(self, provider="openai", index=0):
        """Get an Async OpenAI/Groq client for rotation."""
        from openai import AsyncOpenAI
        if provider == "openai" and self.openai_keys:
            key = self.openai_keys[index % len(self.openai_keys)]
            return AsyncOpenAI(api_key=key)
        elif provider == "groq" and self.groq_keys:
            key = self.groq_keys[index % len(self.groq_keys)]
            return AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        return None

    async def analyze_batch(self, articles: List[Dict[str, str]], is_sports: bool = False) -> List[Dict[str, Any]]:
        """
        Ultra-High Performance Batch Analysis.
        Distributes articles across ALL available keys in parallel for maximum speed.
        """
        if not articles: return []
        
        # Semaphore is now managed at the class level for stability
        
        # Launch all articles as independent tasks that manage their own rotation
        tasks = [self._analyze_single_robust(a, i, is_sports) for i, a in enumerate(articles)]
        results = await asyncio.gather(*tasks)
        return results

    async def _analyze_single_robust(self, article: Dict[str, str], index: int, is_sports: bool) -> Dict[str, Any]:
        """Analyzes a single article with local retry/rotation across the entire key pool."""
        async with self.semaphore:
            # Selection pool: OpenAI first, then Groq
            providers = []
            if self.openai_keys: providers.append("openai")
            if self.groq_keys: providers.append("groq")
            
            if not providers:
                return self._mock_analysis(article["title"])

            # Try twice (once per provider pool if needed)
            for provider in providers:
                keys = self.openai_keys if provider == "openai" else self.groq_keys
                # Offset starting key by article index for maximum parallel distribution
                for attempt in range(len(keys)):
                    key_index = (index + attempt) % len(keys)
                    client = await self._get_async_client(provider, key_index)
                    
                    try:
                        if is_sports:
                            res = await self._analyze_sports_single(article, client)
                        else:
                            res = await self._analyze_single(article, client)
                        await client.close()
                        return res
                    except Exception as e:
                        try:
                            await client.close()
                        except:
                            pass
                        error_msg = str(e).lower()
                        if "quota" in error_msg or "429" in error_msg:
                            logger.warning(f"Key rotation: {provider} key #{key_index+1} rate-limited. Trying next...")
                            continue # Individual task tries next key
                        logger.error(f"Analysis failed for '{article['title']}' on {provider} key #{key_index+1}: {e}")
                        break # Critical error, switch provider or mock
            
            return self._mock_analysis(article["title"])

    async def _analyze_sports_single(self, article: Dict[str, str], client, model: str = None) -> Dict[str, Any]:
        """Specialized Sports News Editor AI analysis with Smart Fallback."""
        title = article.get("title", "")
        content = article.get("content", "")
        source = article.get("source_name", "Unknown")
        timestamp = article.get("published_at", "Unknown")

        # Dynamic model selection with fallback
        if not model:
            if "groq.com" in str(client.base_url):
                model = "llama-3.1-70b-versatile"
            else:
                model = "gpt-4o-mini" # Preferred

        prompt = f"""
You are a Sports News Editor AI for a professional news platform.

Your task is to identify, classify, and structure news that strictly belongs
to the Sports category.

────────────────────────────
INPUT
────────────────────────────
Article Title: {title}
Article Content: {content[:3000]}
Source: {source}
Published Time (UTC): {timestamp}
... (Instructions truncated for brevity) ...
""" # Prompt continues below
        try:
            # We recreate the prompt with full text here to ensure formatting matches
            full_prompt = f"""
You are a Sports News Editor AI for a professional news platform.

Your task is to identify, classify, and structure news that strictly belongs
to the Sports category.

────────────────────────────
INPUT
────────────────────────────
Article Title: {title}
Article Content: {content[:3000]}
Source: {source}
Published Time (UTC): {timestamp}

────────────────────────────
SPORTS CLASSIFICATION RULES
────────────────────────────
Classify the news as "Sports" ONLY if it directly relates to:
- Matches, tournaments, or competitions
- Athletes or teams (performance, selection, injuries)
- Sports events, schedules, or results
- Transfers, auctions, contracts, or signings
- Coaching or management decisions
- Sports rules, governance, or disciplinary actions

Do NOT classify as Sports if the article is:
- Celebrity gossip or personal life
- General politics or entertainment
- Social media drama without sports relevance

────────────────────────────
TASKS
────────────────────────────

A) CATEGORY VALIDATION
- Decide if this article belongs to the Sports section
- If not, clearly mark: "Not Sports News"

B) SPORTS NEWS TYPE (if Sports)
Classify into ONE of the following:
- Match Result / Live Update
- Tournament / Event News
- Player Performance / Records
- Team & Squad News
- Transfer / Auction / Contract
- Injury / Fitness Update
- Coaching / Management Change
- Sports Governance / Rules
- Sports Business (sponsorship, broadcasting)

C) URGENCY TAG
Assign ONE tag:
- Breaking Sports News (only for rare, urgent events)
- Top Sports Headline
- Regular Sports Update

D) STRUCTURED OUTPUT
Generate JSON with:
1. classification_status: "Sports" | "Not Sports News"
2. sports_type: String
3. headline: String (factual, neutral)
4. key_facts: List of 2–4 bullet points
5. why_it_matters: String (Detailed analysis of impact on team, player, tournament, or fans. Provide exactly 3-4 professional lines.)
6. who_is_affected: String (Specific athletes, teams, or fans impacted with detailed reasoning. Provide exactly 3-4 professional lines.)
7. next_update: String (label uncertainty clearly)
8. urgency_tag: String (from rules above)
9. category: "Sports" (if sports)
10. impact_score: 1-10
11. primary_geography: "India" | "Japan" | "China" | "USA" | "UK" | "Global"

IMPORTANT: Output ONLY valid JSON.
"""
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional Sports News Editor AI. Output ONLY JSON."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.2,
                timeout=60.0
            )
            raw_content = response.choices[0].message.content
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            
            result = json.loads(raw_content)
            
            # Map back to standard fields for UI compatibility
            if result.get("classification_status") == "Sports":
                result["summary_bullets"] = result.get("key_facts", [])
                result["why_it_matters"] = f"Sports Type: {result.get('sports_type')}\n\n{result.get('why_it_matters')}"
                result["who_is_affected"] = result.get("who_is_affected", f"Next Update: {result.get('next_update', 'TBD')}")
                result["impact_tags"] = [result.get("urgency_tag", "Regular Update")]
                result["category"] = "Sports"
                result["country"] = result.get("primary_geography", "Global")
            
            return result
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                raise e
            logger.error(f"Sports analysis failed for '{title}': {e}")
            return self._mock_analysis(title)


    async def _analyze_single(self, article: Dict[str, str], client, model: str = "gpt-4o-mini") -> Dict[str, Any]:
        title = article["title"]
        content = article.get("content", "")
        
        # Adjust model for Groq if detected
        if "groq.com" in str(client.base_url):
             model = "llama-3.1-70b-versatile"

        prompt = f"""
        Analyze the following news article:
        Title: {title}
        Content: {content[:3000]}

        TASK:
        Generate a JSON output with:
        PART 1: INDUSTRY INTELLIGENCE REPORT
        - regulatory_changes, market_impact_short, market_impact_long, competitors, strategic_signals, recommendations, confidence_level.
        - who_is_affected_details: String (Provide exactly 3-4 insightful lines about who is impacted).
        - why_it_matters_details: String (Provide exactly 3-4 insightful lines about the strategic significance).
        
        PART 2: DASHBOARD METADATA
        - category, impact_score (1-10), sentiment, summary_bullets (5-7 points), bias_rating, primary_geography (e.g. India, USA, China, Japan, Global).
        
        LANGUAGE REQUIREMENT:
        - Detect the language of the article content (e.g. Japanese, Chinese, Arabic).
        - IMPORTANT: If the article is NOT in English, you MUST provide 'headline', 'summary_bullets', 'why_it_matters', and 'who_is_affected_details' in BOTH the native language AND English.
        - Format for non-English: "English Title (Native Title)" or "English Bullet Point (Native Bullet)".
        
        Output ONLY valid JSON.
        """
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional industry analyst. Output ONLY JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                timeout=60.0
            )
            raw_content = response.choices[0].message.content
            
            # Clean up markdown if present
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].strip()
            else:
                raw_content = raw_content.strip()
            
            result = json.loads(raw_content)
            
            # Ensure mandatory fields for UI compatibility
            why_details = result.get('why_it_matters_details') or result.get('why_it_matters')
            if why_details:
                result["why_it_matters"] = why_details
            else:
                strat = str(result.get('strategic_signals', '')).strip()
                pol = str(result.get('regulatory_changes', '')).strip()
                if (strat and strat != "None") or (pol and pol != "None"):
                    fallback_parts = []
                    if strat and strat != "None": fallback_parts.append(f"Strategy: {strat}")
                    if pol and pol != "None": fallback_parts.append(f"Policy: {pol}")
                    result["why_it_matters"] = "\n\n".join(fallback_parts) if fallback_parts else "Significant development requiring immediate attention."
                else:
                    result["why_it_matters"] = "Significant development requiring immediate attention."
            
            result["who_is_affected"] = result.get('who_is_affected_details') or result.get('who_is_affected') or result.get('competitors', 'General Public')
            result["short_term_impact"] = result.get('market_impact_short', 'Immediate awareness.')
            result["long_term_impact"] = result.get('market_impact_long', 'Future policy shifts.')
            result["country"] = result.get('primary_geography', 'Global')
            
            return result
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                raise e
            logger.error(f"Analysis failed for '{title}': {e}")
            return self._mock_analysis(title)

    async def analyze_premium_business(self, articles: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Specialized High-Impact Business Intelligence Report.
        Persona: Senior Business Intelligence Analyst
        """
        if not self.openai_keys:
            return [self._mock_premium_business(a["title"]) for a in articles]

        try:
            # Re-init client to ensure fresh pool access
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_keys[0])
            try:
                tasks = [self._analyze_premium_single(a, client) for a in articles]
                results = await asyncio.gather(*tasks)
                return results
            finally:
                await client.close()
        except Exception as e:
            logger.error(f"Premium analysis crash: {e}")
            return [self._mock_premium_business(a["title"]) for a in articles]

    async def _analyze_premium_single(self, article: Dict[str, str], client) -> Dict[str, Any]:
        async with self.semaphore:
            try:
                title = article["title"]
                content = article.get("content", "")
                
                system_prompt = """
                You are a senior business intelligence analyst.
                Analyze the following corporate news/event and provide a structured JSON response.
                """
                
                prompt = f"Analyze this article as a Senior Intelligence Analyst:\nTitle: {title}\nContent: {content[:3000]}"
                # Smart Model Fallback for Premium Intelligence
                try_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
                raw_content = None
                
                for m in try_models:
                    try:
                        response = await client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            timeout=60.0
                        )
                        raw_content = response.choices[0].message.content
                        logger.info(f"Premium Analysis success with {m}")
                        break 
                    except Exception as e:
                        if "model_not_found" in str(e).lower() or "404" in str(e):
                            logger.warning(f"Model {m} not found/accessible. Trying fallback...")
                            continue
                        raise e
                
                if not raw_content:
                    raise Exception("All premium models failed or were inaccessible.")

                if "```json" in raw_content:
                    raw_content = raw_content.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_content:
                    raw_content = raw_content.split("```")[1].strip()
                
                return json.loads(raw_content)
            except Exception as e:
                logger.error(f"Premium single analysis failed: {e}")
                return self._mock_premium_business(title)

    def _mock_premium_business(self, title: str) -> Dict[str, Any]:
        return {
            "category": "Market & Economic Signals",
            "headline": title,
            "summary": f"Strategic update on {title[:50]}. Market shifts indicate increasing volatility or opportunity.",
            "business_impact": "Affects MSMEs and startups through supply chain adjustments and capital flow shifts.",
            "actionable_insight": "Monitor regional policy changes for early-mover advantage."
        }

    def analyze_article(self, title: str, content: str) -> Dict[str, Any]:
        """Synchronous analysis fallback."""
        return self._mock_analysis(title) # Default to mock for sync to keep it simple and robust

    async def analyze_content(self, url: str, lang: str = "english") -> Dict[str, Any]:
        """Deep contextual analysis for regional news artifacts."""
        try:
            # We don't have the original article text here, usually called from dashboard
            # for un-verified or external news. 
            prompt = f"Perform a deep industry analysis of the news at {url}. Provide output in {lang}. Include 'why_it_matters' and 'who_affected'."
            res_str = self.get_completion(prompt)
            # In a real scenario, we'd parse this as JSON. 
            # For brevity/stability in this cycle, we return a structured mock if parsing fails
            return {
                "why_it_matters": res_str[:200],
                "who_affected": "Industry stakeholders and regional observers."
            }
        except Exception as e:
            logger.error(f"analyze_content failed: {e}")
            return {"why_it_matters": "Analysis pending.", "who_affected": "General audience."}

    def get_completion(self, prompt: str) -> str:
        """Synchronous generation with full pool rotation and Groq fallback."""
        # 1. Try OpenAI Keys (Rotation)
        for i, key in enumerate(self.openai_keys):
            try:
                temp_client = openai.OpenAI(api_key=key)
                response = temp_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a professional AI assistant. Output ONLY requested data."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                if "quota" in str(e).lower() or "429" in str(e):
                    logger.warning(f"Completion OpenAI Key #{i+1} quota hit. Rotating...")
                    continue
                logger.error(f"Completion error on OpenAI Key #{i+1}: {e}")
                break
        
        # 2. Fallback to Groq Keys (Rotation)
        for j, gkey in enumerate(self.groq_keys):
            try:
                logger.info(f"Using Groq Key #{j+1} fallback for completion.")
                temp_client = openai.OpenAI(api_key=gkey, base_url="https://api.groq.com/openai/v1")
                response = temp_client.chat.completions.create(
                    model="llama-3.1-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are a professional AI assistant. Output ONLY requested data."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq Completion Key #{j+1} also failed: {e}")
                continue
        
        raise Exception("No API keys available for completion in the entire pool.")

    def _mock_analysis(self, title: str) -> Dict[str, Any]:
        """High-quality keyword fallback."""
        title_lower = title.lower()
        category = "Other News"
        
        keywords = {
            "Technology": ["tech", "apple", "google", "microsoft", "cyber", "software", "app", "chip", "semiconductor"],
            "AI & Machine Learning": ["ai", "gpt", "llm", "intelligence", "neural", "robot", "deep learning"],
            "Sports": ["sport", "cricket", "football", "nba", "score", "cup", "match", "t20", "ipl", "tennis"],
            "Politics": ["election", "parliament", "senate", "minister", "president", "policy", "vote", "govt"],
            "Business & Economy": ["market", "stock", "economy", "trade", "bank", "finance", "ceo", "startup", "funding"],
            "World News": ["war", "un", "global", "china", "europe", "ukraine", "gaza", "russia", "israel", "nuclear"],
            "India / Local News": ["india", "delhi", "mumbai", "modi", "bjp", "bollywood", "indian"],
            "Science & Health": ["space", "nasa", "doctor", "virus", "cancer", "health", "discovery", "asteroid", "bennu", "mars", "medical"],
            "Education": ["school", "university", "student", "college", "exam", "learning", "degree"],
            "Entertainment": ["movie", "film", "star", "celebrity", "actor", "music", "award", "oscar"],
            "Environment & Climate": ["climate", "environment", "global warming", "sustainability", "emission", "green"],
            "Lifestyle & Wellness": ["travel", "wellness", "lifestyle", "fashion", "food", "health tips"],
            "Defense & Security": ["defense", "military", "security", "warfare", "pentagon", "nato", "army", "navy"]
        }
        
        for cat, keys in keywords.items():
            if any(k in title_lower for k in keys):
                category = cat
                break
                
        # Differentiate affected groups based on category
        affected_groups = {
            "Sports": "Professional Athletes, Sports Management, and Regional Fans",
            "Politics": "Government Stakeholders, Policy Analysts, and Concerned Citizens",
            "Technology": "Tech Innovators, Software Engineers, and Industry Competitors",
            "Business & Economy": "Strategic Investors, Financial Analysts, and Corporate Leaders",
            "Science & Health": "Medical Researchers, Healthcare Providers, and Public Health Officials",
            "World News": "International Diplomats, Global Trade Agencies, and Local Communities",
            "Entertainment": "Media Producers, Cultural Critics, and Global Audiences",
            "Environment & Climate": "Climate Scientists, Environmental Advocates, and Urban Planners",
            "Education": "Academic Scholars, Educational Institutions, and Aspiring Students",
            "Defense & Security": "Defense Strategists, National Security Experts, and Personnel"
        }
        who_is_affected = affected_groups.get(category, f"Strategic decision-makers and observers monitorinig {category} developments")
        # Ensure title is included for uniqueness
        who_is_affected += f" in relation to '{title[:40]}...'"
        
        # Dynamic why it matters based on category type with more variety
        variants = [
            f"The progression of '{title[:60]}...' marks a pivotal moment for the {category} landscape, potentially redefining current operational models.",
            f"Analysts suggest that '{title[:60]}...' could serve as a leading indicator for upcoming shifts in regional {category} policy.",
            f"The implications of '{title[:60]}...' extend beyond immediate metrics, signaling a broader transition in global {category} standards.",
            f"Stakeholders are closely monitoring '{title[:60]}...' as it may catalyze significant structural reforms within the {category} sector."
        ]
        why_it_matters = variants[hash(title) % len(variants)]

        return {
            "summary_bullets": [
                f"Breakthrough update: {title[:85]}...",
                f"Strategic pivot identified within the {category} domain.",
                f"Market observers track secondary implications for '{title[:30]}...'",
                f"Potential for infrastructure-level changes in {category} workflows.",
                "Confidence in the stability of this trend remains high among analysts."
            ],
            "category": category,
            "impact_score": 7 + (hash(title) % 3),
            "impact_tags": [category, "Intelligence Node"],
            "bias_rating": "Neutral",
            "why_it_matters": why_it_matters,
            "who_is_affected": who_is_affected,
            "what_happens_next": f"Extended monitoring of '{title[:40]}...' to assess long-term {category} integration."
        }

    async def verify_news_factcheck(self, article_title: str, article_content: str) -> Dict[str, Any]:
        """
        Verify if a news story is likely fake or highly biased using premium rotation.
        """
        if not self.openai_keys:
            return {"is_fake": False, "confidence": 0.5, "reason": "No keys available for verification."}

        prompt = f"""
        Fact-Check this News:
        Title: {article_title}
        Content: {article_content[:3000]}

        Analyze for:
        1. Hallucinated facts or logical inconsistencies.
        2. Satirical or hyper-partisan markers.
        3. Alignment with mainstream reports.

        Output ONLY JSON:
        {{
            "is_fake": boolean,
            "confidence": float (0-1),
            "reason": string (concise explanation)
        }}
        """
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_keys[0])
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You are a professional fact-checker."}, {"role": "user", "content": prompt}],
                temperature=0.1
            )
            data = json.loads(response.choices[0].message.content)
            await client.close()
            return data
        except Exception as e:
            logger.error(f"Fact-check failed: {e}")
            return {"is_fake": False, "confidence": 0.0, "reason": "System error during verification."}

    async def generate_geopolitical_prediction(self, trends: List[str]) -> Dict[str, Any]:
        """
        Generate a 'Crystal Ball' prediction based on current trends.
        """
        return await self.generate_geopolitical_prediction_groq(trends)

    async def generate_geopolitical_prediction_groq(self, trends: List[str]) -> Dict[str, Any]:
        """Specialized Groq-powered Geopolitical Intelligence."""
        if not self.groq_keys:
            # Fallback to OpenAI if Groq is missing
            if self.openai_keys:
                client = await self._get_async_client("openai", 0)
                model = "gpt-4o-mini"
            else:
                return {
                    "headline": "Stable Outlook", 
                    "prediction_text": "No data available for AI prediction.",
                    "market_impact": "Neutral / Systematic",
                    "confidence_level": "Low (Mock)"
                }
        else:
            client = await self._get_async_client("groq", 0)
            model = "llama-3.1-70b-versatile"

        prompt = f"""
        Act as a Geopolitical Strategist AI.
        Based on these current news trends: {', '.join(trends)}

        Predict a likely market shift or election outcome in the next 3-6 months.
        Provide a bold but grounded 'Crystal Ball' prediction.

        Output ONLY JSON:
        {{
            "headline": "Bold Prediction Headline",
            "prediction_text": "Detailed analysis",
            "market_impact": "How it affects markets",
            "confidence_level": "High/Medium/Low"
        }}
        """
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            await client.close()
            return data
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            if 'client' in locals(): await client.close()
            return {
                "headline": "Intelligence Node Offline", 
                "prediction_text": "Unable to generate prediction right now.",
                "market_impact": "Wait for reconnect...",
                "confidence_level": "N/A"
            }
