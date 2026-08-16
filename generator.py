import json
import random
import time
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]

GEMINI_KEYS = [key for key in GEMINI_KEYS if key]

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# ---------------------------------------------------------------------------
# Key rotation state
# ---------------------------------------------------------------------------

current_key_index = {"index": 0}
exhausted_keys    = {"keys": set()}
call_counter      = {"count": 0}
company_cache     = {}

TEXT_MODEL        = "gemini-2.5-flash"
OPENAI_TEXT_MODEL = "gpt-4o-mini"


class AllProvidersExhaustedError(Exception):
    pass


class TextProviderSwitchedWarning(Exception):
    def __init__(self, message, from_provider, to_provider):
        super().__init__(message)
        self.from_provider = from_provider
        self.to_provider   = to_provider


def get_client(key_index=None):
    idx = key_index if key_index is not None else current_key_index["index"]
    return genai.Client(api_key=GEMINI_KEYS[idx])


def rotate_key():
    current = current_key_index["index"]
    exhausted_keys["keys"].add(current)
    for i in range(len(GEMINI_KEYS)):
        if i not in exhausted_keys["keys"]:
            current_key_index["index"] = i
            print(f"[keys] Rotated to key index {i}")
            return True
    return False


def reset_keys():
    exhausted_keys["keys"] = set()
    current_key_index["index"] = 0
    print("[keys] All keys reset")


def call_gemini(prompt, system_prompt="", retries=3):
    global call_counter
    call_counter["count"] += 1

    for attempt in range(retries):
        try:
            idx    = current_key_index["index"]
            client = get_client(idx)
            print(f"[gemini] Using key index {idx}, attempt {attempt+1}/{retries}")

            config_kwargs = {}
            if system_prompt:
                config_kwargs["system_instruction"] = system_prompt

            response = client.models.generate_content(
                model    = TEXT_MODEL,
                contents = prompt,
                config   = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
            )
            return response.text

        except Exception as e:
            err = str(e).lower()
            print(f"[gemini] Key {current_key_index['index']} error: {e}")

            if any(x in err for x in ["quota", "rate", "429", "exhausted", "resource_exhausted"]):
                print(f"[gemini] Key {current_key_index['index']} quota exhausted — rotating...")
                rotated = rotate_key()
                if not rotated:
                    print("[gemini] All Gemini keys exhausted — switching to OpenAI fallback")
                    raise TextProviderSwitchedWarning(
                        "All Gemini quota exhausted",
                        from_provider="Gemini",
                        to_provider="OpenAI GPT"
                    )
                continue

            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

    raise Exception("Gemini failed after all retries")


def call_openai(prompt, system_prompt=""):
    if not OPENAI_KEY:
        raise AllProvidersExhaustedError(
            "All Gemini keys are exhausted and no OpenAI key is configured. "
            "Please add your OpenAI API key to generator.py to continue."
        )

    import requests
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    print(f"[openai] Calling {OPENAI_TEXT_MODEL}...")
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": OPENAI_TEXT_MODEL, "messages": messages, "max_tokens": 2000},
        timeout=60
    )
    if r.status_code != 200:
        raise AllProvidersExhaustedError(f"OpenAI also failed: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


def call_text_model(prompt, system_prompt=""):
    try:
        return call_gemini(prompt, system_prompt)
    except TextProviderSwitchedWarning as w:
        print(f"[text] Switching from {w.from_provider} to {w.to_provider}")
        result = call_openai(prompt, system_prompt)
        return result


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------

def find_company_logo(company_name, website_url=None):
    if website_url:
        domain = website_url.replace("https://", "").replace("http://", "").split("/")[0]
        return f"https://logo.clearbit.com/{domain}"
    domain = company_name.lower().replace(" ", "") + ".com"
    return f"https://logo.clearbit.com/{domain}"


def analyze_company_with_ai(company_name, website_content="", website_url=""):
    prompt = f"""Analyze this company and return ONLY a JSON object with no markdown:

Company: {company_name}
Website URL: {website_url}
Website Content: {website_content[:3000] if website_content else "Not available"}

Return this exact JSON structure:
{{
  "what_they_do": "one sentence description",
  "services": "comma separated list of main services",
  "target_audience": "who they serve",
  "brand_tone": "professional/friendly/bold/luxury/etc",
  "key_values": "comma separated values",
  "tagline": "their tagline or a suggested one",
  "logo_url": "{find_company_logo(company_name, website_url)}"
}}"""

    try:
        raw = call_text_model(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"[company] Analysis failed: {e}")
        return {
            "what_they_do": f"{company_name} provides products and services",
            "services": "General services",
            "target_audience": "General audience",
            "brand_tone": "professional",
            "key_values": "Quality, Service, Excellence",
            "tagline": f"{company_name} — built for what's next.",
            "logo_url": find_company_logo(company_name, website_url)
        }


# ---------------------------------------------------------------------------
# Website scraping
# ---------------------------------------------------------------------------

def scrape_website(url):
    try:
        import requests
        from bs4 import BeautifulSoup
        print(f"Scraping {url}...")
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","nav","footer","header"]):
            tag.decompose()
        text = " ".join(soup.get_text().split())
        return text[:5000]
    except Exception as e:
        print(f"[scrape] {e}")
        return ""


def find_website(company_name):
    try:
        prompt = f"What is the official website URL of {company_name}? Reply with ONLY the URL, nothing else."
        url = call_text_model(prompt).strip().strip('"').strip("'")
        if url.startswith("http"):
            return url
    except Exception as e:
        print(f"[website] {e}")
    return None


# ---------------------------------------------------------------------------
# Ad generation
# ---------------------------------------------------------------------------

def generate_ads(company_name, product_description, ad_idea, event_context=None, company_url=None):
    cache_key = (company_url or company_name).lower().strip()

    if cache_key in company_cache:
        print(f"Cached data for {company_name}")
        company_data = company_cache[cache_key]["company_data"]
        website_url  = company_cache[cache_key].get("website_url", company_url or "")
    else:
        website_content = ""
        website_url     = company_url or ""

        if company_url:
            website_content = scrape_website(company_url)
        else:
            print(f"No URL provided — finding website for {company_name}...")
            found = find_website(company_name)
            if found:
                print(f"Found website: {found}")
                website_url     = found
                website_content = scrape_website(found)
            else:
                print("Could not find website — falling back to logo search only...")

        company_data = analyze_company_with_ai(company_name, website_content, website_url)
        company_cache[cache_key] = {
            "company_data": company_data,
            "website_url":  website_url
        }

    from events import pick_best_event
    if event_context:
        detected_event = event_context
    else:
        print("No event provided — auto-detecting trending events...")
        detected_event = pick_best_event(company_name, company_data, get_client())

    detected_name = company_data.get("what_they_do", company_name) and company_name

    system_prompt = f"""You are an expert social media advertising copywriter.
Company: {company_name}
What they do: {company_data.get('what_they_do', '')}
Services: {company_data.get('services', '')}
Target audience: {company_data.get('target_audience', '')}
Brand tone: {company_data.get('brand_tone', 'professional')}
Key values: {company_data.get('key_values', '')}
Tagline: {company_data.get('tagline', '')}
Product info: {product_description}
Ad angle: {ad_idea}
Trending event to connect to: {detected_event}

Write platform-specific ad copy that connects the brand naturally to the trending event."""

    prompt = """Generate ad copy for all 4 platforms and return ONLY a JSON object with no markdown:
{
  "tiktok": "short punchy TikTok/Reels caption under 150 chars with 1-2 relevant hashtags",
  "instagram": "engaging Instagram caption 150-300 chars with 3-5 relevant hashtags",
  "twitter": "punchy X/Twitter post under 280 chars",
  "facebook": "detailed Facebook post 200-400 chars that tells a story and ends with a CTA",
  "image_headline": "short 5-8 word headline for the ad image",
  "quality_score": 8,
  "quality_reason": "one sentence explaining the score"
}"""

    raw_text = call_text_model(prompt, system_prompt)
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip()

    try:
        ads = json.loads(raw_text)
    except json.JSONDecodeError:
        ads = {
            "tiktok":        raw_text,
            "instagram":     raw_text,
            "twitter":       raw_text,
            "facebook":      raw_text,
            "image_headline": f"{company_name} — built for what's next.",
            "quality_score":  0,
            "quality_reason": "Could not parse quality score."
        }

    return ads, company_name, detected_event, company_data