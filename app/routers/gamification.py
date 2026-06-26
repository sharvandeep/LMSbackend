from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List

from ..database import get_db
from .. import models
from .auth import get_current_user

router = APIRouter(prefix="/gamification", tags=["Gamification & Achievements"])

@router.get("/status")
def get_gamification_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        return {
            "streak": 0,
            "achievements": [],
            "message": "Gamification features are for students only"
        }
        
    # 1. Calculate Learning Streak (consecutive days with activity or logins)
    # Query login history and activity log dates
    login_dates = db.query(models.LoginHistory.logged_in_at).filter(
        models.LoginHistory.user_id == current_user.user_id
    ).all()
    
    activity_dates = db.query(models.ActivityLog.created_at).filter(
        models.ActivityLog.user_id == current_user.user_id
    ).all()
    
    all_dates = set()
    for l in login_dates:
        all_dates.add(l[0].date())
    for a in activity_dates:
        all_dates.add(a[0].date())
        
    # Sorted list of unique active dates
    sorted_active_dates = sorted(list(all_dates), reverse=True)
    
    streak = 0
    today_val = date.today()
    yesterday_val = today_val - timedelta(days=1)
    
    # Check if there is activity today or yesterday
    if sorted_active_dates:
        latest_active = sorted_active_dates[0]
        if latest_active == today_val or latest_active == yesterday_val:
            # Calculate consecutive days backward
            streak = 1
            current_date = latest_active
            for next_date in sorted_active_dates[1:]:
                if current_date - next_date == timedelta(days=1):
                    streak += 1
                    current_date = next_date
                elif current_date - next_date == timedelta(days=0):
                    continue
                else:
                    break
    else:
        # Fallback default for new active students to encourage interaction
        streak = 1
        
    # 2. Compute Achievements
    achievements = []
    
    # A. Completed Python / Course Completion Badge
    # Check enrollments with 100% completion
    completed_enrollment = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_user.user_id,
        models.Enrollment.completion_pct >= 100.0
    ).first()
    
    if completed_enrollment:
        achievements.append({
            "id": "course_completion",
            "title": f"Completed {completed_enrollment.course.title}",
            "description": "Graduated with 100% course completion.",
            "icon": "Trophy",
            "color": "gold",
            "unlocked": True
        })
    else:
        # Show locked badge
        achievements.append({
            "id": "course_completion",
            "title": "Course Master",
            "description": "Complete any course to 100%.",
            "icon": "Trophy",
            "color": "gray",
            "unlocked": False
        })
        
    # B. Perfect Quiz Badge
    # Check if any quiz attempt scored maximum marks
    perfect_attempt = None
    attempts = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == current_user.user_id
    ).all()
    
    for att in attempts:
        quiz = att.quiz
        if quiz and att.score == quiz.total_marks:
            perfect_attempt = att
            break
            
    if perfect_attempt:
        achievements.append({
            "id": "perfect_quiz",
            "title": "Perfect Quiz",
            "description": f"Scored 100% on the quiz: {perfect_attempt.quiz.title}.",
            "icon": "Award",
            "color": "cyan",
            "unlocked": True
        })
    else:
        achievements.append({
            "id": "perfect_quiz",
            "title": "Perfect Quiz",
            "description": "Score 100% on any quiz.",
            "icon": "Award",
            "color": "gray",
            "unlocked": False
        })
        
    # C. 100% Attendance Badge
    # Find any course with attendance and 100% attendance rate
    has_perfect_attendance = False
    perfect_course_title = ""
    courses = db.query(models.Course).filter(
        models.Course.branch_id == current_user.branch_id,
        models.Course.semester_id == current_user.semester_id
    ).all()
    
    for c in courses:
        records = db.query(models.Attendance).filter(
            models.Attendance.course_id == c.course_id,
            models.Attendance.student_id == current_user.user_id
        ).all()
        if records:
            absent_count = sum(1 for r in records if r.status == "Absent")
            if absent_count == 0:
                has_perfect_attendance = True
                perfect_course_title = c.title
                break
                
    if has_perfect_attendance:
        achievements.append({
            "id": "perfect_attendance",
            "title": "100% Attendance",
            "description": f"Maintained perfect attendance in {perfect_course_title}.",
            "icon": "CalendarCheck",
            "color": "green",
            "unlocked": True
        })
    else:
        achievements.append({
            "id": "perfect_attendance",
            "title": "Perfect Attendance",
            "description": "Maintain 100% attendance in any course.",
            "icon": "CalendarCheck",
            "color": "gray",
            "unlocked": False
        })
        
    # D. Top Performer Badge
    # Calculate average grades across assignments and quizzes
    # If student average score > 90%, mark as top performer
    total_score_pct = 0.0
    graded_count = 0
    
    # Assignments
    submissions = db.query(models.Submission).filter(
        models.Submission.student_id == current_user.user_id,
        models.Submission.status == "Graded"
    ).all()
    
    for sub in submissions:
        if sub.assignment.total_marks > 0:
            total_score_pct += (sub.marks / sub.assignment.total_marks) * 100
            graded_count += 1
            
    # Quizzes
    for att in attempts:
        if att.quiz.total_marks > 0:
            total_score_pct += (att.score / att.quiz.total_marks) * 100
            graded_count += 1
            
    avg_performance = (total_score_pct / graded_count) if graded_count > 0 else 0.0
    
    if avg_performance >= 90.0:
        achievements.append({
            "id": "top_performer",
            "title": "Top Performer",
            "description": f"Earned an outstanding grade average of {round(avg_performance, 1)}%.",
            "icon": "Zap",
            "color": "purple",
            "unlocked": True
        })
    else:
        achievements.append({
            "id": "top_performer",
            "title": "Academic Elite",
            "description": "Achieve a grade average above 90% across assignments and quizzes.",
            "icon": "Zap",
            "color": "gray",
            "unlocked": False
        })
        
    return {
        "streak": streak,
        "active_days": len(all_dates) if all_dates else 1,
        "grade_average": round(avg_performance, 1),
        "achievements": achievements
    }
