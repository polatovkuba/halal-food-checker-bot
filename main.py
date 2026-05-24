import asyncio
import os
from app.bot import main
from fastapi import FastAPI
import uvicorn
import multiprocessing

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok"}

def run_bot():
    asyncio.run(main())

def run_web():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

if __name__ == "__main__":
    bot_process = multiprocessing.Process(target=run_bot)
    bot_process.start()
    run_web()