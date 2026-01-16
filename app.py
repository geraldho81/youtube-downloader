from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re

app = Flask(__name__, template_folder=".")
CORS(app)

# Cobalt API endpoint (handles YouTube's bot detection)
COBALT_API = "https://api.cobalt.tools"

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
        # Use Cobalt API to get video info
        response = requests.post(
            COBALT_API,
            json={
                'url': url,
                'videoQuality': '1080',
                'filenameStyle': 'basic',
            },
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'error': 'Failed to analyze video'}), 400

        cobalt_data = response.json()

        # Cobalt returns a direct download URL or picker for multiple options
        # For simplicity, we'll offer common resolutions
        formats = [
            {'resolution': '2160p', 'height': 2160, 'quality': '4k'},
            {'resolution': '1440p', 'height': 1440, 'quality': '1440'},
            {'resolution': '1080p', 'height': 1080, 'quality': '1080'},
            {'resolution': '720p', 'height': 720, 'quality': '720'},
            {'resolution': '480p', 'height': 480, 'quality': '480'},
            {'resolution': '360p', 'height': 360, 'quality': '360'},
        ]

        # Extract video ID for thumbnail
        video_id = None
        if 'youtube.com' in url or 'youtu.be' in url:
            if 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[-1].split('?')[0]
            elif 'v=' in url:
                video_id = url.split('v=')[-1].split('&')[0]

        thumbnail = f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg' if video_id else ''

        return jsonify({
            'title': cobalt_data.get('filename', 'Video'),
            'thumbnail': thumbnail,
            'duration': 0,
            'channel': '',
            'view_count': 0,
            'formats': formats
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    """Get download URL for a video."""
    data = request.json
    url = data.get('url', '')
    resolution = data.get('resolution', '720')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # Request download from Cobalt
        response = requests.post(
            COBALT_API,
            json={
                'url': url,
                'videoQuality': str(resolution),
                'filenameStyle': 'basic',
            },
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'error': 'Failed to get download link'}), 400

        cobalt_data = response.json()

        # Cobalt returns different response types
        status = cobalt_data.get('status')

        if status == 'error':
            return jsonify({'error': cobalt_data.get('text', 'Unknown error')}), 400

        if status == 'redirect' or status == 'tunnel':
            # Direct download URL
            download_url = cobalt_data.get('url')
            filename = cobalt_data.get('filename', 'video.mp4')
            return jsonify({
                'success': True,
                'download_url': download_url,
                'filename': filename
            })

        if status == 'picker':
            # Multiple options available, get the video one
            picker = cobalt_data.get('picker', [])
            for item in picker:
                if item.get('type') == 'video':
                    return jsonify({
                        'success': True,
                        'download_url': item.get('url'),
                        'filename': 'video.mp4'
                    })
            # Fallback to first item
            if picker:
                return jsonify({
                    'success': True,
                    'download_url': picker[0].get('url'),
                    'filename': 'video.mp4'
                })

        return jsonify({'error': 'Could not get download URL'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5001)
