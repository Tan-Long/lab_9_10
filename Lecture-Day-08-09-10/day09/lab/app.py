"""
app.py — Web Demo Interface (with real HITL)
Day 09: Multi-Agent Orchestration — IT Helpdesk Assistant

Chạy:
    python app.py          → http://localhost:7860
"""

import asyncio
import json
import os
import sys
import threading
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
from graph import build_graph, make_initial_state, save_trace
from mcp_server import list_tools

app = FastAPI(title="Day 09 — Multi-Agent Helpdesk Demo")

# ── HITL registry ──────────────────────────────────────────────
# run_id → {"event": threading.Event, "decision": dict | None}
_pending_hitl: dict[str, dict] = {}


# ── HTML ───────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>IT Helpdesk — Multi-Agent Demo</title>
<style>
:root{
  --bg:#0f1117;--panel:#1a1d27;--border:#2a2d3e;
  --accent:#6c63ff;--accent2:#00d4ff;
  --green:#00e676;--yellow:#ffd740;--red:#ff5252;--orange:#ff9800;
  --text:#e8eaf6;--muted:#7c83a0;--radius:12px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;display:flex;flex-direction:column}

/* header */
header{background:linear-gradient(135deg,#1a1d27,#12141f);border-bottom:1px solid var(--border);padding:18px 32px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.logo{width:40px;height:40px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px}
header h1{font-size:18px;font-weight:700}
header p{font-size:12px;color:var(--muted);margin-top:2px}
.hbadge{margin-left:auto;background:rgba(108,99,255,.15);border:1px solid var(--accent);color:var(--accent);font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;letter-spacing:.5px}

/* layout */
.container{flex:1;display:grid;grid-template-columns:1fr 380px;grid-template-rows:auto 1fr;gap:20px;max-width:1400px;margin:0 auto;width:100%;padding:24px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:20px}
.panel-title{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.panel-title::before{content:'';display:inline-block;width:3px;height:14px;background:var(--accent);border-radius:2px}

/* query */
.query-panel{grid-column:1/2;grid-row:1/2}
.input-area{display:flex;gap:10px;align-items:flex-start}
textarea{flex:1;background:#12141f;border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:14px;padding:12px 14px;resize:vertical;min-height:80px;font-family:inherit;transition:border-color .2s;line-height:1.5}
textarea:focus{outline:none;border-color:var(--accent)}
textarea::placeholder{color:var(--muted)}
.btn-ask{background:linear-gradient(135deg,var(--accent),#5a52e0);border:none;border-radius:8px;color:#fff;font-size:14px;font-weight:600;padding:12px 24px;cursor:pointer;transition:opacity .2s,transform .1s;white-space:nowrap;align-self:flex-end}
.btn-ask:hover{opacity:.9}
.btn-ask:active{transform:scale(.97)}
.btn-ask:disabled{opacity:.5;cursor:not-allowed}
.samples{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
.sbtn{background:rgba(108,99,255,.1);border:1px solid rgba(108,99,255,.3);color:var(--accent);font-size:12px;padding:5px 12px;border-radius:20px;cursor:pointer;transition:background .2s;font-family:inherit}
.sbtn:hover{background:rgba(108,99,255,.2)}

/* answer */
.answer-panel{grid-column:1/2;grid-row:2/3}
.answer-header{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.conf-badge{margin-left:auto;font-size:12px;font-weight:700;padding:4px 12px;border-radius:20px}
.answer-text{background:#12141f;border:1px solid var(--border);border-radius:8px;padding:16px;font-size:14px;line-height:1.7;min-height:120px;white-space:pre-wrap;word-break:break-word}
.answer-text.loading{color:var(--muted);font-style:italic}
.sources-row{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.src-tag{background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.25);color:var(--accent2);font-size:11px;padding:3px 10px;border-radius:20px}

/* right column */
.trace-panel{grid-column:2/3;grid-row:1/3;display:flex;flex-direction:column;gap:16px}
.metrics-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;display:flex;gap:20px}
.metric{text-align:center;flex:1}
.metric-value{font-size:20px;font-weight:800;color:var(--accent2)}
.metric-label{font-size:11px;color:var(--muted);margin-top:2px}

.route-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.route-pill{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:700;padding:6px 14px;border-radius:20px;margin-bottom:8px}
.route-pill.retrieval{background:rgba(0,230,118,.1);color:var(--green);border:1px solid rgba(0,230,118,.3)}
.route-pill.policy{background:rgba(255,215,64,.1);color:var(--yellow);border:1px solid rgba(255,215,64,.3)}
.route-pill.human{background:rgba(255,82,82,.1);color:var(--red);border:1px solid rgba(255,82,82,.3)}
.route-pill.idle{background:rgba(124,131,160,.1);color:var(--muted);border:1px solid var(--border)}
.route-reason{font-size:12px;color:var(--muted);line-height:1.5;margin-top:6px}

.steps-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:16px;flex:1;overflow-y:auto;max-height:360px}
.step{display:flex;gap:10px;margin-bottom:14px;opacity:0;transform:translateY(8px);animation:fadeUp .3s forwards}
@keyframes fadeUp{to{opacity:1;transform:translateY(0)}}
.step-icon{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;margin-top:2px}
.step-icon.supervisor{background:rgba(108,99,255,.2);color:var(--accent);border:1px solid var(--accent)}
.step-icon.retrieval{background:rgba(0,230,118,.15);color:var(--green);border:1px solid var(--green)}
.step-icon.policy{background:rgba(255,215,64,.15);color:var(--yellow);border:1px solid var(--yellow)}
.step-icon.synthesis{background:rgba(0,212,255,.15);color:var(--accent2);border:1px solid var(--accent2)}
.step-icon.hitl{background:rgba(255,82,82,.15);color:var(--red);border:1px solid var(--red)}
.step-body{flex:1}
.step-label{font-size:12px;font-weight:600;color:var(--text);margin-bottom:2px}
.step-detail{font-size:11px;color:var(--muted);line-height:1.5}
.step-running .step-icon{animation:pulse 1s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(108,99,255,.4)}50%{box-shadow:0 0 0 6px rgba(108,99,255,0)}}

.mcp-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.mcp-call{background:rgba(255,152,0,.06);border:1px solid rgba(255,152,0,.2);border-radius:8px;padding:10px 12px;margin-bottom:8px;font-size:12px}
.mcp-tool{font-weight:700;color:var(--orange);margin-bottom:4px}
.mcp-io{color:var(--muted);font-size:11px;font-family:'Consolas',monospace}

.history-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:14px;max-height:200px;overflow-y:auto}
.history-item{display:flex;align-items:flex-start;gap:8px;padding:7px 8px;border-bottom:1px solid var(--border);cursor:pointer;border-radius:6px;transition:background .15s}
.history-item:last-child{border-bottom:none}
.history-item:hover{background:rgba(108,99,255,.1)}
.hi-q{font-size:12px;color:var(--text);flex:1;line-height:1.4}
.hi-route{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;flex-shrink:0}
.hi-route.retrieval{background:rgba(0,230,118,.15);color:var(--green)}
.hi-route.policy{background:rgba(255,215,64,.15);color:var(--yellow)}
.hi-route.human{background:rgba(255,82,82,.15);color:var(--red)}

/* ── HITL MODAL ── */
.hitl-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);z-index:1000;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .25s}
.hitl-overlay.active{opacity:1;pointer-events:all}
.hitl-modal{background:#1a1d27;border:1px solid #ff5252;border-radius:16px;padding:28px;max-width:520px;width:90%;box-shadow:0 0 40px rgba(255,82,82,.3);transform:scale(.95) translateY(20px);transition:transform .25s}
.hitl-overlay.active .hitl-modal{transform:scale(1) translateY(0)}
.hitl-header{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.hitl-icon{width:44px;height:44px;border-radius:50%;background:rgba(255,82,82,.15);border:1px solid var(--red);display:flex;align-items:center;justify-content:center;font-size:22px}
.hitl-title{font-size:17px;font-weight:700;color:var(--red)}
.hitl-subtitle{font-size:12px;color:var(--muted);margin-top:2px}
.hitl-section{margin-bottom:16px}
.hitl-label{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.hitl-task{background:#12141f;border:1px solid var(--border);border-radius:8px;padding:12px;font-size:13px;color:var(--text);line-height:1.5}
.hitl-reason{background:rgba(255,82,82,.06);border:1px solid rgba(255,82,82,.2);border-radius:8px;padding:10px 12px;font-size:12px;color:var(--red)}
.hitl-context{width:100%;background:#12141f;border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;padding:10px 12px;resize:none;font-family:inherit;transition:border-color .2s}
.hitl-context:focus{outline:none;border-color:var(--accent)}
.hitl-context::placeholder{color:var(--muted)}
.hitl-actions{display:flex;gap:10px;margin-top:20px}
.btn-approve{flex:1;background:linear-gradient(135deg,var(--green),#00c853);border:none;border-radius:8px;color:#0a1f0a;font-size:14px;font-weight:700;padding:12px;cursor:pointer;transition:opacity .2s}
.btn-approve:hover{opacity:.9}
.btn-reject{flex:1;background:rgba(255,82,82,.1);border:1px solid var(--red);border-radius:8px;color:var(--red);font-size:14px;font-weight:700;padding:12px;cursor:pointer;transition:background .2s}
.btn-reject:hover{background:rgba(255,82,82,.2)}
.hitl-timer{font-size:11px;color:var(--muted);text-align:center;margin-top:10px}
.hitl-pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);animation:blink 1s ease-in-out infinite;margin-right:6px}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}

.spinner{width:16px;height:16px;border:2px solid rgba(108,99,255,.3);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;display:inline-block;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
.empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--muted);font-size:13px;padding:40px 20px;text-align:center}
.empty-state .icon{font-size:36px;opacity:.4}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

@media(max-width:900px){.container{grid-template-columns:1fr}.trace-panel{grid-column:1;grid-row:3}}
</style>
</head>
<body>

<header>
  <div class="logo">🤖</div>
  <div>
    <h1>IT Helpdesk Assistant</h1>
    <p>Multi-Agent Orchestration · Day 09 · with Human-in-the-Loop</p>
  </div>
  <span class="hbadge">Supervisor–Worker + HITL</span>
</header>

<div class="container">

  <!-- Query -->
  <div class="query-panel panel">
    <div class="panel-title">Câu hỏi</div>
    <div class="input-area">
      <textarea id="queryInput"
        placeholder="Nhập câu hỏi về IT Helpdesk, SLA, policy, cấp quyền...&#10;&#10;Gợi ý HITL: hỏi về mã lỗi ERR-xxx để trigger human review"
        rows="3"></textarea>
      <button class="btn-ask" id="askBtn" onclick="askQuestion()">Hỏi →</button>
    </div>
    <div class="samples">
      <button class="sbtn" onclick="setQ(this)">Ticket P1 lúc 2am — escalation xảy ra thế nào?</button>
      <button class="sbtn" onclick="setQ(this)">Khách hàng Flash Sale yêu cầu hoàn tiền — được không?</button>
      <button class="sbtn" onclick="setQ(this)">Contractor cần Admin Access Level 3 để sửa P1 khẩn cấp</button>
      <button class="sbtn" onclick="setQ(this)">Tài khoản bị khóa sau bao nhiêu lần đăng nhập sai?</button>
      <button class="sbtn" onclick="setQ(this)">ERR-403-AUTH là lỗi gì? (→ HITL demo)</button>
      <button class="sbtn" onclick="setQ(this)">ERR-500-DB crash nghiêm trọng — cần xử lý ngay</button>
    </div>
  </div>

  <!-- Answer -->
  <div class="answer-panel panel">
    <div class="answer-header panel-title">
      Câu trả lời
      <span id="confBadge" class="conf-badge" style="display:none"></span>
    </div>
    <div class="answer-text loading" id="answerText">Nhập câu hỏi và nhấn <strong>Hỏi →</strong> để bắt đầu.</div>
    <div class="sources-row" id="sourcesRow"></div>
  </div>

  <!-- Right trace panel -->
  <div class="trace-panel">

    <div class="metrics-card">
      <div class="metric"><div class="metric-value" id="mConf">—</div><div class="metric-label">Confidence</div></div>
      <div class="metric"><div class="metric-value" id="mLat">—</div><div class="metric-label">Latency</div></div>
      <div class="metric"><div class="metric-value" id="mMCP">—</div><div class="metric-label">MCP calls</div></div>
    </div>

    <div class="route-card">
      <div class="panel-title">Routing Decision</div>
      <div id="routePill" class="route-pill idle">⏳ Chưa có query</div>
      <div id="routeReason" class="route-reason"></div>
    </div>

    <div class="steps-card">
      <div class="panel-title">Pipeline Steps</div>
      <div id="stepsContainer">
        <div class="empty-state"><span class="icon">🔄</span>Pipeline sẽ hiển thị ở đây</div>
      </div>
    </div>

    <div class="mcp-card" id="mcpCard" style="display:none">
      <div class="panel-title">MCP Tool Calls</div>
      <div id="mcpContainer"></div>
    </div>

    <div class="history-card">
      <div class="panel-title" style="margin-bottom:10px">Lịch sử</div>
      <div id="historyContainer"><div class="empty-state" style="padding:12px"><span class="icon">📋</span>Chưa có query</div></div>
    </div>

  </div>
</div>

<!-- HITL Modal -->
<div class="hitl-overlay" id="hitlOverlay">
  <div class="hitl-modal">
    <div class="hitl-header">
      <div class="hitl-icon">🚨</div>
      <div>
        <div class="hitl-title"><span class="hitl-pulse"></span>Human Review Required</div>
        <div class="hitl-subtitle">Pipeline đã tạm dừng — chờ quyết định của bạn</div>
      </div>
    </div>

    <div class="hitl-section">
      <div class="hitl-label">Câu hỏi đang xử lý</div>
      <div class="hitl-task" id="hitlTask"></div>
    </div>

    <div class="hitl-section">
      <div class="hitl-label">Lý do cần review</div>
      <div class="hitl-reason" id="hitlReason"></div>
    </div>

    <div class="hitl-section">
      <div class="hitl-label">Context / Hướng dẫn thêm (tuỳ chọn)</div>
      <textarea class="hitl-context" id="hitlContext" rows="3"
        placeholder="Thêm context cho pipeline... VD: 'Đây là lỗi authentication, xem playbook PAY-003'"></textarea>
    </div>

    <div class="hitl-actions">
      <button class="btn-approve" onclick="hitlDecide('approve')">✅ Approve — Tiếp tục</button>
      <button class="btn-reject"  onclick="hitlDecide('reject')">❌ Reject — Từ chối</button>
    </div>
    <div class="hitl-timer" id="hitlTimer"></div>
  </div>
</div>

<script>
const ROUTE_ICONS  = {retrieval_worker:'🔍', policy_tool_worker:'📋', human_review:'🚨'};
const ROUTE_LABELS = {retrieval_worker:'Retrieval Worker', policy_tool_worker:'Policy Tool Worker', human_review:'Human Review (HITL)'};
const WORKER_ICONS = {supervisor:'🧠', retrieval_worker:'🔍', policy_tool_worker:'📋', synthesis_worker:'✍️', human_review:'🚨'};

let history = [];
let currentRunId = null;
let hitlTimer = null;
let hitlSeconds = 0;
let currentEventSource = null;

/* ── helpers ── */
function setQ(btn){ document.getElementById('queryInput').value = btn.textContent.replace('(→ HITL demo)','').trim() }

function rc(route){
  if(!route||route==='idle') return 'idle';
  if(route.includes('retrieval')) return 'retrieval';
  if(route.includes('policy')) return 'policy';
  return 'human';
}
function confColor(c){ return c>=.7?'#00e676':c>=.5?'#ffd740':'#ff5252' }

function addStep(type, label, detail, animate=true){
  const c = document.getElementById('stepsContainer');
  if(c.querySelector('.empty-state')) c.innerHTML = '';
  const d = document.createElement('div');
  d.className = 'step' + (animate?' step-running':'');
  d.dataset.type = type;
  const ic = type==='policy'?'policy':type==='human'?'hitl':type==='synthesis'?'synthesis':type==='retrieval'?'retrieval':'supervisor';
  d.innerHTML = `<div class="step-icon ${ic}">${WORKER_ICONS[type+'_worker']||WORKER_ICONS[type]||'⚙️'}</div>
    <div class="step-body"><div class="step-label">${label}</div><div class="step-detail">${detail}</div></div>`;
  c.appendChild(d);
  c.scrollTop = c.scrollHeight;
  return d;
}

function finishStep(stepEl, detail){
  stepEl.classList.remove('step-running');
  if(detail) stepEl.querySelector('.step-detail').textContent = detail;
}

/* ── SSE pipeline ── */
let _stepEls = {};

async function askQuestion(){
  const query = document.getElementById('queryInput').value.trim();
  if(!query) return;

  // close previous SSE
  if(currentEventSource){ currentEventSource.close(); currentEventSource=null; }

  const btn = document.getElementById('askBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  // reset UI
  document.getElementById('answerText').className = 'answer-text loading';
  document.getElementById('answerText').textContent = '⏳ Đang xử lý...';
  document.getElementById('confBadge').style.display = 'none';
  document.getElementById('sourcesRow').innerHTML = '';
  document.getElementById('stepsContainer').innerHTML = '<div class="empty-state"><span class="spinner"></span> Pipeline đang chạy...</div>';
  document.getElementById('mcpCard').style.display = 'none';
  document.getElementById('routePill').className = 'route-pill idle';
  document.getElementById('routePill').textContent = '⏳ Processing...';
  document.getElementById('routeReason').textContent = '';
  document.getElementById('mConf').textContent='—';
  document.getElementById('mLat').textContent='—';
  document.getElementById('mMCP').textContent='—';
  _stepEls = {};

  const url = '/ask/stream?q=' + encodeURIComponent(query);
  const es = new EventSource(url);
  currentEventSource = es;

  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    handleEvent(ev);
  };
  es.onerror = () => {
    es.close();
    btn.disabled = false;
    btn.textContent = 'Hỏi →';
  };
}

function handleEvent(ev){
  const btn = document.getElementById('askBtn');

  if(ev.type === 'supervisor'){
    const route = ev.route;
    const pill = document.getElementById('routePill');
    pill.className = `route-pill ${rc(route)}`;
    pill.textContent = `${ROUTE_ICONS[route]||'🔀'} ${ROUTE_LABELS[route]||route}`;
    document.getElementById('routeReason').textContent = ev.reason || '';
    _stepEls['supervisor'] = addStep('supervisor','Supervisor', `Route → ${ROUTE_LABELS[route]||route}${ev.risk_high?' · ⚠️ Risk HIGH':''}`);
    finishStep(_stepEls['supervisor']);
  }

  else if(ev.type === 'worker_start'){
    const w = ev.worker;
    const label = ROUTE_LABELS[w]||w;
    _stepEls[w] = addStep(w.replace('_worker',''), label, 'đang xử lý...', true);
  }

  else if(ev.type === 'worker_done'){
    const w = ev.worker;
    const el = _stepEls[w];
    if(!el) return;
    let detail = '';
    if(w==='retrieval_worker'){
      detail = `${ev.chunks||0} chunks · ${(ev.sources||[]).join(', ')||'—'}`;
    } else if(w==='policy_tool_worker'){
      const applies = ev.policy_applies;
      detail = applies===false ? `❌ Policy blocked · ${ev.exceptions||0} exception(s)` : `✅ Policy OK`;
    } else if(w==='synthesis_worker'){
      detail = `Confidence ${((ev.confidence||0)*100).toFixed(0)}% · ${(ev.sources||[]).length} source(s)`;
    } else if(w==='human_review'){
      detail = ev.decision==='reject' ? '❌ Rejected by human' : `✅ Approved${ev.context?' · context provided':''}`;
    }
    finishStep(el, detail||'done');

    // MCP
    if(ev.mcp_calls && ev.mcp_calls.length){
      const card = document.getElementById('mcpCard');
      const container = document.getElementById('mcpContainer');
      card.style.display = 'block';
      ev.mcp_calls.forEach(c => {
        const d = document.createElement('div');
        d.className = 'mcp-call';
        const inp = JSON.stringify(c.input||{}).slice(0,80);
        const out = c.output ? (c.output.total_found!==undefined ? c.output.total_found+' results' : JSON.stringify(c.output).slice(0,60)) : (c.error?'❌ error':'—');
        d.innerHTML = `<div class="mcp-tool">🔧 ${c.tool||'?'}</div><div class="mcp-io">in: ${inp}</div><div class="mcp-io">out: ${out}</div>`;
        container.appendChild(d);
      });
    }
  }

  else if(ev.type === 'hitl_required'){
    currentRunId = ev.run_id;
    showHitlModal(ev.task, ev.reason);
  }

  else if(ev.type === 'done'){
    const result = ev.result;
    if(currentEventSource){ currentEventSource.close(); currentEventSource=null; }
    btn.disabled = false;
    btn.textContent = 'Hỏi →';
    renderFinalResult(result);
  }

  else if(ev.type === 'error'){
    if(currentEventSource){ currentEventSource.close(); currentEventSource=null; }
    btn.disabled = false;
    btn.textContent = 'Hỏi →';
    document.getElementById('answerText').className = 'answer-text';
    document.getElementById('answerText').textContent = '❌ Lỗi: ' + (ev.message||'unknown');
  }
}

function renderFinalResult(result){
  if(!result) return;

  // Answer
  const ansEl = document.getElementById('answerText');
  ansEl.className = 'answer-text';
  ansEl.textContent = result.final_answer || '(Không có câu trả lời)';

  // Confidence badge
  const c = result.confidence||0;
  const badge = document.getElementById('confBadge');
  badge.style.display = 'inline-block';
  badge.textContent = `Confidence: ${(c*100).toFixed(0)}%`;
  badge.style.background = confColor(c)+'22';
  badge.style.color = confColor(c);
  badge.style.border = `1px solid ${confColor(c)}55`;

  // Sources
  const srcRow = document.getElementById('sourcesRow');
  srcRow.innerHTML = '';
  (result.sources||result.retrieved_sources||[]).forEach(s=>{
    const t = document.createElement('span');
    t.className = 'src-tag';
    t.textContent = '📄 '+s;
    srcRow.appendChild(t);
  });

  // Metrics
  document.getElementById('mConf').textContent = (c*100).toFixed(0)+'%';
  document.getElementById('mConf').style.color = confColor(c);
  document.getElementById('mLat').textContent = (result.latency_ms||0)+'ms';
  document.getElementById('mMCP').textContent = (result.mcp_tools_used||[]).length;

  // History
  history.unshift(result);
  if(history.length>20) history.pop();
  renderHistory();
}

/* ── HITL modal ── */
function showHitlModal(task, reason){
  document.getElementById('hitlTask').textContent = task;
  document.getElementById('hitlReason').textContent = reason;
  document.getElementById('hitlContext').value = '';
  document.getElementById('hitlOverlay').classList.add('active');

  // Timer countdown
  hitlSeconds = 0;
  clearInterval(hitlTimer);
  hitlTimer = setInterval(() => {
    hitlSeconds++;
    document.getElementById('hitlTimer').textContent = `⏱ Đã chờ ${hitlSeconds}s — pipeline tạm dừng`;
  }, 1000);

  // Mark HITL step
  const el = _stepEls['human_review'];
  if(el) el.querySelector('.step-detail').textContent = '⏳ Chờ human quyết định...';
}

function hideHitlModal(){
  document.getElementById('hitlOverlay').classList.remove('active');
  clearInterval(hitlTimer);
  document.getElementById('hitlTimer').textContent = '';
}

async function hitlDecide(action){
  const context = document.getElementById('hitlContext').value.trim();
  hideHitlModal();

  if(!currentRunId) return;

  // Mark HITL step
  const el = _stepEls['human_review'];
  if(el){
    finishStep(el, action==='reject'
      ? '❌ Rejected by human'
      : `✅ Approved${context?' · context provided':''}`);
  }

  try {
    await fetch(`/hitl/decide/${currentRunId}`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action, context}),
    });
  } catch(e){ console.error('HITL decide failed:', e); }
}

/* ── History ── */
function renderHistory(){
  const c = document.getElementById('historyContainer');
  c.innerHTML = '';
  if(!history.length){ c.innerHTML='<div class="empty-state" style="padding:12px"><span class="icon">📋</span>Chưa có query</div>'; return; }
  history.forEach(r=>{
    const d = document.createElement('div');
    d.className = 'history-item';
    d.onclick = ()=>replayResult(r);
    const rcls = rc(r.supervisor_route);
    d.innerHTML = `<span class="hi-q">${(r.task||'').slice(0,60)}${r.task.length>60?'…':''}</span>
      <span class="hi-route ${rcls}">${rcls==='retrieval'?'R':rcls==='policy'?'P':'H'}</span>`;
    c.appendChild(d);
  });
}

function replayResult(r){
  document.getElementById('queryInput').value = r.task||'';
  renderFinalResult(r);
  // Restore routing
  const route = r.supervisor_route;
  const pill = document.getElementById('routePill');
  pill.className = `route-pill ${rc(route)}`;
  pill.textContent = `${ROUTE_ICONS[route]||'🔀'} ${ROUTE_LABELS[route]||route}`;
  document.getElementById('routeReason').textContent = r.route_reason||'';
  // Restore steps from workers_called
  document.getElementById('stepsContainer').innerHTML='';
  _stepEls={};
  addStep('supervisor','Supervisor',`Route → ${ROUTE_LABELS[route]||route}${r.risk_high?' · ⚠️ Risk HIGH':''}${r.hitl_triggered?' · 🚨 HITL':''}`,false);
  (r.workers_called||[]).forEach(w=>{
    let detail='';
    if(w==='retrieval_worker') detail=`${(r.retrieved_chunks||[]).length} chunks · ${(r.retrieved_sources||[]).join(', ')||'—'}`;
    else if(w==='policy_tool_worker') detail=`policy_applies=${(r.policy_result||{}).policy_applies}`;
    else if(w==='synthesis_worker') detail=`confidence=${((r.confidence||0)*100).toFixed(0)}%`;
    else if(w==='human_review') detail=r.hitl_decision==='reject'?'❌ Rejected':'✅ Approved';
    addStep(w.replace('_worker',''),ROUTE_LABELS[w]||w,detail,false);
  });
  // MCP
  const calls = r.mcp_tools_used||[];
  const card = document.getElementById('mcpCard');
  const mcpC = document.getElementById('mcpContainer');
  if(calls.length){
    card.style.display='block'; mcpC.innerHTML='';
    calls.forEach(c=>{
      const d=document.createElement('div'); d.className='mcp-call';
      const inp=JSON.stringify(c.input||{}).slice(0,80);
      const out=c.output?(c.output.total_found!==undefined?c.output.total_found+' results':JSON.stringify(c.output).slice(0,60)):'—';
      d.innerHTML=`<div class="mcp-tool">🔧 ${c.tool||'?'}</div><div class="mcp-io">in: ${inp}</div><div class="mcp-io">out: ${out}</div>`;
      mcpC.appendChild(d);
    });
  } else card.style.display='none';
}

/* Enter to submit */
document.getElementById('queryInput').addEventListener('keydown', e=>{
  if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); askQuestion(); }
});
</script>
</body>
</html>
"""


# ── API ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.get("/ask/stream")
async def ask_stream(q: str):
    """SSE endpoint: stream pipeline events + support real HITL pause."""
    if not q.strip():
        async def empty():
            yield 'data: {"type":"error","message":"query is empty"}\n\n'
        return StreamingResponse(empty(), media_type="text/event-stream")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def put(obj: dict):
        asyncio.run_coroutine_threadsafe(queue.put(obj), loop)

    # ── Callbacks ──────────────────────────────────────────────
    def on_supervisor(state):
        put({"type": "supervisor",
             "route": state["supervisor_route"],
             "reason": state["route_reason"],
             "risk_high": state.get("risk_high", False)})

    def on_worker_start(name, state):
        put({"type": "worker_start", "worker": name})

    def on_worker_done(name, state):
        ev = {"type": "worker_done", "worker": name}
        if name == "retrieval_worker":
            ev["chunks"]  = len(state.get("retrieved_chunks", []))
            ev["sources"] = state.get("retrieved_sources", [])
        elif name == "policy_tool_worker":
            pr = state.get("policy_result", {})
            ev["policy_applies"] = pr.get("policy_applies")
            ev["exceptions"]     = len(pr.get("exceptions_found", []))
            ev["mcp_calls"]      = state.get("mcp_tools_used", [])
        elif name == "synthesis_worker":
            ev["confidence"] = state.get("confidence", 0)
            ev["sources"]    = state.get("sources", [])
        elif name == "human_review":
            ev["decision"] = state.get("hitl_decision", "")
            ev["context"]  = state.get("hitl_context", "")
        put(ev)

    def on_hitl(state) -> dict:
        """Block the pipeline thread until human decides (or 5-min timeout)."""
        run_id = state["run_id"]
        put({"type": "hitl_required",
             "run_id": run_id,
             "task": state["task"],
             "reason": state["route_reason"]})

        evt = threading.Event()
        _pending_hitl[run_id] = {"event": evt, "decision": None}
        evt.wait(timeout=300)          # 5 min → auto-approve

        entry = _pending_hitl.pop(run_id, {})
        return entry.get("decision") or {"action": "approve", "context": ""}

    def on_done(state):
        # Make JSON-safe copy
        safe = {}
        for k, v in state.items():
            try:
                json.dumps(v)
                safe[k] = v
            except Exception:
                safe[k] = str(v)
        put({"type": "done", "result": safe})

    # ── Run pipeline in thread ──────────────────────────────────
    def run_pipeline():
        try:
            state = make_initial_state(q)
            graph = build_graph(callbacks={
                "on_supervisor":   on_supervisor,
                "on_worker_start": on_worker_start,
                "on_worker_done":  on_worker_done,
                "on_hitl":         on_hitl,
                "on_done":         on_done,
            })
            result = graph(state)
            try:
                save_trace(result, "./artifacts/traces")
            except Exception:
                pass
        except Exception as exc:
            put({"type": "error", "message": str(exc)})

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    # ── SSE generator ───────────────────────────────────────────
    async def generate():
        while True:
            ev = await queue.get()
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if ev["type"] in ("done", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/hitl/decide/{run_id}")
async def hitl_decide(run_id: str, request: Request):
    """Human submits approve/reject decision."""
    if run_id not in _pending_hitl:
        return JSONResponse({"error": "No pending HITL for this run_id"}, status_code=404)
    body = await request.json()
    _pending_hitl[run_id]["decision"] = body
    _pending_hitl[run_id]["event"].set()
    return JSONResponse({"ok": True, "run_id": run_id, "action": body.get("action")})


@app.get("/tools")
async def tools_list():
    return JSONResponse(list_tools())


@app.get("/traces")
async def traces_list():
    traces_dir = "./artifacts/traces"
    if not os.path.exists(traces_dir):
        return JSONResponse([])
    files = sorted(
        [f for f in os.listdir(traces_dir) if f.endswith(".json")], reverse=True
    )[:20]
    results = []
    for f in files:
        try:
            with open(os.path.join(traces_dir, f)) as fh:
                results.append(json.load(fh))
        except Exception:
            pass
    return JSONResponse(results)


# ── Entry ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("=" * 55)
    print("  Day 09 — Multi-Agent Helpdesk Demo  (HITL enabled)")
    print("  http://localhost:7860")
    print("=" * 55)
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)
