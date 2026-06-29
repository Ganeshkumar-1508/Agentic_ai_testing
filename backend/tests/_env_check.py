import os
from dotenv import load_dotenv
load_dotenv("/app/.testai/.env")
print("KEY_LEN:", len(os.environ.get("OPENAI_API_KEY", "")))
print("URL:", os.environ.get("OPENAI_BASE_URL", ""))
print("MODEL:", os.environ.get("DEFAULT_MODEL", ""))
