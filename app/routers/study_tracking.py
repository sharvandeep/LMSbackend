from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from datetime import datetime

from ..database import get_db
from .. import models
from .auth import get_current_user

router = APIRouter(prefix="/study-tracking", tags=["Study Workspace Tracking"])

# ----------------- BOOKMARKS (STARRED MODULES) -----------------
@router.post("/bookmarks/toggle/{module_id}")
def toggle_bookmark(module_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students can bookmark modules")
        
    module = db.query(models.Module).filter(models.Module.module_id == module_id).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        
    existing = db.query(models.Bookmark).filter(
        models.Bookmark.student_id == current_user.user_id,
        models.Bookmark.module_id == module_id
    ).first()
    
    if existing:
        db.delete(existing)
        db.commit()
        return {"starred": False, "message": "Module removed from bookmarks"}
    else:
        new_bookmark = models.Bookmark(
            student_id=current_user.user_id,
            module_id=module_id
        )
        db.add(new_bookmark)
        db.commit()
        return {"starred": True, "message": "Module added to bookmarks"}

@router.get("/bookmarks")
def get_bookmarks(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students have bookmarks")
        
    bookmarks = db.query(models.Bookmark).filter(
        models.Bookmark.student_id == current_user.user_id
    ).order_by(models.Bookmark.created_at.desc()).all()
    
    return [
        {
            "bookmark_id": b.bookmark_id,
            "module_id": b.module_id,
            "module_title": b.module.title,
            "course_id": b.module.course_id,
            "course_title": b.module.course.title,
            "created_at": b.created_at
        } for b in bookmarks
    ]

# ----------------- RECENTLY VIEWED COURSES -----------------
@router.post("/recently-viewed/{course_id}")
def log_recently_viewed(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        return {"message": "Ignored, not a student"}
        
    # Check course exists
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    # Delete existing view log if any to prevent cluttering and update timestamp
    db.query(models.RecentlyViewed).filter(
        models.RecentlyViewed.student_id == current_user.user_id,
        models.RecentlyViewed.course_id == course_id
    ).delete()
    
    new_view = models.RecentlyViewed(
        student_id=current_user.user_id,
        course_id=course_id
    )
    db.add(new_view)
    db.commit()
    return {"message": "Logged view successfully"}

@router.get("/recently-viewed")
def get_recently_viewed(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        return []
        
    views = db.query(models.RecentlyViewed).filter(
        models.RecentlyViewed.student_id == current_user.user_id
    ).order_by(models.RecentlyViewed.viewed_at.desc()).limit(5).all()
    
    return [
        {
            "course_id": v.course_id,
            "title": v.course.title,
            "code": "".join([w[0] for w in v.course.title.split() if w]).upper() if v.course.title else f"CSE-{v.course_id}", # fallback code logic
            "teacher_name": v.course.teacher.full_name if v.course.teacher else "Assigned Faculty",
            "viewed_at": v.viewed_at
        } for v in views
    ]

# ----------------- DOWNLOAD HISTORY -----------------
@router.post("/downloads/{material_id}")
def log_download(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        return {"message": "Ignored, not a student"}
        
    material = db.query(models.Material).filter(models.Material.material_id == material_id).first()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
        
    # Prevent duplicate logs in same minute to avoid spam
    # Just write a new log
    new_log = models.DownloadHistory(
        student_id=current_user.user_id,
        material_id=material_id
    )
    db.add(new_log)
    
    # Log an activity
    action_text = f"Student {current_user.full_name} downloaded study material: {material.title or 'document'}"
    activity = models.ActivityLog(user_id=current_user.user_id, action=action_text)
    db.add(activity)
    
    db.commit()
    return {"message": "Download logged"}

@router.get("/downloads")
def get_download_history(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        return []
        
    downloads = db.query(models.DownloadHistory).filter(
        models.DownloadHistory.student_id == current_user.user_id
    ).order_by(models.DownloadHistory.downloaded_at.desc()).limit(15).all()
    
    return [
        {
            "download_id": d.download_id,
            "material_id": d.material_id,
            "title": d.material.title or "Untitled Document",
            "file_type": d.material.file_type or "Document",
            "course_title": d.material.module.course.title,
            "downloaded_at": d.downloaded_at
        } for d in downloads
    ]
