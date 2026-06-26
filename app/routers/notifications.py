from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_admin

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=List[schemas.NotificationResponse])
def get_notifications(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Students and teachers see their specific notifications OR global ones (where user_id is null)
    return db.query(models.Notification).filter(
        (models.Notification.user_id == current_user.user_id) | 
        (models.Notification.user_id == None)
    ).order_by(models.Notification.created_at.desc()).all()

@router.post("", response_model=schemas.NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(payload: schemas.NotificationCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_notification = models.Notification(
        user_id=payload.user_id,
        title=payload.title,
        message=payload.message,
        is_read=False
    )
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    return new_notification
