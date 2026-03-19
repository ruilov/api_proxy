import csv
import os
from io import StringIO
from urllib.parse import unquote

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ALLOWED_APIS = {
    "metaculus": "https://www.metaculus.com/api2",
    "fred": "https://api.stlouisfed.org/fred/series",
    "cme": "https://data.nasdaq.com/api/v3/datatables/",
}

BARCHART_HISTORY_URL = "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"
BARCHART_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _build_barchart_overview_url(symbol):
    return f"https://www.barchart.com/futures/quotes/{symbol}/overview"


def _get_forwarded_params():
    return list(request.args.items(multi=True))


def _serialize_params():
    serialized = {}
    for key, value in request.args.items(multi=True):
        existing = serialized.get(key)
        if existing is None:
            serialized[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            serialized[key] = [existing, value]
    return serialized


def _parse_barchart_close_series(csv_text):
    reader = csv.DictReader(StringIO(csv_text.strip()))
    if not reader.fieldnames or "tradingDay" not in reader.fieldnames or "close" not in reader.fieldnames:
        raise ValueError("Barchart response did not include tradingDay and close columns")

    series = []
    for row in reader:
        trading_day = row.get("tradingDay")
        close_value = row.get("close")
        if not trading_day or close_value in (None, ""):
            raise ValueError("Barchart response contained an incomplete row")

        try:
            close_price = float(close_value)
        except ValueError as exc:
            raise ValueError("Barchart response contained a non-numeric close value") from exc

        series.append({"date": trading_day, "close": close_price})

    if not series:
        raise ValueError("Barchart response did not contain any rows")

    return series


def _upstream_error(message):
    return jsonify({"error": message}), 502

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


@app.route("/proxy/barchart", methods=["GET"])
def proxy_barchart():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing required query parameter: symbol"}), 400

    overview_url = _build_barchart_overview_url(symbol)
    session = requests.Session()
    session.headers.update({"User-Agent": BARCHART_USER_AGENT})

    try:
        bootstrap_response = session.get(overview_url, timeout=20)
        bootstrap_response.raise_for_status()
    except requests.RequestException as exc:
        return _upstream_error(f"Barchart bootstrap request failed: {exc}")

    xsrf_token = session.cookies.get("XSRF-TOKEN")
    if not xsrf_token:
        return _upstream_error("Barchart bootstrap request failed: missing XSRF-TOKEN cookie")

    try:
        history_response = session.get(
            BARCHART_HISTORY_URL,
            params=_get_forwarded_params(),
            headers={
                "X-XSRF-TOKEN": unquote(xsrf_token),
                "Referer": overview_url,
            },
            timeout=20,
        )
        history_response.raise_for_status()
    except requests.RequestException as exc:
        return _upstream_error(f"Barchart history request failed: {exc}")

    try:
        series = _parse_barchart_close_series(history_response.text)
    except ValueError as exc:
        return _upstream_error(f"Barchart response parsing failed: {exc}")

    return jsonify(
        {
            "symbol": symbol,
            "params": _serialize_params(),
            "series": series,
        }
    )

@app.route("/")
def index():
    return jsonify({"message": "CORS Proxy is running."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
