# RETRO SUB — Vercel V2.2

Single-project YouTube caption tool using FastAPI + yt-dlp.

## Structure

- `app.py` — FastAPI backend and static frontend server
- `static/index.html` — retro CRT UI
- `requirements.txt` — Python dependencies

There is intentionally **no `vercel.json`**. Current Vercel FastAPI deployments are zero-config. The app is discovered from `app.py`, while the FastAPI app serves `static/index.html` with `StaticFiles`.

## Deploy

1. Create/use a Vercel project connected to this GitHub repository.
2. Replace the old files with the files in this ZIP.
3. Make sure `app.py` is in the repository ROOT.
4. Make sure `static/index.html` exists.
5. Commit/push to `main`.
6. Wait for Vercel deployment to become Ready.
7. Open the project root URL.

## Expected routes

- `/` → RETRO SUB interface
- `/api/health` → health JSON
- `/api/info` → inspect YouTube video and caption tracks
- `/api/caption` → extract selected caption

## Important

The app extracts captions that are available to the extractor. Availability can vary by video, language, region, YouTube changes, or anti-bot controls. Use downloaded material only when you have the right to use it.
