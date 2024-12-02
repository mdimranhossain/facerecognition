import os
import requests
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from deepface import DeepFace
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
SCRAPED_FOLDER = 'scraped_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SCRAPED_FOLDER'] = SCRAPED_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SCRAPED_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Check if the file has a valid extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def search_google_images(query, count=5):
    """
    Search for images using Google Custom Search API.
    """
    api_key = os.getenv('GOOGLE_API_KEY')
    cx = os.getenv('GOOGLE_CX')
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "searchType": "image",
        "num": count,
    }
    response = requests.get(search_url, params=params)
    response.raise_for_status()

    # Extract image URLs
    results = response.json()
    return [item["link"] for item in results.get("items", [])]


def download_images(image_urls, folder):
    """
    Download images from URLs to a folder.
    """
    image_paths = []
    for idx, url in enumerate(image_urls):
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            file_path = os.path.join(folder, f"image_{idx}.jpg")
            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            image_paths.append(file_path)
        except Exception as e:
            print(f"Failed to download {url}: {e}")
    return image_paths


@app.route('/')
def home():
    """Render the home page."""
    return render_template('index.html')


@app.route('/verify', methods=['POST'])
def verify_person():
    """
    Verify the uploaded image against images fetched from Google.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    query = request.form.get('query')

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not query:
        return jsonify({'error': 'Query cannot be empty'}), 400

    if file and allowed_file(file.filename):
        # Save uploaded file
        filename = secure_filename(file.filename)
        uploaded_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(uploaded_path)

        try:
            # Fetch images from Google
            image_urls = search_google_images(query, count=5)
            print(f"Scraped image URLs: {image_urls}")  # Debugging log

            # Download images to local folder
            scraped_image_paths = download_images(image_urls, app.config['SCRAPED_FOLDER'])

            # Compare uploaded image with each scraped image
            matches = []
            for idx, img_path in enumerate(scraped_image_paths):
                try:
                    result = DeepFace.verify(img1_path=uploaded_path, img2_path=img_path)
                    matches.append({
                        'image': image_urls[idx],
                        'verified': result['verified'],
                        'distance': result['distance']
                    })
                except Exception as e:
                    print(f"DeepFace verification failed for {img_path}: {e}")

            # Cleanup files
            os.remove(uploaded_path)
            for path in scraped_image_paths:
                os.remove(path)

            return render_template('results.html', matches=matches)
        except Exception as e:
            os.remove(uploaded_path)
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Invalid file type'}), 400


if __name__ == '__main__':
    app.run(debug=True)
