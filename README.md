# ZeroLive

Automated M3U playlist generator for **public, directly playable HLS feeds** linked by event pages, with hourly GitHub Actions refreshes. The default discovery sources are `roxiestreams.info`, `roxiestreams.biz`, and `roxiestreams.su`.

> This project does not provide or guarantee access to third-party broadcasts. Only process streams you have permission to access and republish. It does not bypass DRM, passwords, paywalls, signed-token requirements, or geoblocks. An event webpage is not an IPTV-compatible stream.

## What it does
- Discovers event pages across three mirror domains.
- Extracts **direct .m3u8 URLs only**, checks for a valid `#EXTM3U` HLS response, and skips broken URLs.
- Cleans titles (including removal of `Roxiestreams`), groups them by sport, and labels multiple feeds `Stream 1`, `Stream 2`.
- Deduplicates identical feeds found on multiple mirror sites.
- Adds per-event thumbnails from page metadata and manual `tvg-logo` overrides; generates original 640x360 PNG posters when an event has no supplied art.
- Publishes `playlist.m3u` and `data/manifest.json` using GitHub Actions every hour, keeping the previous playlist on failed discovery.

## Run
Visit **Actions → Refresh ZeroLive playlist → Run workflow**. After a successful refresh, the playlist URL is:

`https://raw.githubusercontent.com/Zer0Spce/ZeroLive/main/playlist.m3u`

GitHub's scheduled job runs at minute 7 of each UTC hour, subject to GitHub Actions scheduling delays. To allow automatic commits, configure **Settings → Actions → General → Workflow permissions → Read and write permissions** if needed.

**There is no functional playlist until an actual run verifies direct HLS URLs.** Event schedules and numbered website player buttons are not themselves direct stream feeds.

## Local setup
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m zerolive
```

Edit `config/sources.json` to set mirror domains, discovery paths and timeouts. Edit `config/logo_overrides.json` to assign an event-specific `tvg-logo`. The supplied Celtics vs Pistons thumbnail URL has been configured for that exact matchup, not for unrelated events.

## Limitations and rights
Only public HTML and documented video/source attributes or regular script URLs are inspected. This does not intercept private player traffic or bypass authentication, DRM, signed tokens, or paywalls. Some players require JavaScript or headers unavailable to ordinary IPTV players, so they cannot be added reliably. Use only feeds and third-party artwork you are authorized to redistribute.
