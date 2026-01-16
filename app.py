from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__, template_folder=".")
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
