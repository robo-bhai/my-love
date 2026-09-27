import csv
import io
import zipfile
import requests
from flask import Flask, render_template, request, Response, send_file
from scraper_bulk import scrape_daraz_category_or_brand, sanitize_filename

app = Flask(__name__)

scraped_bulk_cache = []

@app.route('/', methods=['GET', 'POST'])
def index():
    global scraped_bulk_cache
    data_list = []
    error = None

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        if search_query:
            results = scrape_daraz_category_or_brand(search_query, max_products=50)
            if results:
                data_list = results
                scraped_bulk_cache = results
            else:
                error = "Koi product nahi mila. Valid Category/Brand search karein."
        else:
            error = "Search query likhna zaroori hai."

    return render_template('index.html', data_list=data_list, error=error)


@app.route('/download/zip')
def download_zip():
    if not scraped_bulk_cache:
        return "No data available to download", 400

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Generate CSV Data in 13-Column Template Format
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)

        headers = [
            'Name*', 'Serial No', 'Barcode', 'Description', 
            'Category', 'Brand', 'Unit', 'Location', 
            'Type', 'Price', 'Low Stock Threshold', 'Used For', 'Is Active'
        ]
        writer.writerow(headers)

        headers_req = {'User-Agent': 'Mozilla/5.0'}

        for idx, item in enumerate(scraped_bulk_cache, start=1):
            ai_name = item.get('ai_name', f"Product_{idx}")
            safe_name = sanitize_filename(ai_name)
            img_filename = f"images/{idx}_{safe_name}.jpg"

            # CSV Row Write
            writer.writerow([
                ai_name,                                       # Name*
                f"SN-{idx:03d}",                                # Serial No
                '',                                             # Barcode
                item.get('ai_description', ''),                # Description
                '',                                             # Category
                '',                                             # Brand
                'piece',                                        # Unit
                '',                                             # Location
                '',                                             # Type
                item.get('price', 0),                           # Price
                '',                                             # Low Stock
                '',                                             # Used For
                'TRUE'                                          # Is Active
            ])

            # 2. Download Image and Add to ZIP Archive
            img_url = item.get('image_url')
            if img_url:
                try:
                    img_resp = requests.get(img_url, headers=headers_req, timeout=5)
                    if img_resp.status_code == 200:
                        zip_file.writestr(img_filename, img_resp.content)
                except Exception as img_err:
                    print(f"Failed to download image {img_url}: {img_err}")

        # Add CSV file into ZIP archive
        zip_file.writestr('product_import.csv', csv_buffer.getvalue())

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='daraz_bulk_products.zip'
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)
