# RETRO SUB V3.0

YouTube caption extractor with a **Browser Assist** fallback.

## Why V3?
YouTube can reject server/datacenter requests made by yt-dlp with:
`Sign in to confirm you're not a bot`.

V3 keeps the server extractor as a fallback, but adds a bookmarklet. The bookmarklet runs on the user's own YouTube page, reads the caption track exposed to that page, parses timestamps/text locally, then sends only caption data to RETRO SUB. No YouTube cookies or passwords are sent to the server.

## Files
- `app.py` — FastAPI API + browser-caption endpoint
- `static/index.html` — retro UI
- `static/bookmarklet.js` — Browser Assist extractor
- `requirements.txt`

## Deploy to Vercel
1. Replace the old files in the GitHub repo with these files.
2. Keep `app.py` at repository root.
3. Keep `static/index.html` and `static/bookmarklet.js`.
4. Do not add a `vercel.json` unless your project needs a custom configuration.
5. Commit/push. Vercel should redeploy automatically.

## Browser Assist
After deployment:
1. Open the RETRO SUB site.
2. Drag **RETRO SUB EXTRACT** to the browser bookmark bar.
3. Open a YouTube video.
4. Click the bookmark.
5. Choose a caption track.
6. A RETRO SUB window opens and receives the transcript.
7. Use Search / Copy / Download SRT, VTT or TXT.

The bookmarklet is generated dynamically from the current site origin, so it also works if you later use a custom domain.

## Security
The Browser Assist endpoint receives caption text/timestamps only. Do not add a YouTube cookies upload feature to a public server. YouTube cookies can be sensitive authentication material.

## Limitations
- Browser Assist requires captions to be available on the YouTube video page.
- YouTube UI/player internals can change over time.
- If a video has no captions, the extractor cannot create them.
