import unittest

from zerolive.app import Entry, best_logo, clean_name, discover_hls, event_links, render_m3u


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


if __name__ == "__main__":
    unittest.main()
