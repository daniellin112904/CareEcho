import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException


def require_staff(x_staff_pin: str = Header(default="")):
    pin = os.getenv("STAFF_PIN", "")
    # An unset STAFF_PIN must lock staff routes, not open them to an empty header
    if not pin or not secrets.compare_digest(x_staff_pin, pin):
        raise HTTPException(401, "Wrong staff PIN")


router = APIRouter(tags=["staff"])


@router.post("/staff/verify", status_code=204, dependencies=[Depends(require_staff)])
def verify_pin():
    pass
