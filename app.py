from flask import Flask, request, jsonify, render_template, send_file, after_this_request
from flask_cors import CORS
import yt_dlp
import os
import re
import tempfile
import uuid
import base64

app = Flask(__name__, template_folder=".")
CORS(app)

# Store download progress and file paths
download_progress = {}

# Create a temp directory for downloads
TEMP_DOWNLOADS_DIR = tempfile.mkdtemp(prefix='vidgrab_')

# Cookies file path - created from environment variable
COOKIES_FILE = os.path.join(TEMP_DOWNLOADS_DIR, 'cookies.txt')

def setup_cookies():
    """Setup cookies from environment variable if available."""
    cookies_b64 = os.environ.get('YOUTUBE_COOKIES_B64')
    if cookies_b64:
        try:
            cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
            with open(COOKIES_FILE, 'w') as f:
                f.write(cookies_content)
            print("Cookies file created from environment variable")
            return True
        except Exception as e:
            print(f"Failed to setup cookies: {e}")
    return False

# Setup cookies on startup
COOKIES_AVAILABLE = setup_cookies()

def get_ydl_opts():
    """Get yt-dlp options with cookies if available."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    if COOKIES_AVAILABLE and os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE

    return opts

def sanitize_filename(filename):
    """Remove invalid characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_video():
    """Analyze a YouTube video and return available formats."""
    data = request.json
    url = data.get('url', '')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        ydl_opts = get_ydl_opts()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            formats = []
            seen_heights = set()

            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('height'):
                    height = f['height']
                    if height not in seen_heights:
                        seen_heights.add(height)
                        formats.append({
                            'resolution': f'{height}p',
                            'height': height,
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        })

            formats.sort(key=lambda x: x['height'], reverse=True)

            return jsonify({
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('channel', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats[:8]
            })

    except Exception as e:
        error_msg = str(e)
        if 'Sign in to confirm' in error_msg:
            return jsonify({'error': 'YouTube cookies not configured. See setup instructions.'}), 400
        return jsonify({'error': error_msg}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download a video with the specified format."""
    data = request.json
    url = data.get('url', '')
    resolution = data.get('resolution', '720')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        download_id = str(uuid.uuid4())
        download_progress[download_id] = {'progress': 0, 'status': 'starting'}

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    download_progress[download_id]['progress'] = int((downloaded / total) * 100)
                download_progress[download_id]['status'] = 'downloading'
            elif d['status'] == 'finished':
                download_progress[download_id]['progress'] = 100
                download_progress[download_id]['status'] = 'finished'

        ydl_opts = {
            **get_ydl_opts(),
            'format': f'bestvideo[height<={resolution}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]',
            'outtmpl': os.path.join(TEMP_DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'progress_hooks': [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                filename = filename.rsplit('.', 1)[0] + '.mp4'

            download_progress[download_id]['filepath'] = filename
            download_progress[download_id]['status'] = 'complete'

            return jsonify({
                'success': True,
                'download_id': download_id,
                'filename': os.path.basename(filename)
            })

    except Exception as e:
        error_msg = str(e)
        if 'Sign in to confirm' in error_msg:
            return jsonify({'error': 'YouTube cookies not configured. See setup instructions.'}), 400
        return jsonify({'error': error_msg}), 400

@app.route('/api/progress/<download_id>')
def get_progress(download_id):
    """Get download progress."""
    if download_id in download_progress:
        return jsonify(download_progress[download_id])
    return jsonify({'error': 'Download not found'}), 404

@app.route('/api/file/<download_id>')
def serve_file(download_id):
    """Serve a downloaded file and clean up after."""
    if download_id not in download_progress:
        return jsonify({'error': 'Download not found'}), 404

    filepath = download_progress[download_id].get('filepath')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    filename = os.path.basename(filepath)

    @after_this_request
    def cleanup(response):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            download_progress.pop(download_id, None)
        except Exception:
            pass
        return response

    return send_file(filepath, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
