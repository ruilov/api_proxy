import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

ALLOWED_APIS = {
    "metaculus": "https://www.metaculus.com/api2",
    "fred": "https://api.stlouisfed.org/fred/series",
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
