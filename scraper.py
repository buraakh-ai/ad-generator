import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json

def scrape_company(url):
    result = {
        "company_name": "",
        "description": "",
        "services": "",
        "tone": "",
        "icp": "",
        "logo_url": "",
        "colors": [],
        "tagline": "",
        "raw_text": ""
    }

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        og_site = soup.find("meta", property="og:site_name")
        if og_site:
            result["company_name"] = og_site.get("content", "")
        elif soup.title:
            result["company_name"] = soup.title.text.strip().split("|")[0].split("-")[0].strip()

        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc:
            result["description"] = og_desc.get("content", "")
        elif meta_desc:
            result["description"] = meta_desc.get("content", "")

        hero_tags = soup.find_all(["h1", "h2"], limit=3)
        taglines = [h.get_text(strip=True) for h in hero_tags if h.get_text(strip=True)]
        if taglines:
            result["tagline"] = " | ".join(taglines[:2])

        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["logo_url"] = og_image.get("content", "")
        else:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                alt = img.get("alt", "").lower()
                if "logo" in src.lower() or "logo" in alt:
                    result["logo_url"] = urljoin(url, src)
                    break

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        result["raw_text"] = text[:3000]

    except Exception as e:
        result["error"] = str(e)

    return result


def analyze_company_with_ai(url, client):
    from generator import call_counter

    scraped = scrape_company(url)

    if "error" in scraped:
        return scraped

    prompt = f"""You are a brand analyst. Analyze this company website content and extract structured information.

Website URL: {url}
Page title/name: {scraped['company_name']}
Meta description: {scraped['description']}
Hero headlines: {scraped['tagline']}
Page content: {scraped['raw_text']}

Extract and return ONLY this JSON, no extra text:
{{
  "company_name": "official company name",
  "what_they_do": "1-2 sentence summary of what the company does",
  "services": "comma separated list of main products or services",
  "brand_tone": "describe their brand voice and tone in 1 sentence",
  "target_audience": "who their ideal customer is, 1 sentence",
  "key_values": "comma separated list of brand values or themes",
  "tagline": "their actual tagline or slogan if found, else empty string"
}}"""

    call_counter["count"] += 1
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        analysis = json.loads(raw)
        analysis["logo_url"] = scraped["logo_url"]
        return analysis
    except:
        return scraped


def find_company_logo(company_name, client):
    from generator import call_counter

    prompt = f"""What is the official website domain for the company "{company_name}"?
Respond with ONLY the domain, nothing else. Example format: nike.com
If you're not sure, make your best guess based on the company name."""

    call_counter["count"] += 1
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    domain = response.text.strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").strip("/")

    logo_url = f"https://logo.clearbit.com/{domain}"

    try:
        check = requests.head(logo_url, timeout=5)
        if check.status_code == 200:
            return logo_url
    except:
        pass

    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"