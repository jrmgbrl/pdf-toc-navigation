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
        "service": "PDF TOC Navigation API",
        "version": "2.0",
        "usage": "POST to /add-navigation with pdf_url and grounding_data"
    })

def extract_toc_from_grounding(grounding_data):
    """
    Extract TOC items from Landing.ai grounding data
    
    Returns list of {"y": position, "page": target_page}
    """
    toc_items = []
    
    try:
        # Get chunks array
        if isinstance(grounding_data, list):
            chunks = grounding_data[0].get('chunks', []) if grounding_data else []
        else:
            chunks = grounding_data.get('chunks', [])
        
        logging.info(f"Processing {len(chunks)} chunks from grounding data")
        
        # Standard PDF height in points
        pdf_height = 792
        
        # Only process chunks from page 0 (TOC page) that reference content pages
        for chunk in chunks:
            grounding = chunk.get('grounding', {})
            chunk_page = grounding.get('page')
            markdown = chunk.get('markdown', '')
            
            # Only process TOC items (they're on page 0 and mention "Page X")
            if chunk_page == 0 and 'Page' in markdown:
                # Extract the page number mentioned in the text
                # e.g., "Executive Summary Page 1" -> page 1
                try:
                    # Find "Page X" pattern
                    page_text = markdown.split('Page')[-1].strip().split()[0]
                    target_page = int(page_text)
                    
                    # Get Y position from bounding box
                    box = grounding.get('box', {})
                    box_top = box.get('top', 0)  # Percentage from top (0-1)
                    box_bottom = box.get('bottom', 0)
                    
                    # Calculate center Y position in PDF coordinates
                    # PDF coordinates: 0 at bottom, 792 at top
                    # Box coordinates: 0 at top, 1 at bottom
                    center_percent = (box_top + box_bottom) / 2
                    y_position = pdf_height - (center_percent * pdf_height)
                    
                    toc_items.append({
                        "y": int(y_position),
                        "page": target_page,  # The page mentioned in TOC
                        "label": markdown[:50]  # For logging
                    })
                    
                    logging.info(f"TOC item: '{markdown[:30]}' -> Page {target_page}, Y={int(y_position)}")
                    
                except (ValueError, IndexError) as e:
                    logging.warning(f"Could not parse page number from: {markdown}")
                    continue
        
        logging.info(f"Extracted {len(toc_items)} TOC items")
        return toc_items
        
    except Exception as e:
        logging.error(f"Error extracting TOC from grounding: {str(e)}")
        return []

@app.route('/add-navigation', methods=['POST'])
def add_navigation():
    try:
        data = request.json
        pdf_url = data.get('pdf_url')
        show_borders = data.get('show_borders', False)
        
        if not pdf_url:
            return jsonify({"error": "pdf_url is required"}), 400
        
        logging.info(f"Processing PDF: {pdf_url}")
        
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
        
        # Get TOC page (first page)
        toc_page = reader.pages[0]
        
        # Extract TOC items dynamically
        toc_items = data.get('toc_items')
        
        if not toc_items:
            # Try to extract from grounding data
            grounding_data = data.get('grounding_data')
            
            if grounding_data:
                toc_items = extract_toc_from_grounding(grounding_data)
                logging.info(f"Extracted {len(toc_items)} items from grounding data")
            else:
                # Fallback: auto-generate based on page count
                start_y = data.get('start_y', 650)
                spacing = data.get('spacing', 60)
                
                toc_items = []
                for i in range(1, page_count):
                    y_position = start_y - ((i - 1) * spacing)
                    toc_items.append({
                        "y": y_position,
                        "page": i
                    })
                
                logging.info(f"Auto-generated {len(toc_items)} TOC items")
        
        # Add link annotations
        if "/Annots" not in toc_page:
            toc_page[NameObject("/Annots")] = ArrayObject()
        
        links_added = 0
        for item in toc_items:
            target_page = item["page"]
            
            # Only add link if target page exists
            if target_page < page_count:
                link = DictionaryObject()
                link[NameObject("/Type")] = NameObject("/Annot")
                link[NameObject("/Subtype")] = NameObject("/Link")
                
                # Clickable area (full width of TOC item)
                link[NameObject("/Rect")] = ArrayObject([
                    NumberObject(50),   # Left edge
                    NumberObject(item["y"] - 10),  # Bottom (slightly below text)
                    NumberObject(570),  # Right edge (wider)
                    NumberObject(item["y"] + 30)   # Top (covers text height)
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
                
                # Highlight mode when clicked
                link[NameObject("/H")] = NameObject("/I")  # Invert on click
                
                # GoTo action
                action = DictionaryObject()
                action[NameObject("/S")] = NameObject("/GoTo")
                action[NameObject("/D")] = ArrayObject([
                    reader.pages[target_page].indirect_reference,
                    NameObject("/Fit")
                ])
                
                link[NameObject("/A")] = action
                toc_page["/Annots"].append(writer._add_object(link))
                links_added += 1
                
                logging.info(f"Added link at Y={item['y']} to page {target_page}")
        
        # Add all pages to writer
        writer.add_page(toc_page)
        for i in range(1, page_count):
            writer.add_page(reader.pages[i])
        
        # Save to BytesIO
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        logging.info(f"Success! Added {links_added} navigation links")
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='document_with_navigation.pdf'
        )
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
