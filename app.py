import os
import re
import html
import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="RETRO SUB", version="2.2")

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$",
    re.I,
)

class URLRequest(BaseModel):
    url: str

class CaptionRequest(BaseModel):
    url: str
    lang: str
    kind: str = "auto"  # auto or manual
    fmt: str = "srt"    # srt, vtt, txt

def validate_url(url: str) -> str:
    url = (url or "").strip()
    if not YOUTUBE_RE.match(url):
        raise HTTPException(status_code=400, detail="Masukkan URL YouTube yang valid.")
    return url

def base_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_args": {"youtube": {"player_client": ["web"]}},
    }

def track_list(info: dict):
    out = []
    seen = set()

    for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        for lang, tracks in (info.get(key) or {}).items():
            if lang in seen and kind == "auto":
                continue
            if not tracks:
                continue
            formats = sorted({(t.get("ext") or "").lower() for t in tracks if t.get("ext")})
            out.append({
                "lang": lang,
                "kind": kind,
                "formats": formats,
                "name": lang,
            })
            seen.add(lang)

    return out

def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def parse_vtt_to_segments(raw: str):
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", raw)
    segments = []

    for block in blocks:
        lines = [x.strip("\ufeff") for x in block.split("\n") if x.strip()]
        if not lines:
            continue

        time_idx = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if time_idx is None:
            continue

        timing = lines[time_idx]
        left, right = [x.strip() for x in timing.split("-->", 1)]

        def ts(v):
            v = v.split()[0]
            parts = v.replace(",", ".").split(":")
            try:
                if len(parts) == 3:
                    return int(float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]))
                if len(parts) == 2:
                    return int(float(parts[0]) * 60 + float(parts[1]))
                return int(float(parts[0]))
            except Exception:
                return 0

        start = ts(left)
        end = ts(right)
        text_lines = lines[time_idx + 1:]
        text = clean_text(" ".join(text_lines))
        if text:
            segments.append({"start": start, "end": end, "text": text})

    # Remove exact duplicate consecutive cues commonly produced by YouTube VTT.
    dedup = []
    for seg in segments:
        if not dedup or not (
            seg["text"] == dedup[-1]["text"]
            and seg["start"] == dedup[-1]["start"]
            and seg["end"] == dedup[-1]["end"]
        ):
            dedup.append(seg)
    return dedup

def segments_to_srt(segments):
    chunks = []
    for i, seg in enumerate(segments, 1):
        chunks.append(
            f"{i}\n{ass_time(seg['start'])} --> {ass_time(seg['end'])}\n{seg['text']}\n"
        )
    return "\n".join(chunks)

def segments_to_vtt(segments):
    chunks = ["WEBVTT", ""]
    for seg in segments:
        chunks.append(f"{ass_time(seg['start']).replace(',', '.')} --> {ass_time(seg['end']).replace(',', '.')}")
        chunks.append(seg["text"])
        chunks.append("")
    return "\n".join(chunks)

def get_info(url):
    opts = base_opts()
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

@app.get("/api/health")
def health():
    return {"ok": True, "service": "RETRO SUB", "version": "2.2"}

@app.post("/api/info")
def info(req: URLRequest):
    url = validate_url(req.url)
    try:
        data = get_info(url)
        return {
            "ok": True,
            "video": {
                "id": data.get("id"),
                "title": data.get("title") or "Untitled",
                "channel": data.get("channel") or data.get("uploader") or "",
                "duration": data.get("duration") or 0,
                "thumbnail": data.get("thumbnail") or "",
                "webpage_url": data.get("webpage_url") or url,
            },
            "captions": track_list(data),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal membaca video/caption: {str(e)[:500]}")

@app.post("/api/caption")
def caption(req: CaptionRequest):
    url = validate_url(req.url)
    lang = (req.lang or "").strip()
    kind = (req.kind or "auto").strip().lower()
    fmt = (req.fmt or "srt").strip().lower()

    if not lang:
        raise HTTPException(status_code=400, detail="Bahasa caption belum dipilih.")
    if fmt not in {"srt", "vtt", "txt"}:
        raise HTTPException(status_code=400, detail="Format harus SRT, VTT, atau TXT.")

    try:
        data = get_info(url)
        source = data.get("subtitles") if kind == "manual" else data.get("automatic_captions")
        source = source or {}
        tracks = source.get(lang) or []

        if not tracks:
            # Fallback: try manual then automatic for the requested language.
            alt = (data.get("subtitles") or {}).get(lang) or (data.get("automatic_captions") or {}).get(lang)
            tracks = alt or []

        if not tracks:
            raise HTTPException(status_code=404, detail=f"Caption bahasa '{lang}' tidak ditemukan.")

        preferred = None
        for ext in ("vtt", "srv3", "ttml", "srt"):
            preferred = next((t for t in tracks if (t.get("ext") or "").lower() == ext and t.get("url")), None)
            if preferred:
                break
        preferred = preferred or next((t for t in tracks if t.get("url")), None)

        if not preferred:
            raise HTTPException(status_code=404, detail="URL track caption tidak tersedia.")

        # Let yt-dlp download/convert the selected subtitle track to avoid
        # relying on direct HTTP calls from the serverless function.
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td) / "caption")
            opts = base_opts()
            opts.update({
                "skip_download": True,
                "writesubtitles": kind == "manual",
                "writeautomaticsub": kind != "manual",
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": out,
                "paths": {"home": td},
            })

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            candidates = list(Path(td).glob("caption*.vtt")) + list(Path(td).glob("*.vtt"))
            if not candidates:
                # Some YouTube tracks use a non-vtt extension.
                candidates = [p for p in Path(td).glob("*") if p.is_file() and p.suffix.lower() in {".srv3", ".ttml", ".srt"}]

            if not candidates:
                # Last-resort: fetch the chosen track URL using yt-dlp's network helper.
                import urllib.request
                req2 = urllib.request.Request(preferred["url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req2, timeout=20) as r:
                    raw = r.read().decode("utf-8", "replace")
            else:
                raw = candidates[0].read_text(encoding="utf-8", errors="replace")

        segments = parse_vtt_to_segments(raw)
        if not segments:
            raise HTTPException(status_code=422, detail="Caption berhasil ditemukan tetapi tidak dapat diparse.")

        if fmt == "srt":
            body = segments_to_srt(segments)
            mime = "application/x-subrip"
            filename = f"retro-sub-{lang}.srt"
        elif fmt == "vtt":
            body = segments_to_vtt(segments)
            mime = "text/vtt"
            filename = f"retro-sub-{lang}.vtt"
        else:
            body = "\n".join(s["text"] for s in segments)
            mime = "text/plain"
            filename = f"retro-sub-{lang}.txt"

        return {
            "ok": True,
            "filename": filename,
            "mime": mime,
            "language": lang,
            "kind": kind,
            "format": fmt,
            "count": len(segments),
            "segments": segments,
            "text": body,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil caption: {str(e)[:700]}")

# IMPORTANT: this is intentionally LAST.
# Vercel's current FastAPI integration supports static frontends via StaticFiles,
# and route declaration order gives API routes precedence over this mount.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
