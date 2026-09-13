"""Headless UI checks. Start Vite on port 5175; run with backend's Python environment."""
import copy
import json
import os
import tempfile
import unittest

from playwright.sync_api import sync_playwright, expect


RUN = {
    "id": "ui-test", "url": "https://example.com", "task": "Find the pricing page",
    "status": "completed", "personas": ["first_time", "power_user"],
    "errors": {}, "session_viewer_urls": {}, "results": {},
}
for persona_id in RUN["personas"]:
    RUN["results"][persona_id] = {
        "success": True, "summary": "Found pricing", "score": 8,
        "steps": [{"step": 1, "action": "click", "reasoning": "The pricing link was difficult to find among the navigation options.",
                   "outcome": "ok", "screenshot_url": f"/runs/ui-test/{persona_id}/before"}],
    }
REVAMP = {
    "run_id": "ui-test", "status": "running", "total_images": 2, "completed_images": 0, "error": None,
    "images": [{"persona_id": persona_id, "step": 1, "reasoning": RUN["results"][persona_id]["steps"][0]["reasoning"],
                "original_screenshot_url": f"/runs/ui-test/{persona_id}/before", "fixed_screenshot_url": None,
                "status": "generating" if i == 0 else "pending", "error": None}
               for i, persona_id in enumerate(RUN["personas"])],
}


class ImprovementsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel=os.environ.get("TEST_BROWSER_CHANNEL", "msedge"), headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.revamp = None
        self.posts = 0
        self.expired = False
        self.post_error = False
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.route("**/api/**", self.api)
        self.page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        self.page.add_init_script(f"localStorage.setItem('persona-runs-v1', JSON.stringify({json.dumps([RUN])}));")
        self.page.goto("http://127.0.0.1:5175")
        self.page.get_by_role("button", name="View Find the pricing page", exact=True).click()
        self.page.get_by_role("button", name="Next: Improvements").click()

    def api(self, route):
        path = route.request.url.split("/api", 1)[1]
        if path.endswith("/revamp"):
            if self.expired:
                route.fulfill(status=404, json={"detail": "Run not found"})
            elif route.request.method == "POST":
                self.posts += 1
                if self.post_error:
                    route.fulfill(status=500, json={"detail": "Image generation is unavailable"})
                else:
                    self.revamp = copy.deepcopy(REVAMP)
                    route.fulfill(status=202, json=self.revamp)
            elif self.revamp:
                route.fulfill(json=self.revamp)
            else:
                route.fulfill(status=404, json={"detail": "Revamp not found"})
        elif path.endswith(("/before", "/after")):
            after = path.endswith("/after")
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="540"><rect width="800" height="540" fill="{ "#edf6e7" if after else "#f4f5f1" }"/><text x="45" y="75" font-family="sans-serif" font-size="30">Example website</text><rect x="45" y="120" width="710" height="50" rx="8" fill="#d3e4c9"/><text x="65" y="154" font-family="sans-serif" font-size="23">{ "Pricing · Easy to find" if after else "Home · About · More" }</text><rect x="45" y="220" width="450" height="230" rx="8" fill="white"/></svg>'
            route.fulfill(content_type="image/svg+xml", body=svg)
        elif path == "/personas":
            route.fulfill(json={p: {"id": p, "name": name, "description": "A visitor", "system_prompt": "Explore the site"}
                                for p, name in [("first_time", "First-Time User"), ("power_user", "Power User")]})
        else:
            route.fulfill(status=404, json={"detail": "Not found"})

    def ready(self, partial=False):
        self.revamp["status"] = "partial" if partial else "completed"
        self.revamp["completed_images"] = 1 if partial else 2
        for i, image in enumerate(self.revamp["images"]):
            if partial and i == 1:
                image.update(status="failed", error="Could not generate this image")
            else:
                image.update(status="completed", fixed_screenshot_url=f'/runs/ui-test/{image["persona_id"]}/after')

    def test_generate_progress_navigation_and_reopen(self):
        expect(self.page.get_by_text("2 screenshots", exact=True)).to_be_visible()
        self.assertEqual(self.posts, 0)
        self.page.get_by_role("button", name="Generate improvements", exact=True).click()
        expect(self.page.get_by_text("0 of 2 images ready", exact=True)).to_be_visible()
        self.page.get_by_role("button", name="Power User", exact=True).click()
        expect(self.page.get_by_text("Waiting for generation…", exact=True)).to_be_visible()
        self.ready()
        expect(self.page.get_by_text("2 of 2 images ready", exact=True)).to_be_visible(timeout=10000)
        expect(self.page.get_by_alt_text("Power User, step 1, proposed improvement", exact=True)).to_be_visible()
        self.page.locator(".modal").screenshot(path=os.path.join(tempfile.gettempdir(), "persona-improvements-desktop.png"))
        self.page.get_by_role("button", name="← Back to journey", exact=True).first.click()
        expect(self.page.get_by_role("heading", name="The user journey")).to_be_visible()
        self.page.get_by_role("button", name="Next: Improvements").click()
        expect(self.page.get_by_text("2 of 2 images ready", exact=True)).to_be_visible()
        expect(self.page.get_by_role("button", name="Generate improvements", exact=True)).to_have_count(0)
        self.assertEqual(self.posts, 1)
        self.page.get_by_role("button", name="Close dialog").click()
        self.page.get_by_role("button", name="View Find the pricing page", exact=True).click()
        expect(self.page.get_by_role("heading", name="The user journey")).to_be_visible()
        self.assertEqual(self.page_errors, [])

    def test_partial_results_and_mobile_layout(self):
        self.page.get_by_role("button", name="Generate improvements", exact=True).click()
        expect(self.page.get_by_text("0 of 2 images ready", exact=True)).to_be_visible()
        self.ready(partial=True)
        expect(self.page.get_by_text("Some improvements are ready", exact=True)).to_be_visible(timeout=10000)
        self.page.get_by_role("button", name="Power User", exact=True).click()
        expect(self.page.get_by_text("Could not generate this image", exact=True)).to_be_visible()
        self.page.set_viewport_size({"width": 390, "height": 844})
        figures = self.page.locator(".comparison-grid figure")
        before, after = figures.nth(0).bounding_box(), figures.nth(1).bounding_box()
        self.assertGreater(after["y"], before["y"])
        self.assertEqual(self.page.locator(".modal").evaluate("el => el.scrollWidth <= el.clientWidth"), True)
        self.page.locator(".modal").screenshot(path=os.path.join(tempfile.gettempdir(), "persona-improvements-mobile.png"))
        self.assertEqual(self.page_errors, [])

    def test_expired_run_cannot_generate(self):
        expect(self.page.get_by_role("button", name="Generate improvements", exact=True)).to_be_visible()
        self.page.get_by_role("button", name="← Back to journey", exact=True).click()
        self.expired = True
        self.page.get_by_role("button", name="Next: Improvements").click()
        expect(self.page.get_by_text("This run is no longer available on the server. Create a new test to generate improvements.")).to_be_visible()
        expect(self.page.get_by_role("button", name="Generate improvements", exact=True)).to_have_count(0)
        self.assertEqual(self.posts, 0)

    def test_generation_error_can_be_checked_and_retried(self):
        self.post_error = True
        self.page.get_by_role("button", name="Generate improvements", exact=True).click()
        expect(self.page.get_by_text("Image generation is unavailable", exact=True)).to_be_visible()
        self.post_error = False
        self.page.get_by_role("button", name="Check again", exact=True).click()
        self.page.get_by_role("button", name="Generate improvements", exact=True).click()
        expect(self.page.get_by_text("0 of 2 images ready", exact=True)).to_be_visible()
        self.assertEqual(self.posts, 2)


if __name__ == "__main__":
    unittest.main()
