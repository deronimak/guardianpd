import uuid
from typing import Literal

from pydantic import BaseModel


class ScanRequest(BaseModel):
    token: str
    student_id: uuid.UUID
    type: Literal["drop_off", "pick_up"]


class ScanResponse(BaseModel):
    event_id: uuid.UUID
    status: str
    flagged: bool
