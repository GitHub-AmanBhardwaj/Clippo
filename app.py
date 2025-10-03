from flask import Flask, render_template, request, jsonify
from yt_dlp import YoutubeDL
import re
import os
import time
import uuid
import threading
import logging
from urllib.parse import urlparse

# --- App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'static/downloads'
app.config['MAX_FILE_AGE_SECONDS'] = 60  # CHANGED: Set back to 60 seconds as requested
app.config['CLEANUP_INTERVAL_SECONDS'] = 30 # NEW: Run cleanup every 30 seconds for faster deletion

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def setup_app():
    """Ensure necessary folders and background tasks are set up."""
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # NEW: Start the background cleanup task as a daemon thread
    cleanup_thread = threading.Thread(target=background_cleanup_task, daemon=True)
    cleanup_thread.start()
    logging.info(f"Background cleanup task started. Will run every {app.config['CLEANUP_INTERVAL_SECONDS']} seconds.")

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
        
        logging.info("Running scheduled file cleanup...")
        deleted_count = 0
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path):
                if (now - os.path.getmtime(file_path)) > max_age:
                    try:
                        os.remove(file_path)
                        logging.info(f"Deleted old file: {filename}")
                        deleted_count += 1
                    except Exception as e:
                        logging.error(f"Error deleting file {file_path}: {e}")
        logging.info(f"Cleanup finished. Deleted {deleted_count} file(s).")
    except Exception as e:
        logging.error(f"An error occurred during the cleanup process: {e}")

def background_cleanup_task():
    """NEW: This function runs in the background to periodically clean up old files."""
    while True:
        time.sleep(app.config['CLEANUP_INTERVAL_SECONDS'])
        cleanup_old_files()

# --- Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html', platform='Instagram')

@app.route('/downloader/instagram')
def downloader():
    return render_template('downloader.html', platform='Instagram')

@app.route('/preview', methods=['POST'])
def preview():
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
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'url': info.get('url', '')
            })
    except Exception as e:
        logging.error(f"Error in /preview for URL {url}: {e}")
        return jsonify({'error': 'Could not fetch video preview.'}), 500

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    
    if not url or not is_valid_url(url):
        return jsonify({'error': 'Invalid Instagram URL'}), 400
    
    try:
        unique_id = str(uuid.uuid4())[:8]
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(app.config['UPLOAD_FOLDER'], f'video_{unique_id}_%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = os.path.basename(ydl.prepare_filename(info))
            
            return jsonify({
                'success': True,
                'url': f'/static/downloads/{filename}',
                'title': info.get('title', 'Downloaded Video'),
                'expires_in_seconds': app.config['MAX_FILE_AGE_SECONDS'] # For frontend timer
            })
    except Exception as e:
        logging.error(f"Error in /download for URL {url}: {e}")
        return jsonify({'error': 'Could not process the video download.'}), 500

if __name__ == '__main__':
    setup_app()
    app.run(debug=True)