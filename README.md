# RETRO SUB — Vercel Edition

YouTube caption extractor with a retro CRT interface. Frontend and FastAPI/yt-dlp backend live in one Vercel project.

## Deploy (easiest)
1. Create/login to a Vercel account and create a new project from this folder/repository.
2. No build command is required. Keep the project root at the folder containing `index.html`, `requirements.txt`, `vercel.json`, and `api/index.py`.
3. Deploy.
4. Open the generated URL and paste a YouTube URL.

## GitHub method
Upload the contents of this folder to a new GitHub repository, then in Vercel choose **Add New → Project → Import** that repository. Deploy with the default settings.

## Files
- `index.html` — retro UI
- `api/index.py` — FastAPI endpoints and yt-dlp caption extraction
- `requirements.txt` — Python dependencies
- `vercel.json` — Python Function configuration (300-second maximum on Hobby)

## API
- `GET /api/health`
- `POST /api/info` with `{ "url": "..." }`
- `POST /api/caption` with `{ "url": "...", "lang": "en", "kind": "auto|manual", "fmt": "srt|vtt|txt" }`

## Important
This tool extracts caption tracks that are available to the downloader. Availability and successful extraction can change when YouTube changes its delivery or anti-bot systems. It does not download the video itself.
