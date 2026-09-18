from pydantic import BaseModel
from datetime import datetime

class MemoryMatch(BaseModel):
    id: int
    fact_text: str
    created_at: datetime
    similarity: float