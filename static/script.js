async function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.innerText.toLowerCase().includes(tabName)) btn.classList.add('active');
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(`${tabName}-view`).classList.add('active');

    if (tabName === 'dashboard') {
        updateStats();
    } else if (tabName === 'eval') {
        loadEvaluation();
    }
}

async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        document.getElementById('chunk-count').innerText = data.chunk_count;
        document.getElementById('db-status').innerText = `Database: ${data.db_path}`;
    } catch (e) {
        console.error("Stats error:", e);
    }
}

async function runIndexing() {
    if (!confirm("Are you sure you want to rebuild the index? This runs Sprint 1 pipeline in background.")) return;
    try {
        const response = await fetch('/api/index', { method: 'POST' });
        const data = await response.json();
        alert(data.message);
    } catch (e) {
        alert("Error starting indexing: " + e.message);
    }
}

async function loadEvaluation() {
    try {
        const response = await fetch('/api/eval');
        const data = await response.json();
        document.getElementById('eval-content').innerHTML = `<pre>${data.content}</pre>`;
    } catch (e) {
        document.getElementById('eval-content').innerText = "Error loading evaluation results.";
    }
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const text = input.value.trim();
    if (!text) return;

    // Clear input
    input.value = '';

    // Add user message to UI
    appendMessage('user', text);

    // Add loading message
    const loadingId = appendMessage('ai', 'Đang suy nghĩ...');

    try {
        const retrievalMode = document.getElementById('retrieval-mode').value;
        const topKSelect = parseInt(document.getElementById('top-k').value);

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: text,
                retrieval_mode: retrievalMode,
                top_k_select: topKSelect
            })
        });

        const data = await response.json();
        
        // Remove loading message
        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) loadingMsg.remove();

        // Add AI response
        appendAiResponse(data.answer, data.sources);

    } catch (e) {
        console.error("Chat error:", e);
        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) loadingMsg.innerText = "Error: " + e.message;
    }
}

function appendMessage(role, text) {
    const chatMessages = document.getElementById('chat-messages');
    const msgDiv = document.createElement('div');
    const id = 'msg-' + Date.now();
    msgDiv.id = id;
    msgDiv.className = `message ${role}`;
    msgDiv.innerText = text;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function appendAiResponse(answer, sources) {
    const chatMessages = document.getElementById('chat-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message ai';
    
    let html = `<div class="text">${answer}</div>`;
    if (sources && sources.length > 0) {
        html += `<div class="sources">Sources: ${sources.join(', ')}</div>`;
    }
    
    msgDiv.innerHTML = html;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Enter key support
document.getElementById('user-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') sendMessage();
});

// Init
updateStats();
loadEvaluation();
