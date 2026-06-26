from sqlalchemy import Column, Integer, String, Text, ForeignKey, TIMESTAMP, Date, Boolean, Numeric, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Branch(Base):
    __tablename__ = "branches"
    
    branch_id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True)
    
    users = relationship("User", back_populates="branch")
    courses = relationship("Course", back_populates="branch")
    batches = relationship("Batch", back_populates="branch")

class Semester(Base):
    __tablename__ = "semesters"
    
    semester_id = Column(Integer, primary_key=True, index=True)
    number = Column(Integer, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="Active")
    
    __table_args__ = (
        CheckConstraint("status IN ('Active', 'Planned', 'Archived')", name="semester_status_check"),
    )
    
    users = relationship("User", back_populates="semester")
    courses = relationship("Course", back_populates="semester")
    batches = relationship("Batch", back_populates="semester")

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(Text, nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(10), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.semester_id"))
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        CheckConstraint("role IN ('student', 'teacher', 'admin')", name="role_check"),
    )
    
    branch = relationship("Branch", back_populates="users")
    semester = relationship("Semester", back_populates="users")
    managed_batches = relationship("Batch", back_populates="teacher")
    managed_courses = relationship("Course", back_populates="teacher")
    submissions = relationship("Submission", back_populates="student")
    quiz_attempts = relationship("QuizAttempt", back_populates="student")
    enrollments = relationship("Enrollment", back_populates="student")
    notifications = relationship("Notification", back_populates="user")
    certificates = relationship("Certificate", back_populates="student")
    reviews = relationship("Review", back_populates="student")
    activity_logs = relationship("ActivityLog", back_populates="user")

class Batch(Base):
    __tablename__ = "batches"
    
    batch_id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.semester_id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("branch_id", "semester_id", "teacher_id", name="unique_batch"),
    )
    
    branch = relationship("Branch", back_populates="batches")
    semester = relationship("Semester", back_populates="batches")
    teacher = relationship("User", back_populates="managed_batches")
    enrollments = relationship("Enrollment", back_populates="batch")

class Course(Base):
    __tablename__ = "courses"
    
    course_id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.semester_id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    branch = relationship("Branch", back_populates="courses")
    semester = relationship("Semester", back_populates="courses")
    teacher = relationship("User", back_populates="managed_courses")
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="course", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="course", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="course", cascade="all, delete-orphan")

class Module(Base):
    __tablename__ = "modules"
    
    module_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    order_num = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint("course_id", "order_num", name="unique_course_module_order"),
    )
    
    course = relationship("Course", back_populates="modules")
    materials = relationship("Material", back_populates="module", cascade="all, delete-orphan")

class Material(Base):
    __tablename__ = "materials"
    
    material_id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.module_id"), nullable=False)
    title = Column(Text)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(20))
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    module = relationship("Module", back_populates="materials")

class Assignment(Base):
    __tablename__ = "assignments"
    
    assignment_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    due_date = Column(Date, nullable=False)
    total_marks = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    course = relationship("Course", back_populates="assignments")
    submissions = relationship("Submission", back_populates="assignment", cascade="all, delete-orphan")

class Submission(Base):
    __tablename__ = "submissions"
    
    submission_id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.assignment_id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    file_path = Column(Text, nullable=False)
    submitted_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    marks = Column(Integer)
    feedback = Column(Text)
    status = Column(String(20), nullable=False, default="Pending")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="unique_student_assignment_submission"),
    )
    
    assignment = relationship("Assignment", back_populates="submissions")
    student = relationship("User", back_populates="submissions")

class Quiz(Base):
    __tablename__ = "quizzes"
    
    quiz_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    title = Column(Text, nullable=False)
    total_marks = Column(Integer)
    time_limit = Column(Integer) # in minutes
    attempts_allowed = Column(Integer, default=1)
    
    course = relationship("Course", back_populates="quizzes")
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")

class Question(Base):
    __tablename__ = "questions"
    
    question_id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.quiz_id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(10), nullable=False)
    marks = Column(Integer, nullable=False)
    
    __table_args__ = (
        CheckConstraint("question_type IN ('mcq', 'tf', 'descriptive')", name="question_type_check"),
    )
    
    quiz = relationship("Quiz", back_populates="questions")
    options = relationship("Option", back_populates="question", cascade="all, delete-orphan")

class Option(Base):
    __tablename__ = "options"
    
    option_id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.question_id"), nullable=False)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    
    question = relationship("Question", back_populates="options")

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    
    attempt_id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.quiz_id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    score = Column(Integer)
    attempt_date = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint("quiz_id", "student_id", name="unique_student_quiz_attempt"),
    )
    
    quiz = relationship("Quiz", back_populates="attempts")
    student = relationship("User", back_populates="quiz_attempts")

class Enrollment(Base):
    __tablename__ = "enrollments"
    
    enrollment_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.batch_id"))
    enrolled_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completion_pct = Column(Numeric(5, 2), default=0)
    
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="unique_student_course_enrollment"),
    )
    
    student = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    batch = relationship("Batch", back_populates="enrollments")

class Notification(Base):
    __tablename__ = "notifications"
    
    notification_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    title = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="notifications")

class Certificate(Base):
    __tablename__ = "certificates"
    
    certificate_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    certificate_url = Column(Text, nullable=False)
    issued_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="unique_student_course_certificate"),
    )
    
    student = relationship("User", back_populates="certificates")
    course = relationship("Course", back_populates="certificates")

class Review(Base):
    __tablename__ = "reviews"
    
    review_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    rating = Column(Integer)
    comment = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range_check"),
        UniqueConstraint("student_id", "course_id", name="unique_student_course_review"),
    )
    
    student = relationship("User", back_populates="reviews")
    course = relationship("Course", back_populates="reviews")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    action = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="activity_logs")

class Setting(Base):
    __tablename__ = "settings"
    
    setting_key = Column(String(50), primary_key=True)
    setting_value = Column(Text, nullable=False)

class Attendance(Base):
    __tablename__ = "attendance"
    
    attendance_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(String(10), nullable=False) # 'Present', 'Absent'
    
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "date", name="unique_student_course_attendance_date"),
    )
    
    student = relationship("User")
    course = relationship("Course")

class DiscussionPost(Base):
    __tablename__ = "discussion_posts"
    
    post_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    is_announcement = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    course = relationship("Course")
    user = relationship("User")
    replies = relationship("DiscussionReply", back_populates="post", cascade="all, delete-orphan")

class DiscussionReply(Base):
    __tablename__ = "discussion_replies"
    
    reply_id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("discussion_posts.post_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    post = relationship("DiscussionPost", back_populates="replies")
    user = relationship("User")

class Bookmark(Base):
    __tablename__ = "bookmarks"
    
    bookmark_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    module_id = Column(Integer, ForeignKey("modules.module_id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    student = relationship("User")
    module = relationship("Module")

class RecentlyViewed(Base):
    __tablename__ = "recently_viewed"
    
    view_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    viewed_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    student = relationship("User")
    course = relationship("Course")

class DownloadHistory(Base):
    __tablename__ = "download_history"
    
    download_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.material_id"), nullable=False)
    downloaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    student = relationship("User")
    material = relationship("Material")

class LoginHistory(Base):
    __tablename__ = "login_history"
    
    history_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    logged_in_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    user = relationship("User")
