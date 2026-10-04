import os, re, json, tempfile, glob, html
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title='RETRO SUB API', version='2.0')

class VideoRequest(BaseModel):
    url: str

class CaptionRequest(BaseModel):
    url: str
    lang: str
    kind: str = 'manual'  # manual | auto
    fmt: str = 'srt'      # srt | vtt | txt


def validate_url(url: str) -> str:
    url = (url or '').strip()
    if not re.match(r'^https?://(www\.)?(youtube\.com|youtu\.be)/', url, re.I):
        raise HTTPException(400, 'Masukkan URL YouTube yang valid.')
    return url


def base_opts():
    return {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': False,
        'socket_timeout': 20,
        'retries': 2,
        'fragment_retries': 2,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36'
        },
    }


def simplify_tracks(tracks, kind):
    out = []
    for lang, entries in (tracks or {}).items():
        if not entries:
            continue
        name = entries[0].get('name') or entries[0].get('language') or lang
        out.append({'lang': lang, 'name': name, 'kind': kind})
    return out


def get_info(url):
    opts = base_opts()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        if 'Sign in' in msg or 'bot' in msg.lower() or 'confirm you are human' in msg.lower():
            msg = 'YouTube menolak permintaan otomatis untuk video ini. Coba video lain atau tunggu beberapa saat.'
        raise HTTPException(502, msg[:500])


@app.get('/')
def root():
    return {'ok': True, 'service': 'RETRO SUB', 'version': '2.0'}

@app.get('/api/health')
def health():
    return {'ok': True, 'service': 'RETRO SUB', 'yt_dlp': yt_dlp.version.__version__}

@app.post('/api/info')
def info(req: VideoRequest):
    url = validate_url(req.url)
    data = get_info(url)
    manual = simplify_tracks(data.get('subtitles'), 'manual')
    auto = simplify_tracks(data.get('automatic_captions'), 'auto')
    # Deduplicate by lang + kind while preserving order
    tracks = []
    seen = set()
    for t in manual + auto:
        key = (t['lang'], t['kind'])
        if key not in seen:
            seen.add(key); tracks.append(t)
    return {
        'id': data.get('id'),
        'title': data.get('title') or 'Untitled',
        'channel': data.get('channel') or data.get('uploader') or '',
        'duration': data.get('duration'),
        'thumbnail': data.get('thumbnail'),
        'webpage_url': data.get('webpage_url') or url,
        'tracks': tracks,
    }


def clean_vtt(vtt: str) -> str:
    # Remove WEBVTT header, NOTE/STYLE blocks, cue settings and HTML tags.
    vtt = vtt.replace('\r\n', '\n').replace('\r', '\n')
    lines = vtt.split('\n')
    out = []
    skip = False
    for line in lines:
        s = line.strip()
        if s in ('WEBVTT',) or s.startswith('Kind:') or s.startswith('Language:'):
            continue
        if s.startswith(('NOTE', 'STYLE', 'REGION')):
            skip = True
            continue
        if skip:
            if not s: skip = False
            continue
        if '-->' in s or re.fullmatch(r'\d+', s):
            continue
        if not s:
            if out and out[-1] != '': out.append('')
            continue
        s = re.sub(r'<[^>]+>', '', s)
        s = html.unescape(s)
        s = re.sub(r'\s+', ' ', s).strip()
        if s and (not out or out[-1] != s):
            out.append(s)
    return '\n'.join(out).strip()


def vtt_to_srt(vtt: str) -> str:
    vtt = vtt.replace('\r\n','\n').replace('\r','\n')
    blocks = re.split(r'\n\s*\n', vtt.strip())
    result=[]; n=1
    for block in blocks:
        lines=block.split('\n')
        if not any('-->' in x for x in lines): continue
        idx=next(i for i,x in enumerate(lines) if '-->' in x)
        timing=lines[idx].strip().replace('.', ',')
        text=[]
        for x in lines[idx+1:]:
            x=re.sub(r'<[^>]+>','',x)
            x=html.unescape(x).strip()
            if x: text.append(x)
        if not text: continue
        result += [str(n), timing, '\n'.join(text), '']; n+=1
    return '\n'.join(result).strip()+'\n'


def download_vtt(url, lang, kind):
    tmp = tempfile.mkdtemp(prefix='retrosub-')
    outtmpl = os.path.join(tmp, 'caption.%(ext)s')
    opts = base_opts() | {
        'writesubtitles': kind == 'manual',
        'writeautomaticsub': kind == 'auto',
        'subtitleslangs': [lang],
        'subtitlesformat': 'vtt/best',
        'outtmpl': outtmpl,
        'overwrites': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = glob.glob(os.path.join(tmp, 'caption.*'))
        # Prefer vtt, but accept other text subtitle extensions.
        files.sort(key=lambda p: 0 if p.lower().endswith('.vtt') else 1)
        if not files:
            raise HTTPException(404, 'Subtitle untuk bahasa tersebut tidak berhasil diambil.')
        path=files[0]
        data=Path(path).read_text(encoding='utf-8-sig', errors='replace')
        return data
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(502, str(e)[:500])
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

@app.post('/api/caption')
def caption(req: CaptionRequest):
    url=validate_url(req.url)
    lang=(req.lang or '').strip()
    if not lang: raise HTTPException(400, 'Bahasa subtitle belum dipilih.')
    fmt=req.fmt.lower()
    if fmt not in ('srt','vtt','txt'): raise HTTPException(400,'Format tidak didukung.')
    if req.kind not in ('manual','auto'): raise HTTPException(400,'Jenis subtitle tidak valid.')
    vtt=download_vtt(url, lang, req.kind)
    if fmt=='vtt':
        content=vtt
        media='text/vtt; charset=utf-8'; ext='vtt'
    elif fmt=='txt':
        content=clean_vtt(vtt)+'\n'
        media='text/plain; charset=utf-8'; ext='txt'
    else:
        content=vtt_to_srt(vtt)
        media='application/x-subrip; charset=utf-8'; ext='srt'
    return Response(content=content, media_type=media, headers={'Content-Disposition': f'attachment; filename="retro-sub.{ext}"'})
