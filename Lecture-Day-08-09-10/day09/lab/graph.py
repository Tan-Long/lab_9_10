"""
graph.py — Supervisor Orchestrator
Sprint 1: Implement AgentState, supervisor_node, route_decision và kết nối graph.

Kiến trúc:
    Input → Supervisor → [retrieval_worker | policy_tool_worker | human_review] → synthesis → Output

Chạy thử:
    python graph.py
"""

import json
import os
from datetime import datetime
from typing import TypedDict, Literal, Optional

# Uncomment nếu dùng LangGraph:
# from langgraph.graph import StateGraph, END

# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    task: str                           # Câu hỏi đầu vào từ user

    # Supervisor decisions
    route_reason: str                   # Lý do route sang worker nào
    risk_high: bool                     # True → cần HITL hoặc human_review
    needs_tool: bool                    # True → cần gọi external tool qua MCP
    hitl_triggered: bool                # True → đã pause cho human review
    hitl_decision: str                  # "approved" | "rejected"
    hitl_context: str                   # Context/note từ human reviewer

    # Worker outputs
    retrieved_chunks: list              # Output từ retrieval_worker
    retrieved_sources: list             # Danh sách nguồn tài liệu
    policy_result: dict                 # Output từ policy_tool_worker
    mcp_tools_used: list                # Danh sách MCP tools đã gọi

    # Final output
    final_answer: str                   # Câu trả lời tổng hợp
    sources: list                       # Sources được cite
    confidence: float                   # Mức độ tin cậy (0.0 - 1.0)

    # Trace & history
    history: list                       # Lịch sử các bước đã qua
    workers_called: list                # Danh sách workers đã được gọi
    supervisor_route: str               # Worker được chọn bởi supervisor
    latency_ms: Optional[int]           # Thời gian xử lý (ms)
    run_id: str                         # ID của run này


def make_initial_state(task: str) -> AgentState:
    """Khởi tạo state cho một run mới."""
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "hitl_decision": "",
        "hitl_context": "",
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor phân tích task và quyết định:
    1. Route sang worker nào
    2. Có cần MCP tool không
    3. Có risk cao cần HITL không

    TODO Sprint 1: Implement routing logic dựa vào task keywords.
    """
    task = state["task"].lower()
    state["history"].append(f"[supervisor] received task: {state['task'][:80]}")

    # --- TODO: Implement routing logic ---
    # Gợi ý:
    # - "hoàn tiền", "refund", "flash sale", "license" → policy_tool_worker
    # - "cấp quyền", "access level", "level 3", "emergency" → policy_tool_worker
    # - "P1", "escalation", "sla", "ticket" → retrieval_worker
    # - mã lỗi không rõ (ERR-XXX), không đủ context → human_review
    # - còn lại → retrieval_worker

    route = "retrieval_worker"
    route_reason = "default: no specific keyword matched → retrieval_worker"
    needs_tool = False
    risk_high = False

    policy_keywords = [
        "hoàn tiền", "refund", "flash sale", "license", "license key",
        "cấp quyền", "access level", "level 3", "level 2", "access",
        "subscription", "kỹ thuật số", "store credit",
    ]
    risk_keywords = ["emergency", "khẩn cấp", "2am", "không rõ"]
    sla_keywords = ["p1", "sla", "ticket", "escalation", "sự cố", "on-call", "oncall", "incident"]
    # Keywords cho thấy error code đã có đủ context → không cần HITL
    incident_context_keywords = [
        "crash", "down", "sập", "nghiêm trọng", "khẩn cấp", "xử lý ngay",
        "p1", "incident", "production", "db", "database", "api", "gateway",
        "không đăng nhập", "không truy cập", "toàn bộ", "critical",
    ]

    task_lower_stripped = task  # already lowered above

    # Priority 1: policy / access control questions
    matched_policy = [kw for kw in policy_keywords if kw in task_lower_stripped]
    if matched_policy:
        route = "policy_tool_worker"
        route_reason = f"task contains policy/access keyword(s): {matched_policy}"
        needs_tool = True

    # Priority 2: SLA / ticket questions (override to retrieval unless policy also needed)
    matched_sla = [kw for kw in sla_keywords if kw in task_lower_stripped]
    if matched_sla and not matched_policy:
        route = "retrieval_worker"
        route_reason = f"task contains SLA/ticket keyword(s): {matched_sla}"

    # Risk flag (err- không còn trong risk_keywords, xử lý riêng bên dưới)
    matched_risk = [kw for kw in risk_keywords if kw in task_lower_stripped]
    if matched_risk:
        risk_high = True
        route_reason += f" | risk_high flagged: {matched_risk}"

    # Human review: chỉ khi có error code KHÔNG rõ và KHÔNG có incident context
    import re
    err_match = re.search(r"err-\d+", task_lower_stripped)
    if err_match:
        has_incident_context = any(kw in task_lower_stripped for kw in incident_context_keywords)
        if has_incident_context:
            # Có context đủ → treat như P1 incident, route retrieval
            risk_high = True
            if route != "policy_tool_worker":
                route = "retrieval_worker"
            route_reason += f" | known incident pattern (err code + context) → retrieval"
        else:
            # Không rõ error code, không có context → cần human review
            risk_high = True
            route = "human_review"
            route_reason = f"unknown error code '{err_match.group()}' without incident context → human review"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(f"[supervisor] route={route} reason={route_reason}")

    return state


# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của graph.
    """
    route = state.get("supervisor_route", "retrieval_worker")
    return route  # type: ignore


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL placeholder
# ─────────────────────────────────────────────

def human_review_node(state: AgentState, hitl_handler=None) -> AgentState:
    """
    HITL node: pause và chờ human approval.

    Nếu có hitl_handler (callable), gọi handler và block cho đến khi
    human quyết định approve/reject. Handler nhận state, trả về dict:
        {"action": "approve"|"reject", "context": str}

    Nếu không có handler → auto-approve (lab mode).
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    if hitl_handler is not None:
        # Real HITL: block until human decides
        decision = hitl_handler(state)
        action  = decision.get("action", "approve")
        context = decision.get("context", "")
        state["hitl_decision"] = action
        state["hitl_context"]  = context

        if action == "reject":
            state["final_answer"] = (
                "Yêu cầu đã bị từ chối bởi human reviewer.\n"
                + (f"Lý do: {context}" if context else "Không có lý do thêm.")
            )
            state["confidence"] = 0.0
            state["history"].append(f"[human_review] REJECTED — {context}")
            return state

        if context:
            state["history"].append(f"[human_review] APPROVED with context: {context[:80]}")
        else:
            state["history"].append("[human_review] APPROVED — continuing to retrieval")
    else:
        # Auto-approve (backward-compat / lab mode)
        state["hitl_decision"] = "approved"
        print(f"\n⚠️  HITL TRIGGERED (auto-approve)")
        print(f"   Task: {state['task']}")
        print(f"   Reason: {state['route_reason']}\n")

    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved → retrieval"
    return state


# ─────────────────────────────────────────────
# 5. Import Workers
# ─────────────────────────────────────────────

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi retrieval worker."""
    return retrieval_run(state)


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi policy/tool worker."""
    return policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi synthesis worker."""
    return synthesis_run(state)


# ─────────────────────────────────────────────
# 6. Build Graph
# ─────────────────────────────────────────────

def build_graph(callbacks: dict = None):
    """
    Xây dựng graph với supervisor-worker pattern.

    callbacks (optional dict):
        on_supervisor(state)          — gọi sau supervisor_node
        on_worker_start(name, state)  — gọi trước mỗi worker
        on_worker_done(name, state)   — gọi sau mỗi worker
        on_hitl(state) -> dict        — HITL handler, block đến khi có quyết định
                                        trả về {"action": "approve"|"reject", "context": str}
        on_done(state)                — gọi khi pipeline kết thúc
    """
    cb = callbacks or {}

    def _cb(name, *args):
        fn = cb.get(name)
        if fn:
            return fn(*args)

    def run(state: AgentState) -> AgentState:
        import time
        start = time.time()

        # Step 1: Supervisor decides route
        state = supervisor_node(state)
        _cb("on_supervisor", state)

        # Step 2: Route to appropriate worker
        route = route_decision(state)

        if route == "human_review":
            _cb("on_worker_start", "human_review", state)
            state = human_review_node(state, hitl_handler=cb.get("on_hitl"))
            _cb("on_worker_done", "human_review", state)

            # If rejected, skip remaining workers
            if state.get("hitl_decision") == "reject":
                state["latency_ms"] = int((time.time() - start) * 1000)
                _cb("on_done", state)
                return state

            # After approval, continue with retrieval
            _cb("on_worker_start", "retrieval_worker", state)
            state = retrieval_worker_node(state)
            _cb("on_worker_done", "retrieval_worker", state)

        elif route == "policy_tool_worker":
            _cb("on_worker_start", "policy_tool_worker", state)
            state = policy_tool_worker_node(state)
            _cb("on_worker_done", "policy_tool_worker", state)

            if not state["retrieved_chunks"]:
                _cb("on_worker_start", "retrieval_worker", state)
                state = retrieval_worker_node(state)
                _cb("on_worker_done", "retrieval_worker", state)

        else:
            _cb("on_worker_start", "retrieval_worker", state)
            state = retrieval_worker_node(state)
            _cb("on_worker_done", "retrieval_worker", state)

        # Step 3: Synthesize
        _cb("on_worker_start", "synthesis_worker", state)
        state = synthesis_worker_node(state)
        _cb("on_worker_done", "synthesis_worker", state)

        state["latency_ms"] = int((time.time() - start) * 1000)
        state["history"].append(f"[graph] completed in {state['latency_ms']}ms")
        _cb("on_done", state)
        return state

    return run


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


def run_graph(task: str) -> AgentState:
    """
    Entry point: nhận câu hỏi, trả về AgentState với full trace.

    Args:
        task: Câu hỏi từ user

    Returns:
        AgentState với final_answer, trace, routing info, v.v.
    """
    state = make_initial_state(task)
    result = _graph(state)
    return result


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Lưu trace ra file JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Day 09 Lab — Supervisor-Worker Graph")
    print("=" * 60)

    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = run_graph(query)
        print(f"  Route   : {result['supervisor_route']}")
        print(f"  Reason  : {result['route_reason']}")
        print(f"  Workers : {result['workers_called']}")
        print(f"  Answer  : {result['final_answer'][:100]}...")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency : {result['latency_ms']}ms")

        # Lưu trace
        trace_file = save_trace(result)
        print(f"  Trace saved → {trace_file}")

    print("\n✅ graph.py test complete. Implement TODO sections in Sprint 1 & 2.")
