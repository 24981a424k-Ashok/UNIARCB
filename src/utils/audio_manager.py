import os
import random
import logging
from pathlib import Path
from openai import OpenAI
from src.config import settings

logger = logging.getLogger(__name__)

class AudioManager:
    def __init__(self):
        # Move audio to persistent data directory for Railway/HF persistence
        from src.config.settings import DATA_DIR
        self.output_dir = DATA_DIR / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.keys = list(dict.fromkeys(settings.OPENAI_API_KEYS))
        
    def _get_client(self):
        if not self.keys:
            return None
        key = random.choice(self.keys)
        return OpenAI(api_key=key)

    def generate_tts(self, article_id: int, text: str) -> str:
        """
        Generate mp3 audio for an article brief.
        Returns the public URL path.
        """
        if not text:
            return None
            
        filename = f"news_{article_id}.mp3"
        filepath = self.output_dir / filename
        public_url = f"/static/audio/{filename}"

        # If already exists, don't regenerate (Perfection: Speed)
        if filepath.exists():
            return public_url

        client = self._get_client()
        if not client:
            logger.warning("No OpenAI key for TTS. Skipping.")
            return None

        try:
            # Keep text under limit (4096)
            clean_text = text[:4000]
            
            response = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=clean_text
            )
            
            response.stream_to_file(filepath)
            logger.info(f"✅ Generated TTS for article {article_id}")
            return public_url
        except Exception as e:
            logger.error(f"TTS Generation failed for {article_id}: {e}")
            return None

audio_manager = AudioManager()
