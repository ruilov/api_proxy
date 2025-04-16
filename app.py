from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Whitelisted APIs (base URLs only)
ALLOWED_APIS = {
    "metaculus": "https://www.metaculus.com/api2",
    "example": "https://api.example.com"
}

@app.route("/proxy/<api_name>/<path:endpoint>", methods=["GET"])
def proxy(api_name, endpoint):
    base_url = ALLOWED_APIS.get(api_name)
    if not base_url:
        return jsonify({"error": "API not allowed"}), 403

    full_url = f"{base_url}/{endpoint}"
    try:
        response = requests.get(full_url, params=request.args)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

@app.route("/")
def index():
    return jsonify({"message": "CORS Proxy is running."})
