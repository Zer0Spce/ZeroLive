import tempfile
from pathlib import Path
import unittest

from zerolive.app import Collector, Entry, best_logo, clean_name, discover_hls, event_links, render_m3u
from zerolive.thumbnails import create_thumbnail


class ZeroLiveTests(unittest.TestCase):
    def test_clean_brand(self):
        self.assertEqual(clean_name("ROXIESTREAMS - Celtics vs Pistons | Stream 2"),
                         "Celtics vs. Pistons")

    def test_source_direct(self):
        html = '''<video><source src="https://cdn.example.org/abc/master.m3u8?token=ok"></video>
        <script>const ignored = "https://cdn.example.org/video.mp4";</script>'''
        self.assertEqual(discover_hls(html, "https://example.com"),
                         ["https://cdn.example.org/abc/master.m3u8?token=ok"])

    def test_src_from_js_escaped(self):
        html = r'<script>const u="https:\/\/cdn.example.org\/live.m3u8";</script>'
        self.assertIn("https://cdn.example.org/live.m3u8", discover_hls(html, "https://example.com"))

    def test_event_links(self):
        html = '<table><tr><td><a href="/ppv-streams-1">WWE NXT</a></td></tr></table>'
        self.assertEqual(event_links(html, "https://roxiestreams.info/", {"roxiestreams.info"}),
                         [("https://roxiestreams.info/ppv-streams-1", "WWE NXT")])

    def test_logo_meta(self):
        html = '<meta property="og:image" content="/thumb/event.jpg">'
        self.assertEqual(best_logo(html, "https://site.example/event"),
                         "https://site.example/thumb/event.jpg")

    def test_m3u_mirrors(self):
        streams = [Entry("NBA Finals", "https://a.example/one.m3u8", "NBA", "https://logo.example/nba.jpg", "https://site.example/a"),
                   Entry("NBA Finals", "https://a.example/two.m3u8", "NBA", "https://logo.example/nba.jpg", "https://site.example/a")]
        output = render_m3u(streams)
        self.assertIn("NBA Finals | Stream 1", output)
        self.assertIn("NBA Finals | Stream 2", output)
        self.assertEqual(output.count("#EXTINF"), 2)
        self.assertNotIn("roxiestreams", output.lower())


    def test_collector_fixture(self):
        base = "https://roxiestreams.info"
        page = base + "/ppv-streams-1"
        fixtures = {
            base + "/": '<table><tr><td><a href="/ppv-streams-1">NBA Finals</a></td></tr></table>',
            page: '<video src="https://cdn.example.org/nba.m3u8"></video>',
        }
        collector = Collector([base], ["/"], validate=False)
        collector.fetch = lambda url: fixtures.get(url, "")
        entries, count = collector.collect({})
        self.assertEqual(count, 1)
        self.assertEqual(entries[0].title, "NBA Finals")
        self.assertEqual(entries[0].url, "https://cdn.example.org/nba.m3u8")

    def test_generated_thumbnail(self):
        with tempfile.TemporaryDirectory() as dirname:
            image_url = create_thumbnail("Chicago Cubs vs. New York Yankees", "MLB", "cubs-yankees", Path(dirname))
            self.assertTrue(Path(dirname, "cubsyankees.png").is_file())
            self.assertTrue(image_url.endswith("/cubsyankees.png"))


if __name__ == "__main__":
    unittest.main()
