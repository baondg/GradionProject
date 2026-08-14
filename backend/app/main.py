from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

app = FastAPI(title="Book Illustration Studio")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
