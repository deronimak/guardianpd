"""Master Admin SMS check — lets platform staff confirm that SMS delivery is
actually working (Brevo key, credits, sender name) before switching SMS alerts
on for any school, without anyone needing the key on their own machine.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_platform_staff
from app.core.sms import provider, send_sms_detailed, sender_name, sms_balance, sms_configured

router = APIRouter(prefix="/platform/sms", tags=["platform"], dependencies=[Depends(require_platform_staff)])


class SmsTestRequest(BaseModel):
    to: str


@router.get("/status")
def sms_status() -> dict:
    return {"configured": sms_configured(), "provider": provider(), "sender": sender_name(), "balance": sms_balance()}


@router.post("/test")
def send_test_sms(payload: SmsTestRequest) -> dict:
    try:
        result = send_sms_detailed(payload.to, "GuardianPD test message: SMS alerts are working.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["detail"])
    return result
