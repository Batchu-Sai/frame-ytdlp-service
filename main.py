import os
import subprocess
import tempfile
import uuid
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

API_KEY = os.environ.get("API_KEY", "change-me-in-production")


class ExtractRequest(BaseModel):
    url: str
    api_key: str


@app.post("/extract")
async def extract_audio(req: ExtractRequest):
    if req.api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Validate URL looks like YouTube
    if not any(d in req.url for d in ["youtube.com", "youtu.be"]):
        raise HTTPException(status_code=400, detail="Not a YouTube URL")

    out_dir = tempfile.mkdtemp()
    out_path = os.path.join(out_dir, f"{uuid.uuid4().hex}.m4a")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "-x",
                "--audio-format", "m4a",
                "--audio-quality", "5",  # medium quality, smaller file
                "-o", out_path,
                "--max-filesize", "100M",
                "--socket-timeout", "30",
                req.url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=502,
                detail=f"yt-dlp failed: {result.stderr[:500]}",
            )

        if not os.path.exists(out_path):
            raise HTTPException(status_code=502, detail="No output file produced")

        file_size = os.path.getsize(out_path)
        if file_size < 1000:
            raise HTTPException(status_code=502, detail=f"Output too small: {file_size}B")

        # Get duration via ffprobe
        duration = 0
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", out_path],
                capture_output=True, text=True, timeout=10,
            )
            duration = int(float(probe.stdout.strip()))
        except Exception:
            pass

        # Get title
        title = ""
        try:
            title_result = subprocess.run(
                ["yt-dlp", "--get-title", "--no-playlist", req.url],
                capture_output=True, text=True, timeout=15,
            )
            title = title_result.stdout.strip()
        except Exception:
            pass

        return FileResponse(
            out_path,
            media_type="audio/m4a",
            filename="audio.m4a",
            headers={
                "X-Duration-Seconds": str(duration),
                "X-Title": title[:200],
            },
        )
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="yt-dlp timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    # Also verify yt-dlp is installed and working
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=5)
        return {"status": "ok", "ytdlp_version": result.stdout.strip()}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
