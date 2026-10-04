from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Any, List, Optional
import html
import os
import re
import tempfile
import xml.etree.ElementTree as ET

try:
    import yt_dlp
except Exception:
    yt_dlp = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="RETRO SUB", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InfoRequest(BaseModel):
    url: str

class CaptionRequest(BaseModel):
    url: str
    language: Optional[str] = None
    kind: Optional[str] = "auto"

class BrowserSegment(BaseModel):
    start: float = 0
    dur: float = 0
    text: str = ""

class BrowserCaptionRequest(BaseModel):
    video_id: Optional[str] = ""
    title: Optional[str] = ""
    language: Optional[str] = ""
    language_name: Optional[str] = ""
    kind: Optional[str] = "auto"
    segments: List[BrowserSegment] = Field(default_factory=list)

def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return value.replace("\xa0", " ").strip()

def parse_vtt_file(path: str):
    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    return parse_vtt_text(raw)

def parse_vtt_text(raw: str):
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        a, b = [x.strip() for x in line.split("-->", 1)]
        b = b.split(" ", 1)[0]
        try:
            start = vtt_time(a)
            end = vtt_time(b)
        except Exception:
            i += 1
            continue
        text_lines = []
        i += 1
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        text = clean_text("\n".join(text_lines))
        if text:
            segments.append({"start": start, "dur": max(0, end-start), "text": text})
        i += 1
    return segments

def vtt_time(s):
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return int(h)*3600 + int(m)*60 + float(sec)
    if len(parts) == 2:
        m, sec = parts
        return int(m)*60 + float(sec)
    return float(s)

def parse_srv3_or_xml(raw: str):
    # YouTube can return transcript XML in a few related forms.
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    out = []
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("text", "p"):
            continue
        txt = "".join(node.itertext())
        txt = clean_text(txt)
        if not txt:
            continue
        start = node.attrib.get("start", node.attrib.get("t", "0"))
        dur = node.attrib.get("dur", "0")
        try:
            start = float(start)
            dur = float(dur)
            # Some XML formats use milliseconds for t.
            if start > 100000:
                start /= 1000
            if dur > 100000:
                dur /= 1000
        except Exception:
            start, dur = 0, 0
        out.append({"start": start, "dur": dur, "text": txt})
    return out

def srt_time(sec):
    sec = max(0, float(sec))
    ms = int(round((sec - int(sec))*1000))
    total = int(sec)
    if ms >= 1000:
        total += 1
        ms = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def vtt_time_out(sec):
    sec = max(0, float(sec))
    ms = int(round((sec - int(sec))*1000))
    total = int(sec)
    if ms >= 1000:
        total += 1
        ms = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def make_outputs(segments):
    srt = []
    vtt = ["WEBVTT", ""]
    txt = []
    for i, seg in enumerate(segments, 1):
        start = float(seg.get("start", 0))
        dur = float(seg.get("dur", 0))
        end = start + max(dur, 0.001)
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        srt.append(f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
        vtt.append(f"{vtt_time_out(start)} --> {vtt_time_out(end)}\n{text}\n")
        txt.append(text)
    return "\n".join(srt).strip()+"\n", "\n".join(vtt).strip()+"\n", "\n".join(txt).strip()+"\n"

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

def extract_info(url):
    if yt_dlp is None:
        raise RuntimeError("yt-dlp tidak terpasang")
    with yt_dlp.YoutubeDL(base_opts()) as ydl:
        return ydl.extract_info(url, download=False)

@app.get("/api/health")
def health():
    return {"ok": True, "service": "RETRO SUB", "version": "3.0", "browser_mode": True}

@app.post("/api/info")
def info(req: InfoRequest):
    try:
        data = extract_info(req.url)
        tracks = []
        for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
            for lang, items in (data.get(key) or {}).items():
                if not items:
                    continue
                tracks.append({
                    "language": lang,
                    "name": lang,
                    "kind": kind,
                    "formats": [x.get("ext", "") for x in items],
                })
        return {
            "ok": True,
            "video": {
                "id": data.get("id", ""),
                "title": data.get("title", ""),
                "channel": data.get("channel") or data.get("uploader") or "",
                "duration": data.get("duration") or 0,
                "thumbnail": data.get("thumbnail") or "",
            },
            "tracks": tracks,
            "source": "server",
        }
    except Exception as e:
        raise HTTPException(502, detail=f"Gagal membaca video/caption: {e}")

@app.post("/api/caption")
def caption(req: CaptionRequest):
    try:
        data = extract_info(req.url)
        collection = data.get("subtitles") if req.kind != "auto" else data.get("automatic_captions")
        collection = collection or {}
        if req.language:
            items = collection.get(req.language)
            if not items:
                # allow language prefix fallback
                key = next((k for k in collection if k.lower().startswith(req.language.lower())), None)
                items = collection.get(key) if key else None
        else:
            key = next(iter(collection), None)
            items = collection.get(key) if key else None
        if not items:
            raise RuntimeError("Track caption tidak ditemukan.")
        fmt = next((x for x in items if x.get("ext") == "vtt"), items[0])
        url = fmt.get("url")
        if not url:
            raise RuntimeError("URL caption tidak tersedia.")
        import urllib.request
        raw = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "ignore")
        segments = parse_vtt_text(raw)
        if not segments:
            segments = parse_srv3_or_xml(raw)
        if not segments:
            raise RuntimeError("Caption ditemukan tetapi tidak dapat diparsing.")
        srt, vtt, txt = make_outputs(segments)
        return {
            "ok": True,
            "video": {"id": data.get("id",""), "title": data.get("title","")},
            "language": req.language or "",
            "kind": req.kind,
            "segments": segments,
            "outputs": {"srt": srt, "vtt": vtt, "txt": txt},
            "source": "server",
        }
    except Exception as e:
        raise HTTPException(502, detail=f"Gagal mengambil caption: {e}")

@app.post("/api/browser-caption")
def browser_caption(req: BrowserCaptionRequest):
    if not req.segments:
        raise HTTPException(400, detail="Tidak ada segmen caption.")
    segments = [{"start": x.start, "dur": x.dur, "text": clean_text(x.text)} for x in req.segments if clean_text(x.text)]
    if not segments:
        raise HTTPException(400, detail="Caption kosong.")
    srt, vtt, txt = make_outputs(segments)
    return {
        "ok": True,
        "video": {"id": req.video_id, "title": req.title},
        "language": req.language,
        "language_name": req.language_name,
        "kind": req.kind,
        "segments": segments,
        "outputs": {"srt": srt, "vtt": vtt, "txt": txt},
        "source": "browser",
    }

@app.get("/api/bookmarklet")
def bookmarklet():
    path = os.path.join(STATIC_DIR, "bookmarklet.js")
    return FileResponse(path, media_type="text/javascript")

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
