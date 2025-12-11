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
        "version": "1.0",
        "usage": "POST to /add-navigation with pdf_url"
    })

@app.route('/add-navigation', methods=['POST'])
def add_navigation():
    try:
        data = request.json
        pdf_url = data.get('pdf_url')
        
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
        
        # TOC items (customize Y positions as needed)
        toc_items = data.get('toc_items', [
            {"y": 650, "page": 1},
            {"y": 590, "page": 2},
            {"y": 530, "page": 3},
            {"y": 470, "page": 4},
            {"y": 410, "page": 5},
            {"y": 350, "page": 6},
            {"y": 290, "page": 7}
        ])
        
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
                link[NameObject("/Rect")] = ArrayObject([
                    NumberObject(50),
                    NumberObject(item["y"]),
                    NumberObject(550),
                    NumberObject(item["y"] + 35)
                ])
                link[NameObject("/Border")] = ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ])
                
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
                
                logging.info(f"Added link to page {target_page}")
        
        # Add all pages to writer
        writer.add_page(toc_page)
        for i in range(1, page_count):
            writer.add_page(reader.pages[i])
        
        # Save to BytesIO
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        logging.info(f"Success! Added {links_added} links")
        
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
```

Click **"Commit new file"**

---

### **File 2: `requirements.txt`**

**Filename:** `requirements.txt`

**Content:**
```
flask==3.0.0
pypdf==3.17.0
requests==2.31.0
gunicorn==21.2.0
```

Click **"Commit new file"**

---

## **Step 3: Deploy to Render.com**

### **3.1: Sign Up**
1. Go to https://render.com
2. Click **"Get Started"**
3. Sign up with **GitHub**
4. Authorize Render

---

### **3.2: Create Web Service**
1. Click **"New +"**
2. Select **"Web Service"**
3. Find your `pdf-toc-navigation` repo
4. Click **"Connect"**

---

### **3.3: Configure**

**Name:** `pdf-navigation` (or any name)

**Region:** Choose closest to you

**Branch:** `main`

**Runtime:** `Python 3`

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
gunicorn app:app
```

**Instance Type:** `Free` ✅

Click **"Create Web Service"**

---

### **3.4: Wait for Deploy**

Watch the logs. In 2-5 minutes you'll see:
```
==> Build successful
==> Starting service
==> Your service is live at https://pdf-navigation-xxxx.onrender.com
```

**Copy that URL!**

---

## **Step 4: Update Your n8n Workflow**

### **Updated Flow:**
```
1. Formatting Agent
   → Creates HTML TOC
   
2. Cleanup Agent
   → Cleans HTML
   
3. PDF.co: HTML → PDF
   → Output: { "url": "toc.pdf" }
   
4. PDF.co: Merge
   → Merges TOC + Original
   → Output: { "url": "merged.pdf" }
   
5. HTTP Request: Your Python API ← NEW!
   → Adds clickable navigation
   → Output: Final PDF with working links ✅
