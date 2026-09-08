import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from kdpniche.config import Settings
from kdpniche.server import serve


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings()
        settings.data_dir = tempfile.mkdtemp(prefix="kdpniche-api-")
        settings.offline = True
        settings.request_delay = 0
        cls.httpd = serve("127.0.0.1", 0, settings)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, response.read()

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())

    def test_health(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_markets(self):
        _, body = self.get("/api/markets")
        data = json.loads(body)
        self.assertTrue(any(m["code"] == "us" for m in data["markets"]))
        self.assertEqual(len(data["stores"]), 2)

    def test_index_and_assets_are_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"KDP Niche Finder", body)
        self.assertEqual(self.get("/app.js")[0], 200)
        self.assertEqual(self.get("/styles.css")[0], 200)

    def test_search_job_lifecycle_and_export(self):
        job = self.post("/api/search", {"seed": "journal", "offline": True, "limit": 6})["job"]
        run = None
        for _ in range(60):
            _, body = self.get("/api/job/" + job)
            payload = json.loads(body)
            if payload["status"] == "done":
                run = payload["run"]
                break
            self.assertNotEqual(payload["status"], "error", payload.get("error"))
            time.sleep(0.25)
        self.assertIsNotNone(run, "the search job never finished")
        self.assertTrue(run["niches"])
        self.assertEqual(run["source"], "demo")

        status, csv_body = self.get(f"/api/export?job={job}&format=csv")
        self.assertEqual(status, 200)
        self.assertIn("Keyword", csv_body.decode("utf-8-sig").splitlines()[0])

        keyword = run["niches"][0]["keyword"]
        status, books_csv = self.get(
            f"/api/export?job={job}&kind=books&keyword={urllib.parse.quote(keyword)}")
        self.assertEqual(status, 200)
        self.assertIn("Title", books_csv.decode("utf-8-sig"))

    def test_single_keyword_endpoint(self):
        report = self.post("/api/keyword", {"keyword": "dream journal", "offline": True})
        self.assertEqual(report["keyword"], "dream journal")
        self.assertGreater(len(report["books"]), 0)

    def test_shortlist_roundtrip(self):
        niche = self.post("/api/keyword", {"keyword": "prayer journal", "offline": True})
        self.post("/api/saved", {"niche": niche})
        _, body = self.get("/api/saved")
        saved = json.loads(body)["niches"]
        self.assertIn("prayer journal", [n["keyword"] for n in saved])
        self.post("/api/saved/delete", {"keyword": "prayer journal",
                                        "marketplace": niche["marketplace"],
                                        "store": niche["store"]})
        _, body = self.get("/api/saved")
        self.assertNotIn("prayer journal",
                         [n["keyword"] for n in json.loads(body)["niches"]])

    def test_missing_seed_is_rejected(self):
        try:
            self.post("/api/search", {"seed": "  "})
            self.fail("expected an HTTP 400")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_unknown_job(self):
        try:
            self.get("/api/job/nope")
            self.fail("expected an HTTP 404")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)


if __name__ == "__main__":
    unittest.main()
