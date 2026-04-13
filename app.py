import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import json
from pathlib import Path

# Import our RAG logic
import rag_answer
import index

app = FastAPI(title="RAG CS/IT Helpdesk GUI")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    retrieval_mode: str = "dense"
    top_k_search: int = 10
    top_k_select: int = 3

class QueryResponse(BaseModel):
    answer: str
    sources: List[str]
    chunks: List[dict]

# --- API Endpoints ---

@app.post("/api/chat", response_model=QueryResponse)
async def chat(request: QueryRequest):
    try:
        result = rag_answer.rag_answer(
            query=request.query,
            retrieval_mode=request.retrieval_mode,
            top_k_search=request.top_k_search,
            top_k_select=request.top_k_select
        )
        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            chunks=result["chunks_used"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(index.CHROMA_DB_DIR))
        collection = client.get_collection("rag_lab")
        count = collection.count()
        return {"chunk_count": count, "db_path": str(index.CHROMA_DB_DIR)}
    except Exception as e:
        return {"chunk_count": 0, "error": str(e)}

@app.post("/api/index")
async def run_indexing(background_tasks: BackgroundTasks):
    background_tasks.add_task(index.build_index)
    return {"message": "Indexing started in background"}

@app.get("/api/eval")
async def get_evaluation():
    eval_path = Path("results/scorecard_variant.md")
    if eval_path.exists():
        return {"content": eval_path.read_text(encoding="utf-8")}
    return {"content": "Evaluation results not found. Run eval.py first."}

# Serve static files
# Create static dir if it doesn't exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
