import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

TOP_K_SEARCH = 10
TOP_K_SELECT = 3

# Cache for BM25 index to avoid re-calculating
_bm25_index = None
_bm25_corpus_chunks = None

# =============================================================================
# RETRIEVAL — DENSE (Vector Search)
# =============================================================================

def retrieve_dense(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    import chromadb
    from index import get_embedding, CHROMA_DB_DIR

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    collection = client.get_collection("rag_lab")

    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    chunks = []
    if results["documents"]:
        for i in range(len(results["documents"][0])):
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i]
            })
    
    return chunks

# =============================================================================
# RETRIEVAL — SPARSE / HYBRID (Stubs for Sprint 3)
# =============================================================================

def retrieve_sparse(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Sparse retrieval: tìm kiếm theo keyword (BM25).
    """
    global _bm25_index, _bm25_corpus_chunks
    
    from rank_bm25 import BM25Okapi
    import chromadb
    from index import CHROMA_DB_DIR
    import re
    
    if _bm25_index is None:
        print("[retrieve_sparse] Loading chunks and building BM25 index...")
        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        collection = client.get_collection("rag_lab")
        results = collection.get(include=["documents", "metadatas"])
        
        if not results["documents"]:
            print("[retrieve_sparse] Warning: No documents found in index.")
            return []
            
        _bm25_corpus_chunks = []
        tokenized_corpus = []
        
        for doc, meta in zip(results["documents"], results["metadatas"]):
            _bm25_corpus_chunks.append({"text": doc, "metadata": meta})
            # Simple tokenizer for BM25
            tokens = re.findall(r'\w+', doc.lower())
            tokenized_corpus.append(tokens)
            
        _bm25_index = BM25Okapi(tokenized_corpus)
        print(f"[retrieve_sparse] Index built with {len(_bm25_corpus_chunks)} chunks.")

    # Search
    query_tokens = re.findall(r'\w+', query.lower())
    scores = _bm25_index.get_scores(query_tokens)
    
    # Get top_k
    import numpy as np
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            chunk = _bm25_corpus_chunks[idx].copy()
            chunk["score"] = float(scores[idx])
            results.append(chunk)
            
    return results

def retrieve_hybrid(
    query: str, 
    top_k: int = TOP_K_SEARCH,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: kết hợp dense và sparse bằng Reciprocal Rank Fusion (RRF).
    """
    dense_results = retrieve_dense(query, top_k=top_k * 2)
    sparse_results = retrieve_sparse(query, top_k=top_k * 2)
    
    # RRF scoring
    rrf_scores = {} # (text, source) -> rrf_score
    chunk_map = {} # (text, source) -> chunk_data
    
    K = 60 # RRF constant
    
    for rank, chunk in enumerate(dense_results, 1):
        key = (chunk["text"], chunk["metadata"].get("source", ""))
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (K + rank)
        chunk_map[key] = chunk

    for rank, chunk in enumerate(sparse_results, 1):
        key = (chunk["text"], chunk["metadata"].get("source", ""))
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (K + rank)
        chunk_map[key] = chunk
        
    # Sort by RRF score
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    hybrid_results = []
    for key in sorted_keys[:top_k]:
        chunk = chunk_map[key].copy()
        chunk["rrf_score"] = rrf_scores[key]
        hybrid_results.append(chunk)
        
    return hybrid_results

# =============================================================================
# GENERATION
# =============================================================================

def build_context_block(candidates: List[Dict[str, Any]]) -> str:
    context_parts = []
    for i, c in enumerate(candidates):
        source = c["metadata"].get("source", "unknown")
        section = c["metadata"].get("section", "General")
        context_parts.append(f"[{i+1}] Source: {source} | Section: {section}\nContent: {c['text']}")
    return "\n\n".join(context_parts)

def build_grounded_prompt(query: str, context_block: str) -> str:
    prompt = f"""Answer only from the retrieved context below.
If the context is insufficient to answer the question, say you do not know and do not make up information.
Cite the source field (in brackets like [1]) when possible.
Keep your answer short, clear, and factual.
Respond in the same language as the question.

Question: {query}

Context:
{context_block}

Answer:"""
    return prompt

def call_llm(prompt: str) -> str:
    """
    Gọi LLM (Gemini hoặc OpenAI) để sinh câu trả lời grounded.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "mock":
        # Offline fallback for lab environments without API keys.
        if "Output strictly valid JSON" in prompt:
            return '{"score": 3, "reason": "Mock evaluator output (no API key)."}'
        return "Không đủ dữ liệu để trả lời chắc chắn từ ngữ cảnh hiện có. [1]"
    
    if provider == "gemini":
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in .env")
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0, max_output_tokens=512)
        )
        return response.text.strip()
    
    elif provider == "openai":
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env")
        client = OpenAI(api_key=api_key)
        model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512
        )
        return response.choices[0].message.content.strip()
    
    else:
        raise ValueError(f"LLM_PROVIDER không hợp lệ: {provider}")

# =============================================================================
# PIPELINE
# =============================================================================

def rag_answer(
    query: str, 
    retrieval_mode: str = "dense", 
    top_k_search: int = TOP_K_SEARCH, 
    top_k_select: int = TOP_K_SELECT, 
    use_rerank: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    if retrieval_mode == "dense":
        candidates = retrieve_dense(query, top_k=top_k_search)
    elif retrieval_mode == "hybrid":
        candidates = retrieve_hybrid(query, top_k=top_k_search)
    else:
        raise ValueError(f"Unsupported mode: {retrieval_mode}")

    if use_rerank:
        # Placeholder for rerank if needed in future
        pass

    candidates = candidates[:top_k_select]
    context_block = build_context_block(candidates)
    prompt = build_grounded_prompt(query, context_block)
    answer = call_llm(prompt)
    sources = list({c["metadata"].get("source", "unknown") for c in candidates})

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "chunks_used": candidates,
        "config": {
            "retrieval_mode": retrieval_mode,
            "top_k_search": top_k_search,
            "top_k_select": top_k_select,
            "use_rerank": use_rerank
        }
    }

def compare_retrieval_strategies(query: str) -> None:
    """
    So sánh Dense vs Hybrid strategies.
    """
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    strategies = ["dense", "hybrid"]

    for strategy in strategies:
        print(f"\n--- Strategy: {strategy.upper()} ---")
        try:
            result = rag_answer(query, retrieval_mode=strategy, verbose=False)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except Exception as e:
            print(f"Lỗi: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 3: Hybrid Search Comparison")
    print("=" * 60)

    # Test với câu hỏi chứa thuật ngữ chuyên môn hoặc từ khóa
    queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Approval Matrix để cấp quyền là tài liệu nào?",
        "Chính sách hoàn tiền áp dụng cho các đơn hàng từ ngày nào?"
    ]

    for q in queries:
        compare_retrieval_strategies(q)
