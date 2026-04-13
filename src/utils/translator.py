import logging
import random
import json
import asyncio
from typing import List, Dict, Any, Union
from openai import AsyncOpenAI
from src.config import settings
from src.database.models import SessionLocal, VerifiedNews

logger = logging.getLogger(__name__)


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

class NewsTranslator:
    def __init__(self):
        # 1. Gather unique non-empty keys from settings pools
        self.openai_keys = list(dict.fromkeys([k for k in settings.OPENAI_API_KEYS if k]))
        self.groq_keys = list(dict.fromkeys([k for k in settings.GROQ_API_KEYS if k]))
        
        # Combined Pool for high-speed rotation
        self.all_keys = self.openai_keys + self.groq_keys
        self.current_key_idx = 0
        self._concurrency_limit = asyncio.Semaphore(10) # Max 10 concurrent AI bursts (optimized for multi-key pool)
        
        if not self.all_keys:
            logger.warning("No API keys found for NewsTranslator. Translation will be skipped.")
        else:
            logger.info(f"NewsTranslator initialized with {len(self.all_keys)} keys (OpenAI: {len(self.openai_keys)}, Groq: {len(self.groq_keys)})")
        
        self._clients: Dict[str, AsyncOpenAI] = {}

    def _get_client(self, target_lang: str = None) -> tuple:
        """Return (AsyncOpenAI client, key_info) using steady rotation across all available keys."""
        if not self.all_keys:
            return None, "None"
            
        # Round-robin selection
        idx = self.current_key_idx % len(self.all_keys)
        self.current_key_idx += 1
        key = self.all_keys[idx]
        
        is_groq = key.startswith("gsk_")
        if key not in self._clients:
            if is_groq:
                self._clients[key] = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
            else:
                self._clients[key] = AsyncOpenAI(api_key=key)
        
        provider = "Groq" if is_groq else "OpenAI"
        return self._clients[key], f"{provider} Pool#{idx + 1}"


    async def translate_text(self, text: str, target_lang: str) -> str:
        """Translate a single piece of text to target_lang with automatic failover."""
        if not text or not target_lang or target_lang.lower() == 'english':
            return text
        
        # 0. Check Database Cache (Perfection Fix)
        # We need a way to identify if this text belongs to an article.
        # But for generic text, we might just skip or use a global cache table.
        # For now, we focus on the article blocks which are the main bottleneck.
        
        # 1. Prepare candidate pools

        attempt_pools = []
        if self.openai_keys: attempt_pools.append(("openai", self.openai_keys))
        if self.groq_keys: attempt_pools.append(("groq", self.groq_keys))

        for provider, keys in attempt_pools:
            # Shuffle keys within pool for better distribution on retries
            shuffled_keys = list(keys)
            random.shuffle(shuffled_keys)
            
            for i, key in enumerate(shuffled_keys):
                try:
                    if key not in self._clients:
                        if provider == "openai":
                            self._clients[key] = AsyncOpenAI(api_key=key)
                        else:
                            self._clients[key] = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
                    
                    client = self._clients[key]
                    model = "gpt-4o-mini" if provider == "openai" else GROQ_MODEL
                    
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": f"You are a master news journalist and professional translator. Translate the following news content into {target_lang} with perfect grammar, tone, and cultural accuracy. Maintain the professional news style. UNLESS THE USER ASKS OTHERWISE, RETURN ONLY THE TRANSLATED TEXT. NO INTROS, NO OUTROS."
                            },
                            {"role": "user", "content": text}
                        ],
                        temperature=0.1,
                        timeout=15
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e:
                    logger.warning(f"Translation failed on {provider} key {i+1}: {e}. Retrying...")
                    continue

        logger.error(f"All translation attempts failed for: {text[:30]}...")
        return text


    async def translate_stories(self, stories: List[Dict[str, Any]], target_lang: str) -> List[Dict[str, Any]]:
        """Translate key fields of multiple stories to target_lang (Async)."""
        if not stories or not target_lang or target_lang.lower() == 'english':
            return stories

        translated_stories = json.loads(json.dumps(stories))
        
        # Parallelize translation of stories for better performance
        async def translate_single_story(story):
            # Translate bullet lists
            if 'bullets' in story and story['bullets']:
                story['bullets'] = await asyncio.gather(*[self.translate_text(b, target_lang) for b in story['bullets']])
            
            # Translate key text fields (Adding 'summary' for Personal AI News)
            fields_to_translate = ['title', 'summary', 'why', 'affected', 'headline']
            for field in fields_to_translate:
                if field in story and story[field]:
                    story[field] = await self.translate_text(story[field], target_lang)
            return story

        # Process stories in small groups to distribute across keys and avoid bursts
        results = []
        batch_size = 3
        for i in range(0, len(translated_stories), batch_size):
            batch = translated_stories[i:i+batch_size]
            results.extend(await asyncio.gather(*[translate_single_story(s) for s in batch]))
            if i + batch_size < len(translated_stories):
                await asyncio.sleep(0.3)  # Small breath between batches

        return results

    async def translate_node_bulk(self, node_data: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
        """
        Translate an entire node dashboard with high-speed caching.
        Checks if individual articles already have translations in the DB.
        """
        if not target_lang or target_lang.lower() == 'english':
            return node_data

        stories = node_data.get("stories", [])
        if not stories:
            return node_data

        untranslated_indices = []
        db = SessionLocal()
        
        try:
            # 1. Try to load from cache first
            for idx, story in enumerate(stories):
                article_id = story.get("id")
                if article_id and isinstance(article_id, (int, str)) and str(article_id).isdigit():
                    article = db.query(VerifiedNews).filter(VerifiedNews.id == int(article_id)).first()
                    if article and article.translation_cache:
                        # Handle potential stringified JSON in SQLite
                        cache = article.translation_cache
                        if isinstance(cache, str):
                            try: cache = json.loads(cache)
                            except: cache = {}
                        
                        if target_lang.lower() in [k.lower() for k in cache.keys()]:
                            # Find the actual key case-insensitively
                            lang_key = next(k for k in cache.keys() if k.lower() == target_lang.lower())
                            cached_val = cache[lang_key]
                            
                            story["title"] = cached_val.get("title", story.get("title"))
                            story["headline"] = cached_val.get("title", story.get("headline"))
                            story["bullets"] = cached_val.get("bullets", story.get("bullets"))
                            story["why"] = cached_val.get("why", story.get("why"))
                            story["why_it_matters"] = cached_val.get("why", story.get("why_it_matters"))
                            story["affected"] = cached_val.get("affected", story.get("affected"))
                            story["who_is_affected"] = cached_val.get("affected", story.get("who_is_affected"))
                            story["is_cached"] = True
                            continue
                
                untranslated_indices.append(idx)

            if not untranslated_indices:
                logger.info(f"0.1s perfection: All {len(stories)} articles loaded from cache for {target_lang}.")
                return node_data

            # 2. Batch Translate the rest in parallel using simultaneous keys
            logger.info(f"Translating {len(untranslated_indices)} uncached articles to {target_lang} in parallel batches...")
            
            to_translate_full = [stories[i] for i in untranslated_indices]
            batch_size = 4 # Optimized for Llama-3 / Groq stability
            batches = [to_translate_full[i:i + batch_size] for i in range(0, len(to_translate_full), batch_size)]
            
            def _extract_json(text_content):
                """Search for and extract valid JSON from a mixed-text response."""
                if not text_content: return None
                try:
                    # Clean markdown tags
                    clean = text_content.strip()
                    if "```json" in clean:
                        clean = clean.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean:
                        clean = clean.split("```")[1].strip()
                    
                    # Find start and end of JSON object
                    start = clean.find('{')
                    end = clean.rfind('}')
                    if start != -1 and end != -1:
                        clean = clean[start:end+1]
                    
                    return json.loads(clean)
                except Exception as e:
                    logger.warning(f"JSON extraction failed: {e}. Raw: {text_content[:100]}...")
                    return None

            async def translate_batch(batch_items, b_idx):
                async with self._concurrency_limit:
                    client, key_info = self._get_client(target_lang)
                    if not client: return []
                    await asyncio.sleep(b_idx * 0.4) 
                
                # RECONSTRUCTING ARTICLE DATA FOR AI
                articles_text = ""
                for idx, story in enumerate(batch_items, 1):
                    bullets = story.get("bullets", [])
                    bullet_str = "\n".join(f"- {b}" for b in bullets)
                    articles_text += (
                        f"STORY_{idx}\n"
                        f"T: {story.get('title') or story.get('headline', '')}\n"
                        f"B: {bullet_str}\n"
                        f"S: {story.get('summary') or 'N/A'}\n"
                        f"W: {story.get('why') or story.get('why_it_matters', 'N/A')}\n"
                        f"A: {story.get('affected') or story.get('who_is_affected', 'N/A')}\n"
                        f"---\n"
                    )

                # EXHAUSTIVE RETRY LOOP: Try every key in the pool before giving up
                max_retries = len(self.all_keys)
                for attempt in range(max_retries):
                    try:
                        # Determine model for current key
                        batch_model = GROQ_MODEL if "Groq" in key_info else "gpt-4o-mini"
                        
                        response = await client.chat.completions.create(
                            model=batch_model,
                            messages=[
                                {"role": "system", "content": f"You are a professional journalist group translating intelligence reports to {target_lang}. Return ONLY a JSON object. No conversational filler."},
                                {"role": "user", "content": f"Translate these items to {target_lang}:\n{articles_text}\nFormat as JSON: {{\"translated\": [ {{ \"t\": \"title\", \"b\": [\"bullet\"], \"s\": \"summary\", \"w\": \"why\", \"a\": \"affected\" }} ]}}"}
                            ],
                            temperature=0.1,
                            timeout=45 # High timeout for complex languages
                        )
                        raw_content = response.choices[0].message.content.strip()
                        raw_result = _extract_json(raw_content)
                        
                        if raw_result and raw_result.get("translated"):
                            return raw_result.get("translated")
                        
                        raise ValueError("Invalid or empty translation result")

                    except Exception as e:
                        if "429" in str(e) or "rate_limit" in str(e).lower():
                            logger.warning(f"Batch {b_idx} Retry {attempt+1}/{max_retries}: 429 Rate Limit on {key_info}. Cycling key...")
                        else:
                            logger.error(f"Batch {b_idx} Retry {attempt+1}/{max_retries} failed on {key_info}: {e}")
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 * (attempt + 1)) # Incremental backoff
                            client, key_info = self._get_client(target_lang) # Get NEXT key in rotation
                        else:
                            logger.error(f"Exhausted all {max_retries} keys for Batch {b_idx}. Returning empty.")
                
                return []

            # Execute all batches simultaneously (distributed across keys automatically by rotation)
            batch_results = await asyncio.gather(*[translate_batch(b, i) for i, b in enumerate(batches)])
            
            # Flatten results and apply
            all_translated = []
            for res_list in batch_results:
                all_translated.extend(res_list)

            # 3. Apply translations AND Update Cache
            for i, idx in enumerate(untranslated_indices):
                if i >= len(all_translated): break
                
                orig = stories[idx]
                tr = all_translated[i]
                
                # Update story object
                orig["title"] = tr.get("t", orig.get("title"))
                orig["headline"] = tr.get("t", orig.get("headline"))
                orig["bullets"] = tr.get("b", orig.get("bullets"))
                orig["summary"] = tr.get("s", orig.get("summary"))
                orig["why"] = tr.get("w", orig.get("why"))
                orig["affected"] = tr.get("a", orig.get("affected"))
                orig["is_translated"] = True

                # PERSIST TO DATABASE CACHE
                article_id = orig.get("id")
                if article_id and isinstance(article_id, (int, str)) and str(article_id).isdigit():
                    article = db.query(VerifiedNews).filter(VerifiedNews.id == int(article_id)).first()
                    if article:
                        cache = article.translation_cache or {}
                        if isinstance(cache, str): 
                            try: cache = json.loads(cache)
                            except: cache = {}
                        
                        cache[target_lang] = {
                            "title": orig["title"],
                            "bullets": orig["bullets"],
                            "summary": orig.get("summary", ""),
                            "why": orig["why"],
                            "affected": orig["affected"],
                            "tags": orig.get("tags", []),
                            "bias": orig.get("bias", "Neutral")
                        }
                        article.translation_cache = cache
                        db.commit()

            return node_data

        except Exception as e:
            logger.error(f"Bulk translation with cache failed: {e}")
            return node_data
        finally:
            db.close()

    async def _do_translate(self, items: List[Dict[str, str]], target_lang: str, node_title: str = "") -> Dict[str, Any]:
        """
        Public standard wrapper for translating a list of JSON-like items.
        Used by the web dashboard for nodes and regional news.
        """
        if not items or not target_lang or target_lang.lower() == 'english':
            return {"translated_stories": items, "node_title": node_title}

        try:
            # Re-use existing translate_stories or use the more efficient batch logic
            # For this wrapper, we use the simple list-based translation
            translated = await self.translate_stories(items, target_lang)
            
            # Handle node title separately if provided
            trans_title = node_title
            if node_title:
                trans_title = await self.translate_text(node_title, target_lang)
            
            return {
                "translated_stories": translated,
                "node_title": trans_title
            }
        except Exception as e:
            logger.error(f"Wrapper translation failed: {e}")
            return {"translated_stories": items, "node_title": node_title}
