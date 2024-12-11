from flask import Flask, request, jsonify, render_template_string
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from pyzbar.pyzbar import decode
from PIL import Image
import json
import time
import requests
import os

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Barcode Scanner</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 16px;
            background: #f0f0f0;
        }
        .button {
            width: 100%;
            padding: 16px;
            margin: 8px 0;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            display: block;
        }
        .primary {
            background: #007AFF;
            color: white;
        }
        .secondary {
            background: #ffffff;
            color: #007AFF;
            border: 1px solid #007AFF;
        }
        #barcodeInput {
            width: 100%;
            padding: 12px;
            margin: 8px 0;
            border: 1px solid #ccc;
            border-radius: 8px;
            font-size: 16px;
            display: none;
        }
        .history-item {
            background: white;
            border-radius: 12px;
            padding: 16px;
            margin: 8px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .history-title {
            font-size: 18px;
            font-weight: 600;
            margin: 24px 0 12px 0;
        }
        #fileInput {
            display: none;
        }
        .loading {
            text-align: center;
            padding: 20px;
            display: none;
        }
        .location-info {
            margin-top: 8px;
            font-size: 14px;
            color: #666;
        }
        .warehouse {
            margin-top: 4px;
            padding-left: 12px;
        }
        .location {
            color: #007AFF;
            font-size: 14px;
            margin-left: 8px;
        }
        .scan-active {
            background: #32CD32;
        }
    </style>
</head>
<body>
    <input type="text" id="barcodeInput" placeholder="Ready for barcode scan...">
    <input type="file" id="fileInput" accept="image/*" multiple>
    <button id="scanButton" class="button primary">SCAN ITEM</button>
    <button onclick="handlePhotos()" class="button secondary">Take/Upload Photos</button>
    <div id="loading" class="loading">Processing...</div>
    <div class="history-title">Scan History</div>
    <div id="scanHistory"></div>

    <script>
        let isScanning = false;
        const scanButton = document.getElementById('scanButton');
        const barcodeInput = document.getElementById('barcodeInput');

        scanButton.addEventListener('click', () => {
            isScanning = !isScanning;
            if (isScanning) {
                barcodeInput.style.display = 'block';
                scanButton.classList.add('scan-active');
                barcodeInput.focus();
            } else {
                barcodeInput.style.display = 'none';
                scanButton.classList.remove('scan-active');
            }
        });

        barcodeInput.addEventListener('keyup', async (e) => {
            if (e.key === 'Enter' && barcodeInput.value) {
                const barcode = barcodeInput.value;
                document.getElementById('loading').style.display = 'block';
                
                try {
                    const response = await fetch('/scan-barcode', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ barcode: barcode })
                    });
                    
                    const result = await response.json();
                    updateScanHistory([result]);
                } catch (error) {
                    alert('Error processing barcode: ' + error);
                } finally {
                    document.getElementById('loading').style.display = 'none';
                    barcodeInput.value = '';
                }
            }
        });

        function handlePhotos() {
            document.getElementById('fileInput').click();
        }

        document.getElementById('fileInput').addEventListener('change', async (event) => {
            const loading = document.getElementById('loading');
            loading.style.display = 'block';
            
            const formData = new FormData();
            Array.from(event.target.files).forEach((file) => {
                formData.append('files', file);
            });

            try {
                const response = await fetch('/scan', {
                    method: 'POST',
                    body: formData
                });
                
                const results = await response.json();
                updateScanHistory(results);
            } catch (error) {
                alert('Error processing image: ' + error);
            } finally {
                loading.style.display = 'none';
                event.target.value = '';
            }
        });

        function updateScanHistory(results) {
            const historyDiv = document.getElementById('scanHistory');
            
            results.forEach(result => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'history-item';
                
                if (result.error === 'Item not found') {
                    itemDiv.innerHTML = `
                        <div><strong>Barcode:</strong> ${result.barcode}</div>
                        <div class="not-found">Product Not Found</div>
                    `;
                } else {
                    let warehouseHtml = '<div class="warehouse-locations">';
                    if (result.warehouses && result.warehouses.length > 0) {
                        result.warehouses.forEach(wh => {
                            warehouseHtml += `
                                <div class="warehouse">
                                    <strong>${wh.store_name}</strong>: QOH: ${wh.qoh}, QA: ${wh.qa}
                                    ${wh.location ? `<br><span class="location">${wh.location}</span>` : ''}
                                </div>`;
                        });
                    } else {
                        warehouseHtml += '<div>No location data available</div>';
                    }
                    warehouseHtml += '</div>';

                    itemDiv.innerHTML = `
                        <div><strong>Barcode:</strong> ${result.barcode}</div>
                        <div><strong>U/M Match:</strong> ${result.item_name}</div>
                        <div><strong>QOH:</strong> ${result.total_qoh}</div>
                        <div class="warehouse-info">
                            <strong>Warehouse Locations:</strong>
                            ${warehouseHtml}
                        </div>
                    `;
                }
                
                historyDiv.insertBefore(itemDiv, historyDiv.firstChild);
            });
        }
    </script>
</body>
</html>
"""

@app.route('/scan-barcode', methods=['POST'])
def scan_barcode_direct():
    data = request.json
    barcode = data.get('barcode', '').lstrip('0')
    item_data = erp.search_item(barcode)
    return jsonify(item_data)

class ERPConnector:
    def __init__(self):
        self.base_url = "https://erp.szwholesale.net"
        self.bearer_token = None
        
    def authenticate(self, username, password):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        print("Starting authentication process...")
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            print("Accessing login page...")
            driver.get(f"{self.base_url}/user/login")
            wait = WebDriverWait(driver, 10)
            
            username_field = wait.until(EC.presence_of_element_located((By.ID, "normal_login_username")))
            username_field.send_keys(username)
            
            password_field = driver.find_element(By.ID, "normal_login_password")
            password_field.send_keys(password)
            
            print("Submitting login...")
            login_button = driver.find_element(By.CLASS_NAME, "login-form-button")
            login_button.click()
            time.sleep(3)
            
            print("Getting bearer token...")
            driver.get(f"{self.base_url}/items")
            time.sleep(2)
            
            logs = driver.get_log("performance")
            for entry in logs:
                try:
                    log = json.loads(entry["message"])["message"]
                    if "Network.requestWillBeSent" in log["method"]:
                        headers = log["params"]["request"].get("headers", {})
                        if "Authorization" in headers and "Bearer" in headers["Authorization"]:
                            self.bearer_token = headers["Authorization"].split(" ")[1]
                            print("Authentication successful!")
                            return True
                except Exception as e:
                    print(f"Error parsing log entry: {e}")
                    continue
                    
            print("Failed to retrieve bearer token")
            return False
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return False
        finally:
            driver.quit()
    
    def search_item(self, barcode):
        if not self.bearer_token:
            return {"error": "Not authenticated"}
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {self.bearer_token}",
            "action-name": "PAGE_VIEW",
            "app-code": "ERP",
            "screen-name": "ERP_ITEM_LIST_PAGE"
        }
        
        try:
            # Try first search with original barcode
            response = requests.get(
                f"{self.base_url}/api/index-item",
                headers=headers,
                params={
                    "keyword": barcode,
                    "page": 1,
                    "per_page": 15
                }
            )
            search_data = response.json()
            print(f"Initial search response: {search_data}")
            
            # If no results and barcode doesn't start with 0, try with leading zero
            if (not search_data.get("data", {}).get("data") and 
                not barcode.startswith('0')):
                barcode_with_zero = '0' + barcode
                print(f"Trying with leading zero: {barcode_with_zero}")
                response = requests.get(
                    f"{self.base_url}/api/index-item",
                    headers=headers,
                    params={
                        "keyword": barcode_with_zero,
                        "page": 1,
                        "per_page": 15
                    }
                )
                search_data = response.json()
                print(f"Second search response: {search_data}")
                if search_data.get("data", {}).get("data"):
                    barcode = barcode_with_zero  # Use the successful barcode for the rest of the process
            
            if (search_data.get("status") == "success" and 
                search_data.get("data", {}).get("data") and 
                len(search_data["data"]["data"]) > 0):
                
                item = search_data["data"]["data"][0]
                item_id = item["item_id"]
                
                # Get item details first
                item_headers = {
                    "accept": "application/json, text/plain, */*",
                    "action-name": "PAGE_VIEW",
                    "app-code": "ERP",
                    "authorization": f"Bearer {self.bearer_token}",
                    "screen-name": "ERP_ITEM_EDIT_PAGE",
                    "screen-url": f"{self.base_url}/edit-item/{item_id}"
                }
                
                # Get item details which contains the variety_id
                item_response = requests.get(
                    f"{self.base_url}/api/items/{item_id}",
                    headers=item_headers
                )
                item_data = item_response.json()
                
                print(f"Item details response: {item_data}")
                
                if item_data.get("status") == "success":
                    variety_id = item_data["data"]["variety_id"]
                    
                    # Now get variety details with locations
                    variety_headers = {
                        "accept": "application/json, text/plain, */*",
                        "action-name": "PAGE_VIEW",
                        "app-code": "ERP",
                        "authorization": f"Bearer {self.bearer_token}",
                        "screen-name": "ERP_ITEM_EDIT_PAGE",
                        "screen-url": f"{self.base_url}/edit-item/{item_id}"
                    }
                    
                    variety_response = requests.get(
                        f"{self.base_url}/api/varieties/{variety_id}",
                        headers=variety_headers
                    )
                    variety_data = variety_response.json()
                    
                    print(f"Variety data response: {variety_data}")
                    
                    if variety_data.get("status") == "success":
                        warehouse_info = []
                        # Get locations from item_data first since it has the detailed location info
                        for loc in item_data["data"]["item_locations"]:
                            location_place = loc["location_places"][0] if loc["location_places"] else {}
                            location_str = ""
                            if location_place:
                                parts = []
                                if location_place.get("aisle"): parts.append(f"Aisle: {location_place['aisle']}")
                                if location_place.get("bay"): parts.append(f"Bay: {location_place['bay']}")
                                if location_place.get("shelf"): parts.append(f"Shelf: {location_place['shelf']}")
                                if location_place.get("slot"): parts.append(f"Slot: {location_place['slot']}")
                                location_str = " | ".join(parts) if parts else "No specific location"
                            
                            warehouse_info.append({
                                "store_name": loc["store_name"],
                                "qoh": loc["qoh"],
                                "qa": loc["qa"],
                                "location": location_str
                            })
                        
                        return {
                            "barcode": barcode,
                            "item_name": item["item_name"],
                            "total_qoh": item["qoh"],
                            "warehouses": warehouse_info
                        }
                
            return {"error": "Item not found"}
            
        except Exception as e:
            print(f"Error in search_item: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {"error": str(e)}

# Create global ERP connector instance
erp = ERPConnector()

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/scan', methods=['POST'])
def scan_barcode():
    if 'files' not in request.files:
        print("No files in request")
        return jsonify({"error": "No files uploaded"}), 400

    results = []
    files = request.files.getlist('files')
    
    for file in files:
        try:
            print(f"Processing file: {file.filename}")
            image = Image.open(file.stream)
            barcodes = decode(image)
            
            print(f"Found barcodes: {barcodes}")
            
            for barcode in barcodes:
                code = barcode.data.decode('utf-8').lstrip('0')
                print(f"Processed barcode: {code}")
                item_data = erp.search_item(code)
                
                if "error" in item_data:
                    # Include the barcode in not found results
                    results.append({
                        "barcode": code,
                        "error": "Item not found"
                    })
                else:
                    results.append(item_data)
                
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            print(traceback.format_exc())
            continue

    print(f"Returning results: {results}")
    return jsonify(results)

def initialize_erp():
    print("\nERP System Initialization")
    print("-----------------------")
    username = input("Enter your ERP username: ")
    password = input("Enter your ERP password: ")
    
    if erp.authenticate(username, password):
        print("\nInitialization successful! Server is ready.")
        return True
    else:
        print("\nInitialization failed. Please check your credentials.")
        return False

if __name__ == '__main__':
    print("\nStarting Barcode Scanner Server...")
    while not initialize_erp():
        print("\nRetrying authentication...")
    
    print("\nStarting web server on port 5000...")
    import os
app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

