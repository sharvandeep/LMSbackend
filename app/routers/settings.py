from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .auth import require_admin, get_current_user

router = APIRouter(prefix="/settings", tags=["System Settings"])

@router.get("/")
def get_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    settings_list = db.query(models.Setting).all()
    return {s.setting_key: s.setting_value for s in settings_list}

@router.put("/{setting_key}")
def update_setting(setting_key: str, payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    # Extract the value from payload
    if "value" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must contain a 'value' field"
        )
    
    value_str = str(payload["value"])
    
    # Specific validation for teacher_capacity
    if setting_key == "teacher_capacity":
        try:
            capacity_val = int(value_str)
            if capacity_val <= 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher capacity must be a positive integer"
            )

    setting = db.query(models.Setting).filter(models.Setting.setting_key == setting_key).first()
    if not setting:
        setting = models.Setting(setting_key=setting_key, setting_value=value_str)
        db.add(setting)
    else:
        setting.setting_value = value_str
        
    db.commit()
    return {"setting_key": setting_key, "setting_value": setting.setting_value}
