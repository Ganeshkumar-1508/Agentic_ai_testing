import os
print("ENV_FROM_PROCESS:", os.environ.get("OPENAI_API_KEY", "NONE")[:20])
print("ENV_FROM_PROCESS_LEN:", len(os.environ.get("OPENAI_API_KEY", "")))
