from flask import Flask, request, jsonify, send_file, render_template, after_this_request
from flask_cors import CORS
import yt_dlp
import os
import re
import tempfile
import threading
import uuid
import shutil

app = Flask(__name__, template_folder=".")
CORS(app)

# Store download progress and file paths
download_progress = {}

# Create a temp directory for downloads that persists across requests
TEMP_DOWNLOADS_DIR = tempfile.mkdtemp(prefix='vidgrab_')

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
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Get video formats with both video and audio
            formats = []
            seen_resolutions = set()

            for f in info.get('formats', []):
                # Get formats that have video
                if f.get('vcodec') != 'none' and f.get('height'):
                    resolution = f'{f["height"]}p'
                    format_id = f.get('format_id', '')
                    ext = f.get('ext', 'mp4')
                    filesize = f.get('filesize') or f.get('filesize_approx', 0)

                    # Create a unique key for this resolution
                    key = f"{resolution}_{ext}"

                    if key not in seen_resolutions:
                        seen_resolutions.add(key)
                        formats.append({
                            'format_id': format_id,
                            'resolution': resolution,
                            'height': f['height'],
                            'ext': ext,
                            'filesize': filesize,
                            'has_audio': f.get('acodec') != 'none'
                        })

            # Sort by resolution (height) descending
            formats.sort(key=lambda x: x['height'], reverse=True)

            # Remove duplicates keeping best quality per resolution
            unique_formats = []
            seen_heights = set()
            for f in formats:
                if f['height'] not in seen_heights:
                    seen_heights.add(f['height'])
                    unique_formats.append(f)

            return jsonify({
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('channel', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': unique_formats[:8]  # Limit to top 8 formats
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download a video with the specified format."""
    data = request.json
    url = data.get('url', '')
    resolution = data.get('resolution', '720')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # Create a unique download ID
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
            'format': f'bestvideo[height<={resolution}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]',
            'outtmpl': os.path.join(TEMP_DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'progress_hooks': [progress_hook],
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Handle merged format extension
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
        return jsonify({'error': str(e)}), 400

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
        # Clean up the temp file after sending
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            # Clean up the progress entry
            download_progress.pop(download_id, None)
        except Exception:
            pass
        return response

    return send_file(filepath, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
