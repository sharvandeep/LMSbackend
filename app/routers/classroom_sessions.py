from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import datetime

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_teacher
from .courses import check_course_access

router = APIRouter(tags=["Classroom Sessions"])

@router.post("/courses/{course_id}/sessions", response_model=schemas.ClassroomSessionResponse, status_code=status.HTTP_201_CREATED)
def create_classroom_session(
    course_id: int,
    payload: schemas.ClassroomSessionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_teacher)
):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if this teacher owns the course
    if course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only create sessions for your assigned courses")
    
    db_session = models.ClassroomSession(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        session_date=payload.session_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        room=payload.room,
        meeting_link=payload.meeting_link
    )
    
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    
    # Send a notification to students enrolled in the course
    try:
        from .notifications import send_notification_helper
        enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
        for enrollment in enrollments:
            send_notification_helper(
                user_id=enrollment.student_id,
                title="New Classroom Session Scheduled",
                message=f"A new session '{payload.title}' has been scheduled for {course.title} on {payload.session_date} at {payload.start_time}.",
                db=db
            )
    except Exception as e:
        print(f"Failed to send session notifications: {e}")
        
    return db_session

@router.get("/courses/{course_id}/sessions", response_model=List[schemas.ClassroomSessionResponse])
def get_course_sessions(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify course access
    check_course_access(course_id, current_user, db)
    
    sessions = db.query(models.ClassroomSession).filter(
        models.ClassroomSession.course_id == course_id
    ).order_by(models.ClassroomSession.session_date.asc(), models.ClassroomSession.start_time.asc()).all()
    
    return sessions

@router.get("/sessions/upcoming", response_model=List[schemas.ClassroomSessionResponse])
def get_upcoming_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    today = datetime.date.today()
    
    if current_user.role == "student":
        # Get course IDs student is enrolled in
        enrollments = db.query(models.Enrollment).filter(models.Enrollment.student_id == current_user.user_id).all()
        course_ids = [e.course_id for e in enrollments]
    elif current_user.role == "teacher":
        # Get course IDs teacher is assigned to
        courses = db.query(models.Course).filter(models.Course.teacher_id == current_user.user_id).all()
        course_ids = [c.course_id for c in courses]
    else:  # Admin
        # Get all courses
        courses = db.query(models.Course).all()
        course_ids = [c.course_id for c in courses]
        
    if not course_ids:
        return []
        
    # Get future sessions (today and onward)
    upcoming = db.query(models.ClassroomSession).filter(
        models.ClassroomSession.course_id.in_(course_ids),
        models.ClassroomSession.session_date >= today
    ).order_by(models.ClassroomSession.session_date.asc(), models.ClassroomSession.start_time.asc()).all()
    
    return upcoming

@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
def delete_classroom_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_teacher)
):
    session = db.query(models.ClassroomSession).filter(
        models.ClassroomSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Classroom session not found")
        
    # Check if this teacher owns the course
    course = db.query(models.Course).filter(models.Course.course_id == session.course_id).first()
    if not course or course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only delete sessions for your assigned courses")
        
    db.delete(session)
    db.commit()
    return {"message": "Classroom session deleted successfully"}
