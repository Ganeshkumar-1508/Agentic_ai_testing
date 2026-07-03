from __future__ import annotations

import uvicorn
from dotenv import load_dotenv
from pathlib import Path

# Load backend/.env BEFORE anything reads os.environ
load_dotenv(Path(__file__).parent / ".env")

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
