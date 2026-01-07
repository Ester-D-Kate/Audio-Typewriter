from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router.auth import router as auth_router
from router.oauth import router as oauth_router
from core.config import settings
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Audio Typewriter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(oauth_router, prefix="/auth")


@app.get("/")
async def root():
    return {"status": "Audio Typewriter API is running"}

