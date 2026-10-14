import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    token: str
    student_id: uuid.UUID
    type: Literal["drop_off", "pick_up"]


class ScanResponse(BaseModel):
    event_id: uuid.UUID
    status: str
    flagged: bool


class PupilScanItem(BaseModel):
    token: str
    # When the scan physically happened on the device. Omitted for a live
    # online scan (server uses "now"); set for scans captured offline and
    # synced later, so attendance and parent notifications carry the real
    # time rather than the sync time.
    scanned_at: datetime | None = None


class PupilScanResult(BaseModel):
    # recorded / duplicate / rejected
    status: str
    detail: str | None = None
    event_id: uuid.UUID | None = None
    type: str | None = None
    student_name: str | None = None
    grade: str | None = None
    scanned_at: datetime | None = None


class PupilScanBatchRequest(BaseModel):
    scans: list[PupilScanItem] = Field(max_length=500)


class PupilScanBatchResponse(BaseModel):
    results: list[PupilScanResult]


class PupilRosterEntry(BaseModel):
    id: uuid.UUID
    name: str
    grade: str | None = None
