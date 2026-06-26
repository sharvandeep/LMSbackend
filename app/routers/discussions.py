from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user

router = APIRouter(prefix="/discussions", tags=["Course Forums"])

@router.get("/course/{course_id}")
def get_discussions(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Verify course access
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    posts = db.query(models.DiscussionPost).filter(
        models.DiscussionPost.course_id == course_id
    ).order_by(models.DiscussionPost.created_at.desc()).all()
    
    response = []
    for post in posts:
        replies_list = []
        # Sort replies chronologically
        sorted_replies = sorted(post.replies, key=lambda r: r.created_at)
        for r in sorted_replies:
            replies_list.append({
                "reply_id": r.reply_id,
                "content": r.content,
                "created_at": r.created_at,
                "user_id": r.user_id,
                "user_name": r.user.full_name,
                "user_role": r.user.role
            })
            
        response.append({
            "post_id": post.post_id,
            "title": post.title,
            "content": post.content,
            "is_announcement": post.is_announcement,
            "created_at": post.created_at,
            "user_id": post.user_id,
            "user_name": post.user.full_name,
            "user_role": post.user.role,
            "replies": replies_list
        })
        
    return response

@router.post("/course/{course_id}", status_code=status.HTTP_201_CREATED)
def create_discussion_post(course_id: int, payload: schemas.DiscussionPostCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Verify course access
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    is_announcement = payload.is_announcement
    # Only teachers and admins can make announcements
    if is_announcement and current_user.role not in ["teacher", "admin"]:
        is_announcement = False
        
    new_post = models.DiscussionPost(
        course_id=course_id,
        user_id=current_user.user_id,
        title=payload.title,
        content=payload.content,
        is_announcement=is_announcement
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    # Write an activity log
    action_text = f"Teacher {current_user.full_name} posted announcement: {payload.title}" if is_announcement else f"Student {current_user.full_name} posted in forum: {payload.title}"
    log = models.ActivityLog(user_id=current_user.user_id, action=action_text)
    db.add(log)
    db.commit()
    
    return {
        "post_id": new_post.post_id,
        "title": new_post.title,
        "content": new_post.content,
        "is_announcement": new_post.is_announcement,
        "created_at": new_post.created_at,
        "user_name": current_user.full_name,
        "user_role": current_user.role
    }

@router.post("/posts/{post_id}/replies", status_code=status.HTTP_201_CREATED)
def create_discussion_reply(post_id: int, payload: schemas.DiscussionReplyCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    post = db.query(models.DiscussionPost).filter(models.DiscussionPost.post_id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        
    new_reply = models.DiscussionReply(
        post_id=post_id,
        user_id=current_user.user_id,
        content=payload.content
    )
    db.add(new_reply)
    db.commit()
    db.refresh(new_reply)
    
    # Write an activity log
    action_text = f"{current_user.role.capitalize()} {current_user.full_name} replied to forum post: {post.title}"
    log = models.ActivityLog(user_id=current_user.user_id, action=action_text)
    db.add(log)
    db.commit()
    
    return {
        "reply_id": new_reply.reply_id,
        "content": new_reply.content,
        "created_at": new_reply.created_at,
        "user_name": current_user.full_name,
        "user_role": current_user.role
    }
