from flask import Flask, request, send_file, jsonify
import requests
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, NumberObject
from io import BytesIO
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "service": "PDF TOC Navigation API - FIXED",
        "version": "3.1",
        "usage": "POST to /add-navigation with pdf_url and toc_items"
    })

@app.route('/add-navigation', methods=['POST'])
def add_navigation():
    try:
        data = request.json
        pdf_url = data.get('pdf_url')
        toc_items = data.get('toc_items', [])
        show_borders = data.get('show_borders', False)
        
        if not pdf_url:
            return jsonify({"error": "pdf_url is required"}), 400
        
        if not toc_items:
            return jsonify({"error": "toc_items is required"}), 400
        
        logging.info(f"Processing PDF: {pdf_url}")
        logging.info(f"Adding {len(toc_items)} TOC items")
        
        # Download PDF
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        pdf_bytes = BytesIO(response.content)
        
        logging.info(f"Downloaded {len(response.content)} bytes")
        
        # Load PDF
        reader = PdfReader(pdf_bytes)
        writer = PdfWriter()
        
        page_count = len(reader.pages)
        logging.info(f"PDF has {page_count} pages")
        
        # IMPORTANT: First, add ALL pages to writer
        # This ensures page references are properly created
        for page in reader.pages:
            writer.add_page(page)
        
        logging.info("All pages added to writer")
        
        # Now get the TOC page (page 0) from writer
        toc_page = writer.pages[0]
        
        # Add link annotations array if it doesn't exist
        if "/Annots" not in toc_page:
            toc_page[NameObject("/Annots")] = ArrayObject()
        
        links_added = 0
        for item in toc_items:
            name = item.get('name', 'Unnamed')
            x = item.get('x', 50)
            y = item.get('y')
            page = item.get('page')
            width = item.get('width', 520)
            height = item.get('height', 35)
            
            if y is None or page is None:
                logging.warning(f"Skipping item '{name}': missing y or page")
                continue
            
            # Validate page number
            if page >= page_count:
                logging.warning(f"Skipping item '{name}': page {page} doesn't exist (PDF has {page_count} pages)")
                continue
            
            # Create link annotation
            link = DictionaryObject()
            link[NameObject("/Type")] = NameObject("/Annot")
            link[NameObject("/Subtype")] = NameObject("/Link")
            
            # Clickable rectangle
            link[NameObject("/Rect")] = ArrayObject([
                NumberObject(x),
                NumberObject(y),
                NumberObject(x + width),
                NumberObject(y + height)
            ])
            
            # Border (visible if show_borders=true)
            if show_borders:
                link[NameObject("/Border")] = ArrayObject([
                    NumberObject(1), NumberObject(1), NumberObject(0)
                ])
                link[NameObject("/C")] = ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(1)  # Blue
                ])
            else:
                link[NameObject("/Border")] = ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ])
            
            # Highlight on click
            link[NameObject("/H")] = NameObject("/I")
            
            # CRITICAL FIX: Use writer's page reference, not reader's!
            # GoTo action with proper page reference
            action = DictionaryObject()
            action[NameObject("/S")] = NameObject("/GoTo")
            action[NameObject("/D")] = ArrayObject([
                writer.pages[page].indirect_reference,  # Use writer's pages!
                NameObject("/Fit")
            ])
            
            link[NameObject("/A")] = action
            
            # Add annotation to page
            toc_page["/Annots"].append(link)
            links_added += 1
            
            logging.info(f"✓ Added link '{name}' at ({x},{y}) → page {page}")
        
        # Save to BytesIO
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        logging.info(f"✅ Success! Added {links_added} navigation links")
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='document_with_navigation.pdf'
        )
        
    except Exception as e:
        logging.error(f"❌ Error: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
