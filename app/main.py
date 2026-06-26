from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .routers import auth, users, courses, assignments, quizzes, notifications, branches, semesters, settings, attendance, discussions, study_tracking, gamification, admin_tools

# Initialize FastAPI application
app = FastAPI(
    title="LMS Backend API",
    description="FastAPI Backend for the Learning Management System (LMS)",
    version="0.1.0"
)

# Configure CORS middleware
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directories exist
os.makedirs("static/uploads/submissions", exist_ok=True)

# Mount static files directory for file uploads download
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API Routers under /api prefix
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")
app.include_router(quizzes.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(branches.router, prefix="/api")
app.include_router(semesters.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(discussions.router, prefix="/api")
app.include_router(study_tracking.router, prefix="/api")
app.include_router(gamification.router, prefix="/api")
app.include_router(admin_tools.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to the LMS Backend API. Access docs at /docs"}
