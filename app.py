import csv
import io
import json
import os
from flask import Flask, render_template, request, Response, jsonify
from test_scraper import scrape_daraz_product

app = Flask(__name__)

# Temporary in-memory cache last scraped result
scraped_cache = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    global scraped_cache
    data = None
    error = None

    if request.method == 'POST':
        product_url = request.form.get('product_url', '').strip()
        if product_url:
            result = scrape_daraz_product(product_url)
            if result:
                data = result
                scraped_cache = result
            else:
                error = "Daraz URL se data extract nahi ho saka. Valid product link check karein."
        else:
            error = "Baraye meharbani URL paste karein."

    return render_template('index.html', data=data, error=error)


@app.route('/download/csv')
def download_csv():
    if not scraped_cache:
        return "No data available", 400

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(['Original Name', 'AI Name', 'Price', 'Image URL', 'Original Desc', 'AI Desc', 'Product URL'])
    # Row Data
    writer.writerow([
        scraped_cache.get('original_name', ''),
        scraped_cache.get('ai_name', ''),
        scraped_cache.get('price', 0),
        scraped_cache.get('image_url', ''),
        scraped_cache.get('original_description', ''),
        scraped_cache.get('ai_description', ''),
        scraped_cache.get('product_url', '')
    ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=daraz_scraped_product.csv"}
    )


@app.route('/download/json')
def download_json():
    if not scraped_cache:
        return "No data available", 400

    return Response(
        json.dumps(scraped_cache, indent=4),
        mimetype="application/json",
        headers={"Content-disposition": "attachment; filename=daraz_scraped_product.json"}
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)

