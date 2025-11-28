"""
Backend Entry Point
Run with: uv run python main.py
Or: uv run uvicorn app.main:app --reload
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8090, reload=True)
