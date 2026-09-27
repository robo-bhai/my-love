import json
import os
import re
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


def extract_price_from_soup(soup, text_content):
    """Multiple Fallbacks se Price Extract karne ka function"""
    # Fallback 1: Meta Tags
    meta_price = soup.find('meta', property='product:price:amount') or soup.find('meta', property='og:price:amount')
    if meta_price and meta_price.get('content'):
        try:
            return float(Decimal(meta_price['content']))
        except (InvalidOperation, ValueError):
            pass

    # Fallback 2: Regex for Rs. or PKR in page source
    price_matches = re.findall(r'Rs\.?\s*([\d,]+(?:\.\d{2})?)', text_content, re.IGNORECASE)
    if not price_matches:
        price_matches = re.findall(r'"price":\s*"([\d\.]+)"', text_content)
        if not price_matches:
            price_matches = re.findall(r'"salePrice":\s*"([\d\.]+)"', text_content)

    if price_matches:
        for p in price_matches:
            clean_p = p.replace(',', '')
            try:
                val = float(Decimal(clean_p))
                if val > 0:
                    return val
            except (InvalidOperation, ValueError):
                continue

    return 0.0


def extract_image_from_soup(soup, text_content):
    """Multiple Fallbacks se Image URL Extract karne ka function"""
    # Fallback 1: OpenGraph Meta Image
    meta_img = soup.find('meta', property='og:image') or soup.find('meta', name='twitter:image')
    if meta_img and meta_img.get('content'):
        img_url = meta_img['content']
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        return img_url

    # Fallback 2: Regex for image URLs in JS payload
    img_matches = re.findall(r'"image":\s*"([^"]+)"', text_content)
    if img_matches:
        for img_url in img_matches:
            if 'daraz' in img_url or 'alicdn' in img_url:
                img_url = img_url.replace('\\/', '/')
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                return img_url

    # Fallback 3: DOM img tags
    main_img = soup.find('img', class_=re.compile(r'pdp-mod-common-image|gallery-preview-panel'))
    if main_img and main_img.get('src'):
        img_url = main_img['src']
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        return img_url

    return ""


def scrape_daraz_product(url):
    """Daraz Product URL se Multi-Fallback Scraping"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = response.text

        raw_name = ""
        raw_description = ""
        raw_image_url = ""
        price_decimal = 0.0

        # 1. Primary Method: Try JSON-LD
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Product':
                    raw_name = data.get('name', '')
                    raw_description = data.get('description', '')
                    
                    # Try getting image from JSON-LD
                    img_val = data.get('image')
                    if isinstance(img_val, list) and len(img_val) > 0:
                        raw_image_url = img_val[0]
                    elif isinstance(img_val, str):
                        raw_image_url = img_val

                    # Try getting price from JSON-LD
                    offers = data.get('offers', {})
                    if isinstance(offers, list) and len(offers) > 0:
                        offers = offers[0]
                    if isinstance(offers, dict):
                        p_val = offers.get('price') or offers.get('lowPrice')
                        if p_val:
                            try:
                                price_decimal = float(Decimal(str(p_val)))
                            except (InvalidOperation, TypeError):
                                pass
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        # 2. Name Fallback (Title / Meta)
        if not raw_name:
            og_title = soup.find('meta', property='og:title')
            raw_name = og_title['content'] if og_title else (soup.title.string if soup.title else "Daraz Product")

        # 3. Image Fallback
        if not raw_image_url:
            raw_image_url = extract_image_from_soup(soup, page_text)

        # 4. Price Fallback
        if price_decimal == 0.0:
            price_decimal = extract_price_from_soup(soup, page_text)

        # Ensure image link has protocol
        if raw_image_url.startswith('//'):
            raw_image_url = 'https:' + raw_image_url

        # Divide original price by 2.8
        calculated_price = round(price_decimal / 2.8, 2) if price_decimal > 0 else 0.0

        # AI Text Rewrite
        unique_name, unique_description = rewrite_text_with_ai(raw_name, raw_description)

        return {
            'original_name': raw_name,
            'ai_name': unique_name,
            'original_description': raw_description,
            'ai_description': unique_description,
            'original_price': price_decimal,
            'price': calculated_price,
            'image_url': raw_image_url,
            'product_url': url
        }

    except requests.exceptions.RequestException as e:
        print(f"Scraping Request Error: {e}")
        return None
