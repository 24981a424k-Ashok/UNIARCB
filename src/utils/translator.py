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
GROQ_MODEL = "llama-3.1-70b-versatile"

class NewsTranslator:
    def __init__(self):
        # 1. Gather unique keys from settings pools
        self.openai_keys = list(dict.fromkeys(settings.OPENAI_API_KEYS))
        self.groq_keys = list(dict.fromkeys(settings.GROQ_API_KEYS))
        
        if not self.openai_keys and not self.groq_keys:
            logger.warning("No API keys found for NewsTranslator. Translation will be skipped.")
        else:
            logger.info(f"NewsTranslator initialized with {len(self.openai_keys)} OpenAI and {len(self.groq_keys)} Groq keys.")
        
        self._clients: Dict[str, AsyncOpenAI] = {}

    def _get_client(self, target_lang: str = None) -> tuple:
        """Return (AsyncOpenAI client, key_info) using rotation, prioritizing OpenAI for quality."""
        # 1. Try OpenAI Pool (Highest Quality)
        if self.openai_keys:
            idx = random.randint(0, len(self.openai_keys) - 1)
            key = self.openai_keys[idx]
            if key not in self._clients:
                self._clients[key] = AsyncOpenAI(api_key=key)
            return self._clients[key], f"OpenAI Pool#{idx + 1}"

        # 2. Fallback to Groq Pool
        if self.groq_keys:
            idx = random.randint(0, len(self.groq_keys) - 1)
            key = self.groq_keys[idx]
            if key not in self._clients:
                self._clients[key] = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
            return self._clients[key], f"Groq Pool#{idx + 1}"
            
        return None, "None"


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
                                "content": f"You are a professional news translator. Translate the following news text into {target_lang}. Return ONLY the translated text."
                            },
                            {"role": "user", "content": text}
                        ],
                        temperature=0.2,
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
            
            # Translate key text fields
            fields_to_translate = ['title', 'why', 'affected', 'headline']
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

            # 2. Batch Translate the rest
            logger.info(f"Translating {len(untranslated_indices)} uncached articles to {target_lang}...")
            
            client, key_info = self._get_client(target_lang)
            if not client:
                return node_data

            # Construct batch prompt for remaining
            to_translate = [stories[i] for i in untranslated_indices]
            articles_text = ""
            for idx, story in enumerate(to_translate, 1):
                bullets = story.get("bullets", [])
                bullet_str = "\n".join(f"- {b}" for b in bullets)
                articles_text += (
                    f"STORY_{idx}\n"
                    f"T: {story.get('title') or story.get('headline', '')}\n"
                    f"B: {bullet_str}\n"
                    f"W: {story.get('why') or story.get('why_it_matters', 'N/A')}\n"
                    f"A: {story.get('affected') or story.get('who_is_affected', 'N/A')}\n"
                    f"TGS: {', '.join(story.get('tags', []))}\n"
                    f"BIA: {story.get('bias') or 'Neutral'}\n"
                    f"---\n"
                )

            prompt = f"""Translate these news items to {target_lang}. Return ONLY a JSON object.
Format: {{"translated": [ {{ "t": "title", "b": ["bullet1", "..."], "w": "why", "a": "affected", "tgs": ["tag1", "..."], "bia": "bias" }} ]}}
Items:
{articles_text}"""

            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Return ONLY JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_result = json.loads(response.choices[0].message.content.strip())
            translated_list = raw_result.get("translated", [])

            # 3. Apply translations AND Update Cache
            for i, idx in enumerate(untranslated_indices):
                if i >= len(translated_list): break
                
                orig = stories[idx]
                tr = translated_list[i]
                
                # Update story object
                orig["title"] = tr.get("t", orig.get("title"))
                orig["headline"] = tr.get("t", orig.get("headline"))
                orig["bullets"] = tr.get("b", orig.get("bullets"))
                orig["why"] = tr.get("w", orig.get("why"))
                orig["affected"] = tr.get("a", orig.get("affected"))
                orig["tags"] = tr.get("tgs", orig.get("tags", []))
                orig["bias"] = tr.get("bia", orig.get("bias", "Neutral"))

                # PERSIST TO DATABASE
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
