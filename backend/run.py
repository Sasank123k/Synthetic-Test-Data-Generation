import uvicorn
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app

if __name__ == "__main__":
    print("Pre-start route check:", [getattr(r, 'path', '') for r in app.routes])
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
