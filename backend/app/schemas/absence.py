import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator


class ExpectedAbsenceCreateRequest(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = None

    @model_validator(mode="after")
    def _check_date_order(self) -> "ExpectedAbsenceCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ExpectedAbsenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    start_date: date
    end_date: date
    reason: str | None
