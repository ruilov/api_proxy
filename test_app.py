import unittest
from unittest.mock import MagicMock, patch

import requests

import app


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    @patch("app.requests.get")
    def test_generic_proxy_still_forwards_json(self, mock_get):
        upstream_response = MagicMock()
        upstream_response.json.return_value = {"ok": True}
        upstream_response.raise_for_status.return_value = None
        mock_get.return_value = upstream_response

        response = self.client.get("/proxy/fred/observations", query_string={"series_id": "DGS10"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        mock_get.assert_called_once_with(
            "https://api.stlouisfed.org/fred/series/observations",
            params=unittest.mock.ANY,
        )

    def test_barchart_requires_symbol(self):
        response = self.client.get("/proxy/barchart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Missing required query parameter: symbol"},
        )

    @patch("app.requests.Session")
    def test_barchart_returns_close_series(self, mock_session_cls):
        session = MagicMock()
        session.cookies.get.return_value = "token%20value"
        mock_session_cls.return_value = session

        bootstrap_response = MagicMock()
        bootstrap_response.raise_for_status.return_value = None
        history_response = MagicMock()
        history_response.raise_for_status.return_value = None
        history_response.text = (
            "symbol,tradingDay,open,high,low,close,volume\n"
            "CLM26,2026-03-17,67.1,68.0,66.8,67.5,100\n"
            "CLM26,2026-03-18,67.6,68.2,67.0,68.1,120\n"
        )
        session.get.side_effect = [bootstrap_response, history_response]

        response = self.client.get(
            "/proxy/barchart",
            query_string={
                "symbol": "CLM26",
                "data": "daily",
                "maxrecords": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "symbol": "CLM26",
                "params": {
                    "symbol": "CLM26",
                    "data": "daily",
                    "maxrecords": "2",
                },
                "series": [
                    {"date": "2026-03-17", "close": 67.5},
                    {"date": "2026-03-18", "close": 68.1},
                ],
            },
        )
        session.headers.update.assert_called_once_with({"User-Agent": app.BARCHART_USER_AGENT})
        session.get.assert_any_call(
            "https://www.barchart.com/futures/quotes/CLM26/overview",
            timeout=20,
        )
        session.get.assert_any_call(
            app.BARCHART_HISTORY_URL,
            params=[("symbol", "CLM26"), ("data", "daily"), ("maxrecords", "2")],
            headers={
                "X-XSRF-TOKEN": "token value",
                "Referer": "https://www.barchart.com/futures/quotes/CLM26/overview",
            },
            timeout=20,
        )

    @patch("app.requests.Session")
    def test_barchart_bootstrap_failure_returns_502(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        bootstrap_response = MagicMock()
        bootstrap_response.raise_for_status.side_effect = requests.HTTPError("boom")
        session.get.return_value = bootstrap_response

        response = self.client.get("/proxy/barchart", query_string={"symbol": "CLM26"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("Barchart bootstrap request failed", response.get_json()["error"])

    @patch("app.requests.Session")
    def test_barchart_missing_cookie_returns_502(self, mock_session_cls):
        session = MagicMock()
        session.cookies.get.return_value = None
        mock_session_cls.return_value = session

        bootstrap_response = MagicMock()
        bootstrap_response.raise_for_status.return_value = None
        session.get.return_value = bootstrap_response

        response = self.client.get("/proxy/barchart", query_string={"symbol": "CLM26"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json(),
            {"error": "Barchart bootstrap request failed: missing XSRF-TOKEN cookie"},
        )

    @patch("app.requests.Session")
    def test_barchart_history_failure_returns_502(self, mock_session_cls):
        session = MagicMock()
        session.cookies.get.return_value = "token"
        mock_session_cls.return_value = session

        bootstrap_response = MagicMock()
        bootstrap_response.raise_for_status.return_value = None
        history_response = MagicMock()
        history_response.raise_for_status.side_effect = requests.HTTPError("history boom")
        session.get.side_effect = [bootstrap_response, history_response]

        response = self.client.get("/proxy/barchart", query_string={"symbol": "CLM26"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("Barchart history request failed", response.get_json()["error"])

    def test_parse_barchart_close_series_maps_trading_day_and_close(self):
        series = app._parse_barchart_close_series(
            "close,tradingDay,volume\n"
            "70.25,2026-03-18,100\n"
            "71.50,2026-03-19,110\n"
        )

        self.assertEqual(
            series,
            [
                {"date": "2026-03-18", "close": 70.25},
                {"date": "2026-03-19", "close": 71.5},
            ],
        )

    @patch("app.requests.Session")
    def test_barchart_invalid_csv_returns_502(self, mock_session_cls):
        session = MagicMock()
        session.cookies.get.return_value = "token"
        mock_session_cls.return_value = session

        bootstrap_response = MagicMock()
        bootstrap_response.raise_for_status.return_value = None
        history_response = MagicMock()
        history_response.raise_for_status.return_value = None
        history_response.text = "symbol,tradeDate,lastPrice\nCLM26,2026-03-18,70.25\n"
        session.get.side_effect = [bootstrap_response, history_response]

        response = self.client.get("/proxy/barchart", query_string={"symbol": "CLM26"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("Barchart response parsing failed", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
