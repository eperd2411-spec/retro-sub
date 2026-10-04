# RETRO SUB — Vercel Edition v2.1

YouTube caption downloader with retro CRT UI, FastAPI + yt-dlp.

## Deploy to Vercel

Upload this project to GitHub and import the repository into Vercel.

Important: `index.html` must be in the project root and `api/index.py` must remain under `api/`.

The included `vercel.json` explicitly routes `/api/*` to the Python function and all other paths to `index.html`. This prevents the FastAPI health/root response from replacing the frontend.

## Test

- `/` → Retro SUB UI
- `/api/health` → JSON health response
