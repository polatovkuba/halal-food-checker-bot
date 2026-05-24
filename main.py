import asyncio
import threading
from app.bot import main
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok"}

def run_bot():
    asyncio.run(main())

if __name__ == "__main__":
    thread = threading.Thread(target=run_bot)
    thread.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)