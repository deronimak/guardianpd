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


class GuardianScanItem(BaseModel):
    token: str
    student_id: uuid.UUID
    type: Literal["drop_off", "pick_up"]
    # When the scan physically happened on the phone (set for scans saved
    # offline and uploaded later, so records and parent alerts carry the
    # real time).
    scanned_at: datetime | None = None


class GuardianScanResult(BaseModel):
    # recorded / duplicate / flagged (guardian not authorized for this child) / rejected
    status: str
    detail: str | None = None
    event_id: uuid.UUID | None = None


class GuardianScanBatchRequest(BaseModel):
    scans: list[GuardianScanItem] = Field(max_length=500)


class GuardianScanBatchResponse(BaseModel):
    results: list[GuardianScanResult]


class PupilScanItem(BaseModel):
    token: str
    # "drop_off" = arrived at school, "pick_up" = left school. The scanning
    # staff member (or pupil, at a gate station) chooses it on the device;
    # when omitted the server works it out from the child's day so far.
    type: Literal["drop_off", "pick_up"] | None = None
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
    student_id: uuid.UUID | None = None
    has_photo: bool = False
    student_name: str | None = None
    grade: str | None = None
    scanned_at: datetime | None = None


class PupilLookupRequest(BaseModel):
    token: str


class PupilLookupResult(BaseModel):
    student_id: uuid.UUID
    student_name: str
    grade: str | None = None
    has_photo: bool = False
    # What the child's day so far suggests (arrival if nothing yet today,
    # otherwise the opposite of the last scan) — only a default for the buttons.
    suggested_type: str
    last_type: str | None = None
    last_time: str | None = None


class PupilScanBatchRequest(BaseModel):
    scans: list[PupilScanItem] = Field(max_length=500)


class PupilScanBatchResponse(BaseModel):
    results: list[PupilScanResult]


class PupilRosterEntry(BaseModel):
    id: uuid.UUID
    name: str
    grade: str | None = None
    # md5 of the stored photo (null if none): lets the gate device re-download
    # a photo only when it actually changed.
    photo_hash: str | None = None
