from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date as date_type

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_teacher, require_admin

router = APIRouter(prefix="/attendance", tags=["Attendance"])

@router.post("", status_code=status.HTTP_201_CREATED)
def submit_attendance(payload: schemas.AttendanceSubmit, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Verify course access
    course = db.query(models.Course).filter(models.Course.course_id == payload.course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    # Check permission (must be admin or the course's teacher)
    if current_user.role == "teacher" and course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
    elif current_user.role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students cannot submit attendance")
        
    # Write to database
    recorded = 0
    for record in payload.records:
        # Check if student is enrolled in the course
        enrollment = db.query(models.Enrollment).filter(
            models.Enrollment.student_id == record.student_id,
            models.Enrollment.course_id == payload.course_id
        ).first()
        if not enrollment:
            continue
            
        # Check if attendance already exists for this student on this day and course
        existing = db.query(models.Attendance).filter(
            models.Attendance.student_id == record.student_id,
            models.Attendance.course_id == payload.course_id,
            models.Attendance.date == payload.date
        ).first()
        
        if existing:
            existing.status = record.status
        else:
            new_record = models.Attendance(
                student_id=record.student_id,
                course_id=payload.course_id,
                date=payload.date,
                status=record.status
            )
            db.add(new_record)
        recorded += 1
        
    db.commit()
    return {"message": f"Successfully recorded attendance for {recorded} students"}

@router.get("/course/{course_id}")
def get_course_attendance(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    # If student, return their individual attendance logs and rate
    if current_user.role == "student":
        records = db.query(models.Attendance).filter(
            models.Attendance.course_id == course_id,
            models.Attendance.student_id == current_user.user_id
        ).order_by(models.Attendance.date.desc()).all()
        
        total = len(records)
        present = sum(1 for r in records if r.status == "Present")
        rate = (present / total * 100) if total > 0 else 100.0
        
        return {
            "percentage": round(rate, 2),
            "total_classes": total,
            "present_classes": present,
            "records": [
                {
                    "date": r.date,
                    "status": r.status
                } for r in records
            ]
        }
        
    # If teacher or admin, return full course summary
    # 1. Total sessions count
    dates = db.query(models.Attendance.date).filter(
        models.Attendance.course_id == course_id
    ).distinct().order_by(models.Attendance.date.desc()).all()
    session_dates = [d[0] for d in dates]
    
    # 2. Enrolled students and their attendance percentages
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    student_summary = []
    
    for enrollment in enrollments:
        student = enrollment.student
        records = db.query(models.Attendance).filter(
            models.Attendance.course_id == course_id,
            models.Attendance.student_id == student.user_id
        ).all()
        
        total = len(records)
        present = sum(1 for r in records if r.status == "Present")
        rate = (present / total * 100) if total > 0 else 100.0
        
        student_summary.append({
            "student_id": student.user_id,
            "full_name": student.full_name,
            "email": student.email,
            "percentage": round(rate, 2),
            "present_count": present,
            "total_count": total,
            "history": {r.date.isoformat(): r.status for r in records}
        })
        
    return {
        "course_id": course_id,
        "title": course.title,
        "session_dates": session_dates,
        "students": student_summary
    }
