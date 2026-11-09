
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(200), nullable=False)

    original_transcript = Column(Text, nullable=False)
    content = Column(Text, nullable=False)

    language = Column(String(30), default="hi-IN")
    category = Column(String(100), nullable=True)
    person = Column(String(150), nullable=True)

    memory_date = Column(Date, nullable=True)

    audio_path = Column(String(500), nullable=True)
    narration_path = Column(String(500), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
