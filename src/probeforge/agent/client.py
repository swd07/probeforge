"""Meta Model API client setup.

Values checked against https://dev.meta.ai/docs on 2026-10-27:
- Chat Completions endpoint is OpenAI-compatible at https://api.meta.ai/v1
- Muse Spark model id is "muse-spark-1.3" (Muse Wonder preview: "muse-wonder-1.0")
- Only tool_choice="auto" is supported; reasoning_effort="none" returns HTTP 400
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

META_BASE_URL = "https://api.meta.ai/v1"
MUSE_SPARK = "muse-spark-1.3"
MUSE_WONDER = "muse-wonder-1.0"


def make_client() -> OpenAI:
    """Build an OpenAI SDK client pointed at the Meta Model API.

    The key is read from META_API_KEY (project convention). MODEL_API_KEY,
    the name used in the Meta docs, is accepted as a fallback.
    """
    load_dotenv()
    key = os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("META_API_KEY is not set (put it in .env)")
    return OpenAI(base_url=os.environ.get("META_BASE_URL", META_BASE_URL), api_key=key)
