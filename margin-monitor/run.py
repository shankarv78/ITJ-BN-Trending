"""
Margin Monitor - Application Runner
"""

import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.mm_host,
        port=settings.mm_port,
        reload=True,
        log_level="info",
    )
