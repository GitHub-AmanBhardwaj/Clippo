from flask import Flask, render_template, request, jsonify
from yt_dlp import YoutubeDL
import re
import os
import time
import uuid
from urllib.parse import urlparse

# --- App Configuration ---
app = Flask(__name__)
# Vercel handles secrets via Environment Variables in the project settings
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default-secret-for-local-dev')
app.config['UPLOAD_FOLDER'] = '/tmp/static/downloads' # Vercel uses the /tmp directory for writable storage
app.config['MAX_FILE_AGE_SECONDS'] = 60 

# --- Setup ---
# Ensure the temporary download directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Helper Functions ---
def clean_filename(filename):
    """Remove invalid characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def is_valid_url(url):
    """Validate URL for Instagram."""
    try:
        parsed = urlparse(url)
        return all([parsed.scheme, parsed.netloc]) and 'instagram.com' in parsed.netloc
    except (ValueError, AttributeError):
        return False

def cleanup_old_files():
    """Delete files in UPLOAD_FOLDER older than MAX_FILE_AGE."""
    try:
        now = time.time()
        max_age = app.config['MAX_FILE_AGE_SECONDS']
        folder = app.config['UPLOAD_FOLDER']
        
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path):
                if (now - os.path.getmtime(file_path)) > max_age:
                    os.remove(file_path)
    except Exception as e:
        # In a production environment, you would log this error
        print(f"Error during cleanup: {e}")

# --- Routes ---
# Note: No need for home, about, or downloader routes if they are static HTML.
# Vercel will serve them automatically. If they use Jinja templating, keep them.

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/downloader/instagram')
def downloader():
    return render_template('downloader.html')

@app.route('/preview', methods=['POST'])
def preview():
    # ... (This function remains the same as your original)
    data = request.get_json()
    url = data.get('url')
    if not url or not is_valid_url(url):
        return jsonify({'error': 'Invalid Instagram URL'}), 400
    try:
        ydl_opts = {'format': 'best', 'quiet': True, 'no_warnings': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                'success': True,
                'title': info.get('title', 'Video Preview'),
                'url': info.get('url', '')
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    # Cleanup runs at the start of a download, which is reliable in a serverless environment
    cleanup_old_files()
    
    data = request.get_json()
    url = data.get('url')
    if not url or not is_valid_url(url):
        return jsonify({'error': 'Invalid Instagram URL'}), 400
    
    try:
        unique_id = str(uuid.uuid4())[:8]
        # Get video info first to create a clean filename
        with YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = clean_filename(info.get('title', 'video'))
            ext = info.get('ext', 'mp4')

        filename = f"{title}_{unique_id}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        ydl_opts = {
            'format': 'best',
            'outtmpl': filepath,
            'quiet': True,
            'no_warnings': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return jsonify({
            'success': True,
            # This URL will be handled by a new /serve route
            'url': f'/serve/{filename}',
            'title': info.get('title', 'Downloaded Video'),
            'expires_in_seconds': app.config['MAX_FILE_AGE_SECONDS']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# NEW ROUTE: To serve files from the /tmp directory
from flask import send_from_directory

@app.route('/serve/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
