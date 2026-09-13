import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


ORIGIN = "https://persona-agents-nu.vercel.app"


class CorsTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(main.app))

    def test_frontend_json_preflights(self):
        for path, method in (("/personas", "GET"), ("/runs", "POST")):
            with self.subTest(path=path):
                response = self.client.options(path, headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "content-type",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
                self.assertIn(method, response.headers["access-control-allow-methods"])
                self.assertIn("content-type", response.headers["access-control-allow-headers"].lower())

    def test_personas_response_can_be_read_by_frontend(self):
        response = self.client.get("/personas", headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
        self.assertIn("first_time", response.json())

    def test_launch_response_has_cors_headers_without_starting_real_agents(self):
        with patch.dict(main.RUNS, {}, clear=True), patch.object(main, "execute_run") as execute:
            response = self.client.post("/runs", headers={"Origin": ORIGIN}, json={
                "url": "https://example.com", "task": "Find pricing", "personas": ["first_time"],
            })
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
            execute.assert_called_once()

    def test_api_errors_remain_readable(self):
        response = self.client.post("/runs", headers={"Origin": ORIGIN}, json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)

    def test_unlisted_origin_is_not_allowed(self):
        response = self.client.options("/runs", headers={
            "Origin": "https://unrelated.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_local_requests_still_work(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.get("/personas", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
