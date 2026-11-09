
import uuid
import subprocess
import os

from pathlib import Path
from datetime import date
from typing import Optional

import imageio_ffmpeg

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    Depends,
    HTTPException
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import engine, Base, get_db, DATA_DIR
from backend.models import Memory
from backend.gnani import transcribe_audio, generate_speech


# ==================================================
# PATHS AND DATABASE
# ==================================================

# Use the same persistent storage directory as database.py
AUDIO_DIR = DATA_DIR / "audio"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Create database tables
Base.metadata.create_all(bind=engine)

# Get the FFmpeg executable installed through imageio-ffmpeg
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


# ==================================================
# FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="MaaMemo API",
    description=(
        "A voice-first digital memory book for preserving "
        "personal and family moments using Gnani AI."
    ),
    version="1.2.0"
)


# ==================================================
# CORS CONFIGURATION
# ==================================================

FRONTEND_URLS = os.getenv("FRONTEND_URLS", "")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

# Add deployed frontend URLs from environment variables
for url in FRONTEND_URLS.split(","):
    url = url.strip().rstrip("/")

    if url and url not in allowed_origins:
        allowed_origins.append(url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==================================================
# STATIC AUDIO FILES
# ==================================================

app.mount(
    "/audio",
    StaticFiles(directory=str(AUDIO_DIR)),
    name="audio"
)


# ==================================================
# REQUEST SCHEMAS
# ==================================================

class MemoryCreate(BaseModel):
    title: str
    original_transcript: Optional[str] = None
    content: str
    language: str = "hi-IN"
    category: Optional[str] = None
    person: Optional[str] = None
    memory_date: Optional[date] = None
    audio_path: Optional[str] = None


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    original_transcript: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None
    person: Optional[str] = None
    memory_date: Optional[date] = None


# ==================================================
# AUDIO FORMAT CONFIGURATION
# ==================================================

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".webm",
    ".weba",
    ".ogg",
    ".mpeg",
    ".mpga",
    ".aac",
    ".flac",
    ".opus",
    ".3gp"
}


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def get_audio_filename(upload: UploadFile) -> str:
    """Validate audio extension and generate a unique filename."""

    extension = Path(upload.filename or "").suffix.lower()

    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported audio format. "
                "Upload WAV, MP3, M4A, WebM, WEBA, OGG, "
                "AAC, FLAC, OPUS or another supported format."
            )
        )

    return f"{uuid.uuid4().hex}{extension}"


def save_uploaded_audio(audio: UploadFile, destination: Path):
    """Save uploaded audio in chunks."""

    with destination.open("wb") as output:

        while True:

            chunk = audio.file.read(1024 * 1024)

            if not chunk:
                break

            output.write(chunk)

    if not destination.exists() or destination.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded audio file is empty."
        )


def convert_audio_to_wav(
    source: Path,
    destination: Path
):
    """
    Convert the original recording into a standard WAV file.

    Gnani Prisma receives:
    - WAV container
    - PCM signed 16-bit audio
    - Mono channel
    - 16 kHz sample rate

    The original uploaded recording is never modified.
    """

    command = [
        FFMPEG_PATH,
        "-y",
        "-i", str(source),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(destination)
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180
        )

        if result.returncode != 0:

            error_message = result.stderr[-1500:]

            raise RuntimeError(
                f"FFmpeg conversion failed: {error_message}"
            )

        if not destination.exists() or destination.stat().st_size == 0:

            raise RuntimeError(
                "FFmpeg did not generate a valid WAV file."
            )

        return destination

    except subprocess.TimeoutExpired:

        raise RuntimeError(
            "Audio conversion timed out. Try a shorter recording."
        )


def extract_transcript(result):
    """Extract transcript text from common STT response formats."""

    if isinstance(result, str):
        return result.strip()

    if isinstance(result, dict):

        possible_keys = [
            "transcript",
            "text",
            "transcription",
            "recognized_text",
            "utterance"
        ]

        for key in possible_keys:

            value = result.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ["data", "result", "response"]:

            nested = result.get(key)

            if isinstance(nested, dict):

                extracted = extract_transcript(nested)

                if extracted:
                    return extracted

    return ""


def get_memory_or_404(memory_id: int, db: Session):

    memory = db.query(Memory).filter(
        Memory.id == memory_id
    ).first()

    if memory is None:

        raise HTTPException(
            status_code=404,
            detail="Memory not found."
        )

    return memory


def remove_audio_file(relative_path):
    """Delete a file only if it belongs to MaaMemo's audio folder."""

    if not relative_path:
        return

    try:

        filename = Path(relative_path).name

        path = (AUDIO_DIR / filename).resolve()

        if path.parent == AUDIO_DIR.resolve() and path.is_file():
            path.unlink()

    except OSError:
        pass


def generate_memory_title(transcript: str) -> str:
    """Generate a basic title from the first few transcript words."""

    words = transcript.strip().split()

    if not words:
        return "Untitled Memory"

    title = " ".join(words[:8])

    if len(words) > 8:
        title += "..."

    return title


def transcribe_uploaded_recording(
    original_path: Path,
    language_code: str
):
    """
    Convert an uploaded recording and send it to Gnani Prisma.

    Returns:
        transcript, raw API response

    The original file remains untouched.
    """

    temporary_wav = AUDIO_DIR / (
        f"converted_{uuid.uuid4().hex}.wav"
    )

    try:

        # 1. Convert original recording to standard WAV
        convert_audio_to_wav(
            original_path,
            temporary_wav
        )

        # 2. Send converted WAV to Gnani Prisma
        result = transcribe_audio(
            str(temporary_wav),
            language_code=language_code
        )

        # 3. Extract transcript
        transcript = extract_transcript(result)

        return transcript, result

    finally:

        # Always remove temporary converted WAV
        remove_audio_file(temporary_wav.name)


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/")
def home():

    return {
        "message": "Welcome to MaaMemo API!",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "application": "MaaMemo",
        "audio_conversion": "enabled",
        "ffmpeg": "available"
    }


# ==================================================
# AUDIO TRANSCRIPTION - GNANI PRISMA STT
# ==================================================

@app.post("/transcribe")
def transcribe(
    audio: UploadFile = File(...),
    language_code: str = Form("hi-IN")
):
    """
    Upload audio, convert it and transcribe using Gnani Prisma.

    Original recording is preserved.
    """

    filename = get_audio_filename(audio)

    destination = AUDIO_DIR / filename

    try:

        # 1. Save original recording
        save_uploaded_audio(
            audio,
            destination
        )

        # 2. Convert and transcribe
        transcript, result = transcribe_uploaded_recording(
            destination,
            language_code
        )

        if not transcript:

            return {
                "message": (
                    "Audio processed, but no transcript "
                    "could be extracted."
                ),
                "transcript": "",
                "language": language_code,
                "audio_path": f"/audio/{filename}",
                "raw_response": result
            }

        return {
            "message": "Transcription successful.",
            "transcript": transcript,
            "language": language_code,
            "audio_path": f"/audio/{filename}"
        }

    except HTTPException:
        raise

    except Exception as error:

        # Keep the original recording for possible retry.
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Gnani transcription failed: {str(error)}",
                "audio_path": f"/audio/{filename}"
            }
        )

    finally:

        audio.file.close()


# ==================================================
# CREATE MEMORY FROM AUDIO
# ==================================================

@app.post("/memories/from-audio")
def create_memory_from_audio(
    audio: UploadFile = File(...),
    language_code: str = Form("hi-IN"),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    person: Optional[str] = Form(None),
    memory_date: Optional[date] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload a recording, transcribe using Gnani Prisma,
    and save it directly as a MaaMemo memory.
    """

    filename = get_audio_filename(audio)

    destination = AUDIO_DIR / filename

    try:

        # 1. Save original recording
        save_uploaded_audio(
            audio,
            destination
        )

        # 2. Convert and transcribe using Gnani Prisma
        transcript, result = transcribe_uploaded_recording(
            destination,
            language_code
        )

        if not transcript:

            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        "No speech could be transcribed "
                        "from this recording."
                    ),
                    "audio_path": f"/audio/{filename}"
                }
            )

        # 3. Prepare memory content
        clean_transcript = transcript.strip()

        memory_title = (
            title.strip()
            if title and title.strip()
            else generate_memory_title(clean_transcript)
        )

        # 4. Create memory record
        memory = Memory(
            title=memory_title,
            original_transcript=clean_transcript,
            content=clean_transcript,
            language=language_code,
            category=category.strip() if category else None,
            person=person.strip() if person else None,
            memory_date=memory_date,
            audio_path=f"/audio/{filename}"
        )

        # 5. Save to database
        db.add(memory)

        db.commit()

        db.refresh(memory)

        return {
            "message": "Voice memory created successfully.",
            "transcript": clean_transcript,
            "memory": memory
        }

    except HTTPException:

        db.rollback()

        # Preserve the original recording for retry.
        raise

    except Exception as error:

        db.rollback()

        # Preserve the original recording for retry.
        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    f"Could not create voice memory: {str(error)}"
                ),
                "audio_path": f"/audio/{filename}"
            }
        )

    finally:

        audio.file.close()


# ==================================================
# CREATE MEMORY MANUALLY
# ==================================================

@app.post("/memories")
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db)
):
    """Save a memory from manually entered text."""

    if not payload.title.strip():

        raise HTTPException(
            status_code=400,
            detail="Memory title cannot be empty."
        )

    if not payload.content.strip():

        raise HTTPException(
            status_code=400,
            detail="Memory content cannot be empty."
        )

    original = (
        payload.original_transcript
        if payload.original_transcript is not None
        else payload.content
    )

    memory = Memory(
        title=payload.title.strip(),
        original_transcript=original,
        content=payload.content.strip(),
        language=payload.language,
        category=payload.category,
        person=payload.person,
        memory_date=payload.memory_date,
        audio_path=payload.audio_path
    )

    db.add(memory)

    db.commit()

    db.refresh(memory)

    return {
        "message": "Memory saved successfully.",
        "memory": memory
    }


# ==================================================
# GET ALL MEMORIES + SEARCH + FILTERS
# ==================================================

@app.get("/memories")
def get_memories(
    search: Optional[str] = None,
    category: Optional[str] = None,
    language: Optional[str] = None,
    person: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Retrieve memories with optional search and filters."""

    query = db.query(Memory)

    if search:

        term = f"%{search}%"

        query = query.filter(
            (Memory.title.ilike(term)) |
            (Memory.content.ilike(term)) |
            (Memory.original_transcript.ilike(term)) |
            (Memory.person.ilike(term))
        )

    if category:

        query = query.filter(
            Memory.category == category
        )

    if language:

        query = query.filter(
            Memory.language == language
        )

    if person:

        query = query.filter(
            Memory.person.ilike(f"%{person}%")
        )

    if year:

        query = query.filter(
            Memory.memory_date.is_not(None),
            Memory.memory_date >= date(year, 1, 1),
            Memory.memory_date < date(year + 1, 1, 1)
        )

    if month:

        if month < 1 or month > 12:

            raise HTTPException(
                status_code=400,
                detail="Month must be between 1 and 12."
            )

        if not year:

            raise HTTPException(
                status_code=400,
                detail="Provide a year when filtering by month."
            )

        query = query.filter(
            Memory.memory_date >= date(year, month, 1)
        )

        if month == 12:
            next_month = date(year + 1, 1, 1)

        else:
            next_month = date(year, month + 1, 1)

        query = query.filter(
            Memory.memory_date < next_month
        )

    memories = query.order_by(
        Memory.created_at.desc()
    ).all()

    return {
        "count": len(memories),
        "memories": memories
    }


# ==================================================
# GET ONE MEMORY
# ==================================================

@app.get("/memories/{memory_id}")
def get_memory(
    memory_id: int,
    db: Session = Depends(get_db)
):

    return get_memory_or_404(
        memory_id,
        db
    )


# ==================================================
# UPDATE A MEMORY
# ==================================================

@app.put("/memories/{memory_id}")
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    db: Session = Depends(get_db)
):

    memory = get_memory_or_404(
        memory_id,
        db
    )

    updates = payload.model_dump(
        exclude_unset=True
    )

    for field, value in updates.items():

        if field in {"title", "content"} and value is not None:

            value = value.strip()

            if not value:

                raise HTTPException(
                    status_code=400,
                    detail=f"{field} cannot be empty."
                )

        setattr(memory, field, value)

    db.commit()

    db.refresh(memory)

    return {
        "message": "Memory updated successfully.",
        "memory": memory
    }


# ==================================================
# DELETE A MEMORY
# ==================================================

@app.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db)
):

    memory = get_memory_or_404(
        memory_id,
        db
    )

    remove_audio_file(memory.audio_path)

    remove_audio_file(memory.narration_path)

    db.delete(memory)

    db.commit()

    return {
        "message": "Memory deleted successfully.",
        "memory_id": memory_id
    }


# ==================================================
# GNANI TIMBRE TTS - NARRATE A MEMORY
# ==================================================

@app.post("/memories/{memory_id}/narrate")
def narrate_memory(
    memory_id: int,
    db: Session = Depends(get_db)
):
    """Generate spoken narration using Gnani Timbre."""

    memory = get_memory_or_404(
        memory_id,
        db
    )

    filename = (
        f"narration_{memory.id}_{uuid.uuid4().hex}.wav"
    )

    destination = AUDIO_DIR / filename

    try:

        generate_speech(
            text=memory.content,
            output_path=str(destination),
            language_code=memory.language
        )

        # Replace previous narration only after success.
        previous_narration = memory.narration_path

        memory.narration_path = f"/audio/{filename}"

        db.commit()

        db.refresh(memory)

        if previous_narration:

            remove_audio_file(previous_narration)

        return {
            "message": "Memory narration generated successfully.",
            "narration_path": memory.narration_path,
            "memory": memory
        }

    except Exception as error:

        db.rollback()

        remove_audio_file(filename)

        raise HTTPException(
            status_code=502,
            detail=f"Could not generate narration: {str(error)}"
        )


# ==================================================
# MONTHLY MEMORY RECAP
# ==================================================

@app.get("/recap/{year}/{month}")
def monthly_recap(
    year: int,
    month: int,
    db: Session = Depends(get_db)
):
    """Retrieve memories recorded during a particular month."""

    if month < 1 or month > 12:

        raise HTTPException(
            status_code=400,
            detail="Month must be between 1 and 12."
        )

    start_date = date(year, month, 1)

    if month == 12:
        end_date = date(year + 1, 1, 1)

    else:
        end_date = date(year, month + 1, 1)

    all_memories = db.query(Memory).all()

    selected = []

    for memory in all_memories:

        relevant_date = memory.memory_date

        if relevant_date is None and memory.created_at:

            relevant_date = memory.created_at.date()

        if relevant_date and start_date <= relevant_date < end_date:

            selected.append(memory)

    selected.sort(
        key=lambda item: (
            item.memory_date or (
                item.created_at.date()
                if item.created_at else date.min
            )
        )
    )

    return {
        "year": year,
        "month": month,
        "total_memories": len(selected),
        "memories": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "category": item.category,
                "person": item.person,
                "memory_date": item.memory_date
            }
            for item in selected
        ]
    }
