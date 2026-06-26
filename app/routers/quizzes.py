from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_teacher, require_student
from .courses import check_course_access

router = APIRouter(tags=["Quizzes & Questions"])

# ----------------- QUIZ ENDPOINTS -----------------

@router.get("/courses/{course_id}/quizzes", response_model=List[schemas.QuizResponse])
def get_course_quizzes(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    check_course_access(course_id, current_user, db)
    quizzes = db.query(models.Quiz).filter(models.Quiz.course_id == course_id).all()
    
    response_data = []
    for quiz in quizzes:
        attempt = db.query(models.QuizAttempt).filter(
            models.QuizAttempt.quiz_id == quiz.quiz_id,
            models.QuizAttempt.student_id == current_user.user_id
        ).first()
        
        response_data.append(schemas.QuizResponse(
            quiz_id=quiz.quiz_id,
            course_id=quiz.course_id,
            title=quiz.title,
            total_marks=quiz.total_marks,
            time_limit=quiz.time_limit,
            attempts_allowed=quiz.attempts_allowed,
            student_status="Completed" if attempt else "Not Attempted",
            score=attempt.score if attempt else None
        ))
    return response_data

@router.get("/quizzes/{quiz_id}", response_model=schemas.QuizResponse)
def get_quiz_by_id(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    check_course_access(quiz.course_id, current_user, db)
    
    attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.quiz_id == quiz_id,
        models.QuizAttempt.student_id == current_user.user_id
    ).first()
    
    return schemas.QuizResponse(
        quiz_id=quiz.quiz_id,
        course_id=quiz.course_id,
        title=quiz.title,
        total_marks=quiz.total_marks,
        time_limit=quiz.time_limit,
        attempts_allowed=quiz.attempts_allowed,
        student_status="Completed" if attempt else "Not Attempted",
        score=attempt.score if attempt else None
    )

@router.post("/courses/{course_id}/quizzes", response_model=schemas.QuizResponse, status_code=status.HTTP_201_CREATED)
def create_quiz(course_id: int, payload: schemas.QuizCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    # Verify course ownership
    course = db.query(models.Course).filter(
        models.Course.course_id == course_id,
        models.Course.teacher_id == current_user.user_id
    ).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    new_quiz = models.Quiz(
        course_id=course_id,
        title=payload.title,
        total_marks=payload.total_marks,
        time_limit=payload.time_limit,
        attempts_allowed=payload.attempts_allowed
    )
    db.add(new_quiz)
    db.commit()
    db.refresh(new_quiz)
    return new_quiz

@router.delete("/quizzes/{quiz_id}", status_code=status.HTTP_200_OK)
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        
    if quiz.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    db.delete(quiz)
    db.commit()
    return {"message": "deleted"}

# ----------------- QUESTION ENDPOINTS -----------------

@router.get("/quizzes/{quiz_id}/questions", response_model=List[schemas.QuestionResponse])
def get_quiz_questions(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        
    check_course_access(quiz.course_id, current_user, db)
    
    questions = db.query(models.Question).filter(models.Question.quiz_id == quiz_id).all()
    
    # If student is retrieving questions, we should technically strip the "is_correct" flag from options
    # to prevent cheating in production. For simplicity and syncing we can return options as is or filter.
    return questions

@router.post("/quizzes/{quiz_id}/questions", response_model=schemas.QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_quiz_question(quiz_id: int, payload: schemas.QuestionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        
    if quiz.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    new_question = models.Question(
        quiz_id=quiz_id,
        question_text=payload.question_text,
        question_type=payload.question_type,
        marks=payload.marks
    )
    db.add(new_question)
    db.commit()
    db.refresh(new_question)
    
    # Add multiple choice options if provided
    if payload.options and payload.question_type == "mcq":
        for index, opt in enumerate(payload.options):
            new_option = models.Option(
                question_id=new_question.question_id,
                option_text=opt.option_text,
                is_correct=opt.is_correct
            )
            db.add(new_option)
        db.commit()
        db.refresh(new_question)
        
    return new_question

@router.put("/quizzes/{quiz_id}/questions/{question_id}", response_model=schemas.QuestionResponse)
def update_question(quiz_id: int, question_id: int, payload: schemas.QuestionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    question = db.query(models.Question).filter(
        models.Question.question_id == question_id,
        models.Question.quiz_id == quiz_id
    ).first()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        
    if question.quiz.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    question.question_text = payload.question_text
    question.question_type = payload.question_type
    question.marks = payload.marks
    
    db.commit()
    db.refresh(question)
    return question

# ----------------- ATTEMPTS & RESULTS ENDPOINTS -----------------

@router.post("/quizzes/{quiz_id}/attempts")
def submit_quiz_attempt(quiz_id: int, payload: schemas.QuizAttemptCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_student)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        
    check_course_access(quiz.course_id, current_user, db)
    
    # Check if student already attempted
    existing_attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.quiz_id == quiz_id,
        models.QuizAttempt.student_id == current_user.user_id
    ).first()
    if existing_attempt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already attempted this quiz")
        
    # Calculate score
    score = 0
    for ans in payload.answers:
        question = db.query(models.Question).filter(models.Question.question_id == ans.question_id).first()
        if not question:
            continue
            
        if question.question_type == "mcq" and ans.selected_option_id:
            # Check if selected option is correct
            option = db.query(models.Option).filter(
                models.Option.option_id == ans.selected_option_id,
                models.Option.question_id == ans.question_id
            ).first()
            if option and option.is_correct:
                score += question.marks
        elif question.question_type == "tf" and ans.text_answer:
            # Check true/false string
            correct_option = db.query(models.Option).filter(
                models.Option.question_id == ans.question_id,
                models.Option.is_correct == True
            ).first()
            if correct_option and correct_option.option_text.lower() == ans.text_answer.lower():
                score += question.marks
                
    # Record attempt
    new_attempt = models.QuizAttempt(
        quiz_id=quiz_id,
        student_id=current_user.user_id,
        score=score
    )
    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)
    
    return {
        "attempt_id": new_attempt.attempt_id,
        "score": score,
        "results": f"Quiz submitted. Total score: {score}/{quiz.total_marks}"
    }

@router.get("/quizzes/{quiz_id}/results")
def get_quiz_results(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    quiz = db.query(models.Quiz).filter(models.Quiz.quiz_id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        
    if quiz.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    attempts = db.query(models.QuizAttempt).filter(models.QuizAttempt.quiz_id == quiz_id).all()
    
    return [
        {
            "student_id": att.student_id,
            "student_name": att.student.full_name,
            "score": att.score,
            "attempt_date": att.attempt_date
        } for att in attempts
    ]
