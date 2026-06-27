from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal

# Base Config for all schemas to support ORM mapping
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# ----------------- TOKEN SCHEMAS -----------------
class Token(BaseModel):
    token: str
    user_id: int
    role: str

class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None

# ----------------- BRANCH SCHEMAS -----------------
class BranchCreate(BaseModel):
    name: str

class BranchResponse(BaseSchema):
    branch_id: int
    name: str

# ----------------- SEMESTER SCHEMAS -----------------
class SemesterCreate(BaseModel):
    number: int
    name: str
    status: Optional[str] = "Active"

class SemesterResponse(BaseSchema):
    semester_id: int
    number: int
    name: str
    status: str

# ----------------- USER SCHEMAS -----------------
class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    branch_id: int
    semester_id: Optional[int] = None
    role: Optional[str] = "student"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseSchema):
    user_id: int
    full_name: str
    email: EmailStr
    role: str
    branch_id: int
    semester_id: Optional[int] = None
    branch: Optional[str] = None
    semester_name: Optional[str] = None
    average_grade: Optional[float] = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None

# ----------------- COURSE SCHEMAS -----------------
class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    branch_id: int
    semester_id: int
    teacher_id: int

class CourseResponse(BaseSchema):
    course_id: int
    title: str
    description: Optional[str] = None
    branch_id: int
    semester_id: int
    teacher_id: Optional[int] = None
    branch: Optional[str] = None
    semester_name: Optional[str] = None
    teacher_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    progress: Optional[float] = 0.0
    modules_completed: Optional[int] = 0
    modules_total: Optional[int] = 0
    assignments_submitted: Optional[int] = 0
    assignments_total: Optional[int] = 0
    quizzes_attempted: Optional[int] = 0
    quizzes_total: Optional[int] = 0
    attendance_percentage: Optional[float] = 100.0

# ----------------- MODULE SCHEMAS -----------------
class ModuleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    order_num: int

class ModuleResponse(BaseSchema):
    module_id: int
    course_id: int
    title: str
    description: Optional[str] = None
    order_num: int

# ----------------- MATERIAL SCHEMAS -----------------
class MaterialResponse(BaseSchema):
    material_id: int
    module_id: int
    title: Optional[str] = None
    file_path: str
    file_type: Optional[str] = None
    uploaded_at: datetime

# ----------------- ASSIGNMENT SCHEMAS -----------------
class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: date
    total_marks: Optional[int] = None

class AssignmentResponse(BaseSchema):
    assignment_id: int
    course_id: int
    title: str
    description: Optional[str] = None
    due_date: date
    total_marks: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    student_status: Optional[str] = None
    submitted_at: Optional[datetime] = None
    grade: Optional[int] = None
    feedback: Optional[str] = None
    course_title: Optional[str] = None

# ----------------- SUBMISSION SCHEMAS -----------------
class SubmissionResponse(BaseSchema):
    submission_id: int
    assignment_id: int
    student_id: int
    file_path: str
    submitted_at: datetime
    updated_at: Optional[datetime] = None
    marks: Optional[int] = None
    feedback: Optional[str] = None
    status: str

class GradeSubmission(BaseModel):
    marks: int
    feedback: Optional[str] = None

# ----------------- OPTION SCHEMAS -----------------
class OptionCreate(BaseModel):
    option_text: str
    is_correct: bool = False

class OptionResponse(BaseSchema):
    option_id: int
    question_id: int
    option_text: str
    is_correct: bool

# ----------------- QUESTION SCHEMAS -----------------
class QuestionCreate(BaseModel):
    question_text: str
    question_type: str = Field(..., pattern="^(mcq|tf|descriptive)$")
    options: Optional[List[OptionCreate]] = None
    marks: int

class QuestionResponse(BaseSchema):
    question_id: int
    quiz_id: int
    question_text: str
    question_type: str
    marks: int
    options: List[OptionResponse] = []

# ----------------- QUIZ SCHEMAS -----------------
class QuizCreate(BaseModel):
    title: str
    total_marks: Optional[int] = None
    time_limit: Optional[int] = None
    attempts_allowed: Optional[int] = 1

class QuizResponse(BaseSchema):
    quiz_id: int
    course_id: int
    title: str
    total_marks: Optional[int] = None
    time_limit: Optional[int] = None
    attempts_allowed: Optional[int] = 1
    student_status: Optional[str] = None
    score: Optional[int] = None

# ----------------- QUIZ ATTEMPT SCHEMAS -----------------
class AnswerSubmit(BaseModel):
    question_id: int
    selected_option_id: Optional[int] = None
    text_answer: Optional[str] = None

class QuizAttemptCreate(BaseModel):
    answers: List[AnswerSubmit]

class QuizAttemptResponse(BaseSchema):
    attempt_id: int
    quiz_id: int
    student_id: int
    score: Optional[int] = None
    attempt_date: datetime

# ----------------- ENROLLMENT SCHEMAS -----------------
class EnrollmentResponse(BaseSchema):
    enrollment_id: int
    student_id: int
    course_id: int
    enrolled_at: datetime
    completion_pct: Decimal

# ----------------- NOTIFICATION SCHEMAS -----------------
class NotificationCreate(BaseModel):
    user_id: Optional[int] = None
    title: str
    message: str

class NotificationResponse(BaseSchema):
    notification_id: int
    user_id: Optional[int] = None
    title: str
    message: str
    is_read: bool
    created_at: datetime

# ----------------- REVIEW SCHEMAS -----------------
class ReviewCreate(BaseModel):
    course_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class ReviewResponse(BaseSchema):
    review_id: int
    student_id: int
    course_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime

# ----------------- ATTENDANCE SCHEMAS -----------------
class AttendanceRecord(BaseModel):
    student_id: int
    status: str # 'Present', 'Absent'

class AttendanceSubmit(BaseModel):
    course_id: int
    date: date
    records: List[AttendanceRecord]

# ----------------- DISCUSSION SCHEMAS -----------------
class DiscussionPostCreate(BaseModel):
    title: str
    content: str
    is_announcement: bool = False

class DiscussionReplyCreate(BaseModel):
    content: str

# ----------------- EMAIL BROADCAST SCHEMAS -----------------
class EmailBroadcast(BaseModel):
    subject: str
    body: str
    target_type: str # 'all', 'students', 'teachers', 'branch_sem'
    branch_id: Optional[int] = None
    semester_id: Optional[int] = None

# ----------------- CLASSROOM SESSION SCHEMAS -----------------
class ClassroomSessionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    session_date: date
    start_time: str
    end_time: str
    room: Optional[str] = None
    meeting_link: Optional[str] = None

class ClassroomSessionResponse(BaseSchema):
    session_id: int
    course_id: int
    title: str
    description: Optional[str] = None
    session_date: date
    start_time: str
    end_time: str
    room: Optional[str] = None
    meeting_link: Optional[str] = None
    created_at: datetime


