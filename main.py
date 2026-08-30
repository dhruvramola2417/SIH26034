from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

app = FastAPI(title="LMPC Scan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/scans")
async def upload_scan(
    side: str,
    image: UploadFile = File(...)
):
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG, or WEBP images are allowed."
        )

    contents = await image.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds 10 MB limit."
        )

    scan_id = str(uuid4())
    suffix = Path(image.filename or "image.jpg").suffix.lower() or ".jpg"
    file_path = UPLOAD_DIR / f"{scan_id}_{side}{suffix}"

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    try:
        with Image.open(file_path) as opened:
            width, height = opened.size
            opened.verify()
    except Exception:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image."
        )

    return {
        "scan_id": scan_id,
        "side": side,
        "filename": file_path.name,
        "image_width": width,
        "image_height": height,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": "uploaded"
    }