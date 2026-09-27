import json
import os
import requests
from bs4 import BeautifulSoup
from decimal import Decimal, InvalidOperation

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def rewrite_text_with_ai(name, description=""):
    """Google Gemini API se Product Name aur Description rewrite karta hai."""
    if not genai or not GEMINI_API_KEY:
        return name, description

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
        You are an e-commerce copywriting expert. Rewrite the following product name and description for an online store to make them 100% unique, engaging, professional, and SEO-friendly while avoiding copyright issues.

        Original Name: {name}
        Original Description: {description}

        Respond ONLY in valid JSON format:
        {{
            "new_name": "Rewritten unique product name here",
            "new_description": "Rewritten unique product description here"
        }}
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        result = json.loads(response.text)
        return result.get("new_name", name), result.get("new_description", description)

    except Exception as e:
        print(f"AI Rewriting Error: {e}")
        return name, description


def scrape_daraz_product(url):
    """Daraz Product URL se Details Extract karta hai."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        script_tags = soup.find_all('script', type='application/ld+json')

        for script in script_tags:
            if not script.string:
                continue

            try:
                data = json.loads(script.string)

                if data.get('@type') == 'Product':
                    raw_name = data.get('name', '')
                    raw_description = data.get('description', '')
                    raw_image_url = data.get('image', '')

                    offers = data.get('offers', {})
                    if isinstance(offers, list) and len(offers) > 0:
                        offers = offers[0]

                    raw_price = offers.get('price') or offers.get('lowPrice') or "0.00"
                    try:
                        price_decimal = float(Decimal(str(raw_price)))
                    except (InvalidOperation, TypeError):
                        price_decimal = 0.00

                    unique_name, unique_description = rewrite_text_with_ai(raw_name, raw_description)

                    return {
                        'original_name': raw_name,
                        'ai_name': unique_name,
                        'original_description': raw_description,
                        'ai_description': unique_description,
                        'price': price_decimal,
                        'image_url': raw_image_url,
                        'product_url': url
                    }

            except (json.JSONDecodeError, TypeError):
                continue

        return None

    except requests.exceptions.RequestException as e:
        print(f"Scraping Request Error: {e}")
        return None

