import asyncio
import sys
import os
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.append(str(root))

from src.config import settings
from src.analysis.llm_analyzer import LLMAnalyzer
from src.utils.translator import NewsTranslator

async def test_connections():
    print("=== AI CONNECTION HEALTH CHECK ===")
    
    # 1. LLM Analyzer Check
    print("\n1. Testing LLM Analyzer...")
    analyzer = LLMAnalyzer()
    print(f" - Configured Keys: {len(analyzer.openai_keys)} OpenAI, {len(analyzer.groq_keys)} Groq")
    
    test_article = {"title": "India and UAE strengthen oil & gas ties in historical move", "content": "Content about oil and gas trade between UAE and India."}
    try:
        res = await analyzer.analyze_batch([test_article])
        if res and res[0].get("category"):
            print(" ✅ LLM Analysis Successful!")
            print(f"    - Category: {res[0].get('category')}")
        else:
            print(" ⚠️ LLM Analysis returned unexpected result.")
    except Exception as e:
        print(f" ❌ LLM Analysis Failed: {e}")

    # 2. Translation Check
    print("\n2. Testing NewsTranslator...")
    translator = NewsTranslator()
    test_text = "Global Intelligence Dashboard"
    try:
        hindi_text = await translator.translate_text(test_text, "hindi")
        if hindi_text and hindi_text != test_text:
            print(f" ✅ Translation Successful: {test_text} -> {hindi_text}")
        else:
            print(" ⚠️ Translation returned same text (check keys).")
    except Exception as e:
        print(f" ❌ Translation Failed: {e}")

    print("\n=== HEALTH CHECK COMPLETED ===")

if __name__ == "__main__":
    asyncio.run(test_connections())
