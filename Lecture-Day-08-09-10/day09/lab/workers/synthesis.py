"""
workers/synthesis.py — Synthesis Worker
Sprint 2: Tổng hợp câu trả lời từ retrieved_chunks và policy_result.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: evidence từ retrieval_worker
    - policy_result: kết quả từ policy_tool_worker

Output (vào AgentState):
    - final_answer: câu trả lời cuối với citation
    - sources: danh sách nguồn tài liệu được cite
    - confidence: mức độ tin cậy (0.0 - 1.0)

Gọi độc lập để test:
    python workers/synthesis.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

WORKER_NAME = "synthesis_worker"

SYSTEM_PROMPT = """Bạn là trợ lý IT Helpdesk nội bộ.

Quy tắc nghiêm ngặt:
1. CHỈ trả lời dựa vào context được cung cấp. KHÔNG dùng kiến thức ngoài.
2. Nếu context không đủ để trả lời → nói rõ "Không đủ thông tin trong tài liệu nội bộ".
3. Trích dẫn nguồn cuối mỗi câu quan trọng: [tên_file].
4. Trả lời súc tích, có cấu trúc. Không dài dòng.
5. Nếu có exceptions/ngoại lệ → nêu rõ ràng trước khi kết luận.
6. QUAN TRỌNG — Xử lý Policy Version Mismatch: Nếu phần POLICY EXCEPTIONS chứa thông báo về "chính sách phiên bản 3" hoặc "v3" hoặc "không có trong tài liệu hiện tại" liên quan đến chính sách áp dụng cho đơn hàng → PHẢI trả lời: "Đơn hàng này được đặt trước ngày áp dụng chính sách v4 (01/02/2026), do đó áp dụng chính sách hoàn tiền phiên bản 3. Tài liệu hiện tại chỉ có v4. Không thể xác nhận theo v3 — cần liên hệ CS Team để tra cứu chính sách v3." KHÔNG được áp dụng điều kiện v4 cho đơn hàng trước 01/02/2026.
"""


def _call_llm(messages: list) -> str:
    """
    Gọi LLM để tổng hợp câu trả lời.
    Thử OpenAI → Gemini → Anthropic Claude → rule-based fallback.
    """
    # Option A: OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("sk-..."):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.1,
                max_tokens=500,
            )
            return response.choices[0].message.content
        except Exception:
            pass

    # Option B: Gemini
    google_key = os.getenv("GOOGLE_API_KEY", "")
    if google_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            combined = "\n".join([m["content"] for m in messages])
            response = model.generate_content(combined)
            return response.text
        except Exception:
            pass

    # Option C: Anthropic Claude
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system=system_msg,
                messages=[{"role": "user", "content": user_msg}],
            )
            return response.content[0].text
        except Exception:
            pass

    # Option D: Rule-based extraction fallback (no LLM needed)
    return _rule_based_synthesis(messages)


def _rule_based_synthesis(messages: list) -> str:
    """
    Fallback: xây dựng câu trả lời từ chunks bằng rule-based extraction.
    Không hallucinate — chỉ dùng text từ context.
    """
    user_content = ""
    for m in messages:
        if m.get("role") == "user":
            user_content = m["content"]
            break

    if not user_content or "TÀI LIỆU THAM KHẢO" not in user_content:
        return "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."

    # Extract question
    lines = user_content.split("\n")
    question = ""
    for line in lines:
        if line.startswith("Câu hỏi:"):
            question = line.replace("Câu hỏi:", "").strip()
            break

    # Extract context blocks
    context_section = user_content.split("=== TÀI LIỆU THAM KHẢO ===")[-1]
    if "=== POLICY EXCEPTIONS ===" in context_section:
        context_part, exception_part = context_section.split("=== POLICY EXCEPTIONS ===", 1)
    else:
        context_part = context_section
        exception_part = ""

    # Parse chunks
    chunks_info = []
    blocks = context_part.strip().split("\n\n")
    for block in blocks:
        block = block.strip()
        if block.startswith("[") and "Nguồn:" in block:
            lines_b = block.split("\n")
            header = lines_b[0]  # [1] Nguồn: sla_p1_2026.txt (relevance: 0.85)
            text = "\n".join(lines_b[1:]).strip()
            # Extract source name
            import re
            src_match = re.search(r"Nguồn: (\S+)", header)
            src = src_match.group(1) if src_match else "unknown"
            chunks_info.append({"source": src, "text": text})

    if not chunks_info:
        return "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."

    # Build answer
    parts = []

    # Add exception warnings first
    if exception_part.strip():
        for line in exception_part.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                parts.append(f"**Lưu ý ngoại lệ:** {line}")

    # Add evidence from chunks
    for i, chunk in enumerate(chunks_info, 1):
        text = chunk["text"].strip()
        if text:
            parts.append(f"{text} [{chunk['source']}]")

    if not parts:
        return "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."

    answer = "\n\n".join(parts)
    return answer


def _build_context(chunks: list, policy_result: dict) -> str:
    """Xây dựng context string từ chunks và policy result."""
    parts = []

    if chunks:
        parts.append("=== TÀI LIỆU THAM KHẢO ===")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            score = chunk.get("score", 0)
            parts.append(f"[{i}] Nguồn: {source} (relevance: {score:.2f})\n{text}")

    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS ===")
        for ex in policy_result["exceptions_found"]:
            parts.append(f"- {ex.get('rule', '')}")

    if not parts:
        return "(Không có context)"

    return "\n\n".join(parts)


def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    """
    Ước tính confidence dựa vào:
    - Số lượng và quality của chunks
    - Có exceptions không
    - Answer có abstain không

    TODO Sprint 2: Có thể dùng LLM-as-Judge để tính confidence chính xác hơn.
    """
    if not chunks:
        return 0.1  # Không có evidence → low confidence

    if "Không đủ thông tin" in answer or "không có trong tài liệu" in answer.lower():
        return 0.3  # Abstain → moderate-low

    # Weighted average của chunk scores
    if chunks:
        avg_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
    else:
        avg_score = 0

    # Penalty nếu có exceptions (phức tạp hơn)
    exception_penalty = 0.05 * len(policy_result.get("exceptions_found", []))

    confidence = min(0.95, avg_score - exception_penalty)
    return round(max(0.1, confidence), 2)


def synthesize(task: str, chunks: list, policy_result: dict) -> dict:
    """
    Tổng hợp câu trả lời từ chunks và policy context.

    Returns:
        {"answer": str, "sources": list, "confidence": float}
    """
    context = _build_context(chunks, policy_result)

    # Build messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Câu hỏi: {task}

{context}

Hãy trả lời câu hỏi dựa vào tài liệu trên."""
        }
    ]

    answer = _call_llm(messages)
    sources = list({c.get("source", "unknown") for c in chunks})
    confidence = _estimate_confidence(chunks, answer, policy_result)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
    }


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy_result = state.get("policy_result", {})

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "has_policy": bool(policy_result),
        },
        "output": None,
        "error": None,
    }

    try:
        result = synthesize(task, chunks, policy_result)
        state["final_answer"] = result["answer"]
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]

        worker_io["output"] = {
            "answer_length": len(result["answer"]),
            "sources": result["sources"],
            "confidence": result["confidence"],
        }
        state["history"].append(
            f"[{WORKER_NAME}] answer generated, confidence={result['confidence']}, "
            f"sources={result['sources']}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        state["final_answer"] = f"SYNTHESIS_ERROR: {e}"
        state["confidence"] = 0.0
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Synthesis Worker — Standalone Test")
    print("=" * 50)

    test_state = {
        "task": "SLA ticket P1 là bao lâu?",
        "retrieved_chunks": [
            {
                "text": "Ticket P1: Phản hồi ban đầu 15 phút kể từ khi ticket được tạo. Xử lý và khắc phục 4 giờ. Escalation: tự động escalate lên Senior Engineer nếu không có phản hồi trong 10 phút.",
                "source": "sla_p1_2026.txt",
                "score": 0.92,
            }
        ],
        "policy_result": {},
    }

    result = run(test_state.copy())
    print(f"\nAnswer:\n{result['final_answer']}")
    print(f"\nSources: {result['sources']}")
    print(f"Confidence: {result['confidence']}")

    print("\n--- Test 2: Exception case ---")
    test_state2 = {
        "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì lỗi nhà sản xuất.",
        "retrieved_chunks": [
            {
                "text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền theo Điều 3 chính sách v4.",
                "source": "policy_refund_v4.txt",
                "score": 0.88,
            }
        ],
        "policy_result": {
            "policy_applies": False,
            "exceptions_found": [{"type": "flash_sale_exception", "rule": "Flash Sale không được hoàn tiền."}],
        },
    }
    result2 = run(test_state2.copy())
    print(f"\nAnswer:\n{result2['final_answer']}")
    print(f"Confidence: {result2['confidence']}")

    print("\n✅ synthesis_worker test done.")
