import os
import io
import json
import csv
import zipfile
import re
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def sanitize_filename(name):
    """Filename ke illegal characters ko clean karta hai."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")[:50]

def download_and_crop_image(img_url, top_crop_percentage=0.22):
    """
    Daraz image ke top header badges ko crop/remove karta hai.
    Top 22% portion ko cut karke clean product image bytes return karta hai.
    """
    if not img_url:
        return None

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(img_url, headers=headers, timeout=8)
        
        if response.status_code == 200:
            img = Image.open(io.BytesIO(response.content))
            width, height = img.size

            top_offset = int(height * top_crop_percentage)
            cropped_img = img.crop((0, top_offset, width, height))

            buffer = io.BytesIO()
            if cropped_img.mode in ("RGBA", "P"):
                cropped_img = cropped_img.convert("RGB")
                
            cropped_img.save(buffer, format="JPEG", quality=95)
            return buffer.getvalue()
    except Exception as e:
        print(f"Image downloading/cropping error: {e}")
    
    return None

def rewrite_bulk_with_ai(products):
    """Gemini AI se multiple products ke titles aur descriptions rewrite karta hai."""
    if not genai or not GEMINI_API_KEY or not products:
        for p in products:
            p['ai_name'] = p['original_name']
            p['ai_description'] = p['original_description']
        return products

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt_data = [
            {"id": idx, "name": p['original_name'], "description": p.get('original_description', '')}
            for idx, p in enumerate(products)
        ]

        prompt = f"""
        You are an e-commerce copywriting expert. Rewrite the product titles and descriptions for the following items to make them unique, SEO-friendly, and engaging.
        Return ONLY a JSON list of objects containing 'id', 'new_name', and 'new_description'.

        Input Data:
        {json.dumps(prompt_data)}
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        rewritten = json.loads(response.text)
        rewritten_dict = {item['id']: item for item in rewritten}

        for idx, p in enumerate(products):
            if idx in rewritten_dict:
                p['ai_name'] = rewritten_dict[idx].get('new_name', p['original_name'])
                p['ai_description'] = rewritten_dict[idx].get('new_description', p['original_description'])
            else:
                p['ai_name'] = p['original_name']
                p['ai_description'] = p['original_description']

    except Exception as e:
        print(f"AI Bulk Rewrite Error: {e}")
        for p in products:
            p['ai_name'] = p['original_name']
            p['ai_description'] = p['original_description']

    return products


def scrape_daraz_category_or_brand(search_query, max_products=50):
    """Daraz par Brand/Category search karke top 50 products details extract karta hai."""
    search_url = f"https://www.daraz.pk/catalog/?q={requests.utils.quote(search_query)}"
    products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_selector('div[data-qa-locator="product-item"]', timeout=10000)

            # Lazy loading ke liye scroll down
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1000)

            items = page.query_selector_all('div[data-qa-locator="product-item"]')[:max_products]

            for item in items:
                try:
                    title_elem = item.query_selector('a[title]')
                    price_elem = item.query_selector('span[class*="price"]') or item.query_selector('span:has-text("Rs.")')
                    img_elem = item.query_selector('img')

                    name = title_elem.get_attribute('title') if title_elem else "Product"
                    link = title_elem.get_attribute('href') if title_elem else ""
                    if link.startswith('//'):
                        link = 'https:' + link

                    price_str = price_elem.inner_text() if price_elem else "0"
                    
                    # Clean Price Logic: Sirf numbers extract karein (no float, integer only)
                    clean_price = re.sub(r'[^\d]', '', price_str)
                    price = int(clean_price) if clean_price else 0

                    img_url = ""
                    if img_elem:
                        img_url = img_elem.get_attribute('src') or img_elem.get_attribute('data-ks-lazyload') or ""
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url

                    products.append({
                        'original_name': name,
                        'original_description': name,
                        'price': price,
                        'image_url': img_url,
                        'product_url': link
                    })

                except Exception as item_err:
                    print(f"Item parse error: {item_err}")
                    continue

        except Exception as e:
            print(f"Search page error: {e}")
        finally:
            browser.close()

    # AI Rewrite for all scraped products
    products = rewrite_bulk_with_ai(products)
    return products
