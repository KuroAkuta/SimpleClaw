"""
Simple Agent Web - Backend Entry Point
FastAPI server with SSE streaming support
"""
import sys
from pathlib import Path

# Add parent directory to path for tools import
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import chat_router, sessions_router, tools_router, knowledge_router, subagent_router


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(title="Simple Agent Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(tools_router)
app.include_router(knowledge_router)
app.include_router(subagent_router)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health():
    return {"status": "ok"}


# =============================================================================
# Server Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    from config.settings import settings

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT
    )
