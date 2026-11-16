
from fastapi import FastAPI

# Create CLUMS application
app = FastAPI(
    title="CLUMS Backend",
    description="Computer Laboratory User Monitoring System",
    version="1.0.0"
)


# Homepage
@app.get("/")
def home():
    return {
        "message": "Welcome to CLUMS Backend!",
        "status": "running"
    }


# Backend health check
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": "CLUMS"
    }
