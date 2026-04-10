// Configuration
const API_BASE = 'http://localhost:8000';
let currentSessionId = null;
let isStreaming = false;
let waitingForConfirmation = false;
let pendingToolCalls = null;
let pendingImages = []; // 待发送的图片（base64）
let enabledKnowledgeBases = []; // 当前启用的知识库 ID 列表
let allKnowledgeBases = []; // 所有知识库
let currentDetailKbId = null; // 当前详情面板的知识库 ID
let indexingPollInterval = null; // 索引状态轮询定时器
let currentEditKbId = null; // 当前编辑的知识库 ID

// Configure marked
marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return code;
    }
});

// Starry Background Animation
function createStars() {
    const container = document.getElementById('starsContainer');
    const starCount = 80;

    for (let i = 0; i < starCount; i++) {
        const star = document.createElement('div');
        star.className = 'star';

        const size = Math.random() * 2 + 1;
        const x = Math.random() * 100;
        const y = Math.random() * 100;
        const delay = Math.random() * 3;
        const duration = 2 + Math.random() * 2;
        const opacity = 0.3 + Math.random() * 0.5;

        star.style.width = `${size}px`;
        star.style.height = `${size}px`;
        star.style.left = `${x}%`;
        star.style.top = `${y}%`;
        star.style.setProperty('--twinkle-duration', `${duration}s`);
        star.style.animationDelay = `${delay}s`;
        star.style.setProperty('--star-opacity', opacity);

        container.appendChild(star);
    }

    // Create floating particles
    const particleCount = 15;
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';

        const size = 3 + Math.random() * 4;
        const x = Math.random() * 100;
        const delay = Math.random() * 10;
        const duration = 15 + Math.random() * 10;

        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.left = `${x}%`;
        particle.style.animationDelay = `${delay}s`;
        particle.style.animationDuration = `${duration}s`;

        container.appendChild(particle);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    createStars();
    loadSessions();
    loadKnowledgeBases();
    updateStatus('disconnected');
    initImageUpload();
});

// Status updates
function updateStatus(state, text) {
    const indicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');

    indicator.className = 'status-indicator';
    if (state === 'connected') {
        indicator.classList.add('connected');
        statusText.textContent = text || '已连接';
    } else if (state === 'thinking') {
        indicator.classList.add('thinking');
        statusText.textContent = text || '思考中...';
    } else {
        statusText.textContent = text || '已断开';
    }
}

// Session management
async function loadSessions() {
    try {
        const res = await fetch(`${API_BASE}/api/sessions`);
        const data = await res.json();
        renderSessionList(data.sessions);
    } catch (e) {
        console.error('Failed to load sessions:', e);
    }
}

function renderSessionList(sessions) {
    const container = document.getElementById('sessionList');
    container.innerHTML = sessions.map(s => `
        <div class="session-item ${s.id === currentSessionId ? 'active' : ''}"
             onclick="selectSession('${s.id}')">
            ${s.id.slice(0, 8)}...
        </div>
    `).join('');
}

async function newSession() {
    try {
        const res = await fetch(`${API_BASE}/api/sessions`, { method: 'POST' });
        const data = await res.json();
        currentSessionId = data.session_id;
        document.getElementById('messages').innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <p>新对话已开始</p>
            </div>
        `;
        document.getElementById('sessionInfo').textContent = `会话：${currentSessionId.slice(0, 8)}...`;
        updateStatus('connected');
        loadSessions();
    } catch (e) {
        console.error('Failed to create session:', e);
    }
}

async function selectSession(sessionId) {
    currentSessionId = sessionId;
    document.getElementById('sessionInfo').textContent = `会话：${sessionId.slice(0, 8)}...`;

    // Load messages
    try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
        const data = await res.json();
        console.log('Loaded messages:', data);
        renderMessages(data.messages);
        updateStatus('connected');
        loadSessions();
    } catch (e) {
        console.error('Failed to load messages:', e);
    }
}

// Message rendering
function renderMessages(messages) {
    const container = document.getElementById('messages');
    container.innerHTML = messages.map(msg => {
        if (msg.role === 'user') {
            // Handle multi-modal content (array with text and images)
            let contentHtml = '';
            if (Array.isArray(msg.content)) {
                msg.content.forEach(item => {
                    if (item.type === 'text') {
                        contentHtml += `<p>${escapeHtml(item.text)}</p>`;
                    } else if (item.type === 'image_url' && item.image_url?.url) {
                        contentHtml += `<img src="${item.image_url.url}" class="message-image" />`;
                    }
                });
            } else {
                contentHtml = `<p>${escapeHtml(msg.content)}</p>`;
            }
            return `<div class="message user">${contentHtml}</div>`;
        } else if (msg.role === 'assistant') {
            return `<div class="message assistant">${marked.parse(msg.content)}</div>`;
        } else if (msg.role === 'tool') {
            return `
                <div class="message tool">
                    <span class="tool-badge">🔧 ${msg.name || 'tool'}</span>
                    <pre><code>${escapeHtml(msg.content)}</code></pre>
                </div>
            `;
        }
        return '';
    }).join('');
    container.scrollTop = container.scrollHeight;
}

function addMessage(content, type) {
    const container = document.getElementById('messages');
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const div = document.createElement('div');
    div.className = `message ${type}`;

    if (type === 'tool') {
        div.innerHTML = content;
    } else if (type === 'assistant') {
        div.innerHTML = marked.parse(content);
    } else {
        div.textContent = content;
    }

    container.appendChild(div);
    scrollToBottom();
    return div;
}

// Send message
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if ((!message || message === '') && pendingImages.length === 0 || isStreaming) return;
    if (!currentSessionId) {
        await newSession();
    }

    // 获取启用的知识库列表
    const knowledgeBasesToSend = [...enabledKnowledgeBases];
    console.log('Sending with knowledge bases:', knowledgeBasesToSend);

    // Add user message to UI (with images if present)
    if (pendingImages.length > 0) {
        // Render message with images
        const container = document.getElementById('messages');
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const div = document.createElement('div');
        div.className = 'message user message-with-images';

        let imagesHtml = pendingImages.map(img => `<img src="${img}" class="message-image" />`).join('');
        let messageText = message ? `<p>${escapeHtml(message)}</p>` : '';
        div.innerHTML = imagesHtml + messageText;

        container.appendChild(div);
        scrollToBottom();
    } else {
        addMessage(message, 'user');
    }

    // Prepare images for API (strip data:image prefix)
    const imagesForApi = pendingImages.map(img => {
        if (img.startsWith('data:image')) {
            return img.split(',')[1];
        }
        return img;
    });

    const messageToSend = message || '(Image attached)';
    input.value = '';

    // Clear images from preview area immediately after sending
    clearImages();

    // Create placeholder for AI response
    const aiMessageDiv = addMessage('', 'assistant');
    aiMessageDiv.innerHTML = '<span style="opacity: 0.5;">思考中...</span>';
    isStreaming = true;
    updateStatus('thinking', '思考中...');

    let streamDone = false;

    try {
        const messagesContainer = document.getElementById('messages');
        const res = await fetch(`${API_BASE}/api/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: messageToSend,
                session_id: currentSessionId,
                images: imagesForApi.length > 0 ? imagesForApi : undefined,
                enabled_knowledge_bases: knowledgeBasesToSend
            })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastContent = '';

        // 【新增变量】记录当前工具DIV和工具名
        let currentToolMessageDiv = null;
        let currentToolName = null;

        while (true) {
            const { done, value } = await reader.read();

            if (value) {
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === 'ai') {
                            if (data.content !== lastContent) {
                                aiMessageDiv.innerHTML = marked.parse(data.content);
                                lastContent = data.content;
                                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                                aiMessageDiv.querySelectorAll('pre code').forEach((block) => {
                                    hljs.highlightElement(block);
                                });
                            }
                            if (data.done || streamDone) {
                                isStreaming = false;
                                updateStatus('connected', '已连接');
                            }
                        } else if (data.type === 'tool') {
                            if (data.tool_name !== currentToolName) {
                                currentToolMessageDiv = addMessage('', 'tool');
                                currentToolName = data.tool_name;
                            }
                            currentToolMessageDiv.innerHTML = `
                                <span class="tool-badge">🔧 ${data.tool_name}</span>
                                <pre><code>${escapeHtml(data.content)}</code></pre>
                            `;
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;
                        } else if (data.type === 'tool_pending') {
                            waitingForConfirmation = true;
                            isStreaming = false;
                            pendingToolCalls = data.tool_calls;
                            updateStatus('thinking', '等待确认...');

                            // 可选：如果AI还没输出描述文字，填充默认提示
                            if (aiMessageDiv.innerHTML.includes('思考中...')) {
                                aiMessageDiv.innerHTML = marked.parse('我需要执行以下操作来完成你的请求：');
                            }
                            showToolConfirmation(data.tool_calls, messagesContainer);
                            return;
                        }
                    }

                    if (line.startsWith('event: done')) {
                        streamDone = true;
                        isStreaming = false;
                        updateStatus('connected', '已连接');
                        aiMessageDiv.innerHTML = marked.parse(lastContent);
                    }
                }
            }

            if (done && streamDone) break;

            if (done && !streamDone) {
                streamDone = true;
                isStreaming = false;
                updateStatus('connected', '已连接');
                aiMessageDiv.innerHTML = marked.parse(lastContent);
                break;
            }
        }

        isStreaming = false;
        updateStatus('connected', '已连接');

    } catch (e) {
        console.error('Stream error:', e);
        aiMessageDiv.innerHTML = `<span style="color: var(--error);">Error: ${escapeHtml(e.message)}</span>`;
        isStreaming = false;
        updateStatus('disconnected', '连接断开');
    }
}

// Show tool confirmation UI
function showToolConfirmation(toolCalls, container) {
    const existingConfirmation = document.getElementById('toolConfirmation');
    if (existingConfirmation) {
        existingConfirmation.remove();
    }

    const aiPlaceholders = container.querySelectorAll('.message.assistant:empty');
    aiPlaceholders.forEach(el => el.remove());

    const confirmationDiv = document.createElement('div');
    confirmationDiv.className = 'tool-confirmation';
    confirmationDiv.id = 'toolConfirmation';

    let toolsHtml = '';
    toolCalls.forEach((tc, index) => {
        const toolName = tc.name;
        const args = tc.args || {};
        let detailHtml = '';

        if (toolName === 'run_command') {
            detailHtml = `<code>${escapeHtml(args.command || 'N/A')}</code>`;
        } else if (toolName === 'read_file' || toolName === 'write_file') {
            detailHtml = `<code>${escapeHtml(args.path || 'N/A')}</code>`;
        } else if (toolName === 'execute_skill_script') {
            detailHtml = `Skill: <code>${escapeHtml(args.skill_name || 'N/A')}</code>, Script: <code>${escapeHtml(args.script_name || 'N/A')}</code>`;
        } else {
            detailHtml = `<code>${escapeHtml(JSON.stringify(args))}</code>`;
        }

        toolsHtml += `
            <div class="tool-item">
                <div class="tool-item-name">${index + 1}. ${toolName}</div>
                <div class="tool-item-detail">${detailHtml}</div>
            </div>
        `;
    });

    confirmationDiv.innerHTML = `
        <div class="waiting-badge">
            <span class="spinner"></span>
            <span>等待用户确认</span>
        </div>
        <div class="tool-confirmation-header">
            <span>🔧</span>
            <h3>AI 想要执行以下操作：</h3>
        </div>
        <div class="tool-confirmation-body">
            ${toolsHtml}
        </div>
        <div class="tool-confirmation-actions">
            <button class="btn btn-reject" onclick="rejectToolCalls()">拒绝</button>
            <button class="btn btn-confirm" onclick="confirmToolCalls()">确认执行</button>
        </div>
    `;

    container.appendChild(confirmationDiv);
    container.scrollTop = container.scrollHeight;
}

// Confirm tool calls
async function confirmToolCalls() {
    if (!currentSessionId || !pendingToolCalls) return;

    const confirmationDiv = document.getElementById('toolConfirmation');

    try {
        const confirmRes = await fetch(`${API_BASE}/api/tool_confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                action: 'confirm'
            })
        });

        const confirmData = await confirmRes.json();
        if (!confirmData.success) {
            throw new Error('Failed to confirm tool calls');
        }

        if (confirmationDiv) confirmationDiv.remove();
        await resumeAfterConfirmation();

    } catch (e) {
        console.error('Confirm error:', e);
        if (confirmationDiv) {
            confirmationDiv.innerHTML = `<span style="color: var(--error);">Error: ${escapeHtml(e.message)}</span>`;
        }
    }
}

// Reject tool calls
async function rejectToolCalls() {
    if (!currentSessionId || !pendingToolCalls) return;

    const confirmationDiv = document.getElementById('toolConfirmation');
    if (confirmationDiv) {
        confirmationDiv.innerHTML = '<span style="opacity: 0.5;">已拒绝...</span>';
    }

    try {
        const rejectRes = await fetch(`${API_BASE}/api/tool_confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                action: 'reject'
            })
        });

        const rejectData = await rejectRes.json();
        if (!rejectData.success) {
            throw new Error('Failed to reject tool calls');
        }

        if (confirmationDiv) {
            confirmationDiv.outerHTML = `
                <div class="message tool" style="border-color: var(--error);">
                    <span class="tool-badge" style="background: var(--error);">❌ 已拒绝</span>
                    <p>工具调用已被用户拒绝</p>
                </div>
            `;
        }

        pendingToolCalls = null;
        waitingForConfirmation = false;
        updateStatus('connected', '已连接');

        const aiMessageDiv = document.createElement('div');
        aiMessageDiv.className = 'message assistant';
        aiMessageDiv.innerHTML = marked.parse('操作已被用户拒绝。请问还有什么我可以帮助您的吗？');
        document.getElementById('messages').appendChild(aiMessageDiv);
        scrollToBottom();

    } catch (e) {
        console.error('Reject error:', e);
        if (confirmationDiv) {
            confirmationDiv.innerHTML = `<span style="color: var(--error);">Error: ${escapeHtml(e.message)}</span>`;
        }
    }
}

// Resume after tool confirmation
async function resumeAfterConfirmation() {
    isStreaming = true;
    updateStatus('thinking', '执行中...');

    const messagesContainer = document.getElementById('messages');
    let finalAiMessageDiv = null;

    try {
        const res = await fetch(`${API_BASE}/api/chat/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: '',
                session_id: currentSessionId
            })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastToolContent = '';
        let streamDone = false;
        let currentToolMessageDiv = null;
        let currentToolName = null;

        while (true) {
            const { done, value } = await reader.read();

            if (value) {
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === 'tool') {
                            if (data.content !== lastToolContent) {
                                if (data.tool_name !== currentToolName) {
                                    currentToolMessageDiv = addMessage('', 'tool');
                                    currentToolName = data.tool_name;
                                }
                                currentToolMessageDiv.innerHTML = `
                                    <span class="tool-badge">🔧 ${data.tool_name}</span>
                                    <pre><code>${escapeHtml(data.content)}</code></pre>
                                `;
                                lastToolContent = data.content;
                                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                            }
                        } else if (data.type === 'ai') {
                            if (!finalAiMessageDiv) {
                                finalAiMessageDiv = addMessage('', 'assistant');
                            }
                            finalAiMessageDiv.innerHTML = marked.parse(data.content);
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;
                            finalAiMessageDiv.querySelectorAll('pre code').forEach((block) => {
                                hljs.highlightElement(block);
                            });
                        } else if (data.type === 'tool_pending') {
                            waitingForConfirmation = true;
                            pendingToolCalls = data.tool_calls;

                            if (!finalAiMessageDiv) {
                                finalAiMessageDiv = addMessage('', 'assistant');
                            }
                            finalAiMessageDiv.innerHTML = marked.parse(data.content || '准备执行更多工具...');
                            showToolConfirmation(data.tool_calls, messagesContainer);
                            isStreaming = false;
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;
                            return;
                        }
                    }

                    if (line.startsWith('event: done')) {
                        streamDone = true;
                    }
                }
            }

            if (done && streamDone) break;

            if (done && !streamDone) {
                streamDone = true;
                break;
            }
        }

        isStreaming = false;
        updateStatus('connected', '已连接');
        pendingToolCalls = null;
        waitingForConfirmation = false;

    } catch (e) {
        console.error('Resume error:', e);
        isStreaming = false;
        updateStatus('disconnected', '连接断开');
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Scroll to bottom of messages
function scrollToBottom() {
    const container = document.getElementById('messages');
    container.scrollTop = container.scrollHeight;
}

// ==================== Knowledge Base Functions ====================

// 切换知识库面板
function toggleKnowledgePanel() {
    const sidebar = document.getElementById('knowledgeSidebar');
    sidebar.classList.toggle('collapsed');
}

// 加载知识库列表
async function loadKnowledgeBases() {
    try {
        const res = await fetch(`${API_BASE}/api/knowledge`);
        const data = await res.json();
        allKnowledgeBases = data;
        renderKnowledgeList();
        renderKnowledgeSelector();
    } catch (e) {
        console.error('Failed to load knowledge bases:', e);
    }
}

// 渲染知识库列表
function renderKnowledgeList() {
    const container = document.getElementById('knowledgeList');
    if (allKnowledgeBases.length === 0) {
        container.innerHTML = '<div class="text-muted" style="padding: 1rem; text-align: center;">暂无知识库<br/>点击 "+" 创建</div>';
        return;
    }

    container.innerHTML = allKnowledgeBases.map(kb => `
        <div class="knowledge-item" onclick="showKnowledgeDetail('${kb.id}')" style="cursor: pointer;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1; min-width: 0;">
                    <span class="knowledge-item-name">📚 ${escapeHtml(kb.name)}</span>
                    <span class="knowledge-item-meta">
                        <span>${kb.documents ? kb.documents.length : 0} 文档</span>
                        <span>${kb.total_chunks || 0} 分块</span>
                    </span>
                </div>
                <div class="knowledge-item-actions" onclick="event.stopPropagation()">
                    <button class="btn-icon btn-sm" onclick="editKnowledgeBase('${kb.id}')" title="编辑">✏️</button>
                    <button class="btn-icon btn-sm delete" onclick="confirmDeleteKnowledgeBase('${kb.id}')" title="删除">🗑️</button>
                </div>
            </div>
        </div>
    `).join('');
}

// 渲染知识库选择器（聊天时用）
function renderKnowledgeSelector() {
    const container = document.getElementById('knowledgeCheckboxes');
    if (allKnowledgeBases.length === 0) {
        container.innerHTML = '<span class="text-muted">暂无知识库</span>';
        return;
    }

    container.innerHTML = allKnowledgeBases.map(kb => {
        const isChecked = enabledKnowledgeBases.includes(kb.id);
        return `
            <label class="knowledge-checkbox ${isChecked ? 'checked' : ''}">
                <input type="checkbox" value="${kb.id}" ${isChecked ? 'checked' : ''} onchange="toggleKnowledgeBase('${kb.id}', this.checked)">
                ${escapeHtml(kb.name)}
            </label>
        `;
    }).join('');
}

// 切换知识库启用状态
function toggleKnowledgeBase(kbId, checked) {
    if (checked) {
        if (!enabledKnowledgeBases.includes(kbId)) {
            enabledKnowledgeBases.push(kbId);
        }
    } else {
        enabledKnowledgeBases = enabledKnowledgeBases.filter(id => id !== kbId);
    }
    renderKnowledgeSelector();
}

// 显示创建知识库 Modal
function showCreateKnowledgeModal() {
    document.getElementById('createKnowledgeModal').style.display = 'flex';
}

// 关闭创建知识库 Modal
function closeCreateKnowledgeModal() {
    document.getElementById('createKnowledgeModal').style.display = 'none';
    document.getElementById('newKnowledgeName').value = '';
    document.getElementById('newKnowledgeDesc').value = '';
}

// 创建知识库
async function createKnowledgeBase() {
    const name = document.getElementById('newKnowledgeName').value.trim();
    const description = document.getElementById('newKnowledgeDesc').value.trim();

    if (!name) {
        alert('请输入知识库名称');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/knowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });

        if (!res.ok) throw new Error('创建失败');

        await loadKnowledgeBases();
        closeCreateKnowledgeModal();
    } catch (e) {
        alert('创建失败：' + e.message);
    }
}

// 显示知识库详情
async function showKnowledgeDetail(kbId) {
    currentDetailKbId = kbId;
    const kb = allKnowledgeBases.find(k => k.id === kbId);
    if (!kb) return;

    document.getElementById('knowledgeDetailTitle').textContent = kb.name;
    document.getElementById('knowledgeDetailDesc').textContent = kb.description || '无描述';

    document.getElementById('knowledgeDetailModal').style.display = 'flex';

    // 加载索引状态和文档列表
    await loadIndexingStatus(kbId);
    await loadDocumentList(kbId);
}

// 关闭知识库详情 Modal
function closeKnowledgeDetailModal() {
    document.getElementById('knowledgeDetailModal').style.display = 'none';
    // 清除轮询
    if (indexingPollInterval) {
        clearInterval(indexingPollInterval);
        indexingPollInterval = null;
    }
    currentDetailKbId = null;
}

// 加载索引状态
async function loadIndexingStatus(kbId) {
    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${kbId}/index/status`);
        const data = await res.json();

        const container = document.getElementById('indexingStatus');
        container.innerHTML = `
            <div class="indexing-status-header">
                <h4>索引状态</h4>
                <span class="text-muted">策略：${data.indexing_strategy}</span>
            </div>
            <div class="status-breakdown">
                <span class="status-item">
                    <span class="status-dot pending"></span>
                    待索引：${data.status_breakdown.pending}
                </span>
                <span class="status-item">
                    <span class="status-dot indexing"></span>
                    索引中：${data.status_breakdown.indexing}
                </span>
                <span class="status-item">
                    <span class="status-dot indexed"></span>
                    已完成：${data.status_breakdown.indexed}
                </span>
                <span class="status-item">
                    <span class="status-dot failed"></span>
                    失败：${data.status_breakdown.failed}
                </span>
            </div>
            <div class="text-muted" style="margin-top: 0.5rem; font-size: 0.75rem;">
                总分块：${data.total_chunks} | 最后索引：${data.last_indexed_at ? new Date(data.last_indexed_at).toLocaleString() : '从未'}
            </div>
        `;
    } catch (e) {
        document.getElementById('indexingStatus').innerHTML = '<span class="text-muted">加载状态失败</span>';
    }
}

// 加载文档列表
async function loadDocumentList(kbId) {
    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${kbId}`);
        const kb = await res.json();

        const container = document.getElementById('documentList');
        if (!kb.documents || kb.documents.length === 0) {
            container.innerHTML = '<div class="text-muted" style="text-align: center; padding: 2rem;">暂无文档</div>';
            return;
        }

        container.innerHTML = kb.documents.map(doc => `
            <div class="document-item">
                <div class="document-item-info">
                    <span class="document-item-icon">📄</span>
                    <div>
                        <div class="document-item-name">${escapeHtml(doc.filename)}</div>
                        <div class="document-item-meta">
                            ${doc.size} bytes |
                            <span class="document-status-badge ${doc.status}">${doc.status}</span>
                            ${doc.chunk_count ? `| ${doc.chunk_count} 分块` : ''}
                            ${doc.error_message ? `| ${escapeHtml(doc.error_message)}` : ''}
                        </div>
                    </div>
                </div>
                <div class="document-item-actions">
                    <button class="btn-icon" onclick="alert('文档预览功能开发中')" title="预览">👁️</button>
                    <button class="btn-icon delete" onclick="deleteDocument('${kbId}', '${doc.id}')" title="删除">🗑️</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        document.getElementById('documentList').innerHTML = '<span class="text-muted">加载文档列表失败</span>';
    }
}

// 上传文档
function uploadDocument() {
    document.getElementById('documentUploadInput').click();
}

// 处理文档上传
async function handleDocumentUpload(event) {
    const file = event.target.files[0];
    if (!file || !currentDetailKbId) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${currentDetailKbId}/documents`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '上传失败');
        }

        const result = await res.json();
        alert(`文档 "${result.filename}" 上传成功`);

        // 刷新列表
        await loadKnowledgeBases();
        await loadDocumentList(currentDetailKbId);
        await loadIndexingStatus(currentDetailKbId);

    } catch (e) {
        alert('上传失败：' + e.message);
    }

    event.target.value = ''; // Reset input
}

// 触发索引
async function triggerIndexing(strategy) {
    if (!currentDetailKbId) return;

    // 清除之前的轮询
    if (indexingPollInterval) {
        clearInterval(indexingPollInterval);
    }

    // 立即显示索引中状态
    const indexingStatusEl = document.getElementById('indexingStatus');
    if (indexingStatusEl) {
        indexingStatusEl.innerHTML = `
            <div class="indexing-status-header">
                <h4>索引中...</h4>
            </div>
            <div style="text-align: center; padding: 2rem;">
                <div class="spinner" style="width: 40px; height: 40px; border: 3px solid var(--border-color); border-top-color: var(--accent-gold); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1rem;"></div>
                <p class="text-muted">正在向量化文档，请稍候...</p>
            </div>
        `;
    }

    // 启动轮询，每 2 秒刷新一次状态
    indexingPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/knowledge/${currentDetailKbId}/index/status`);
            const data = await res.json();

            // 检查是否还有待索引或索引中的文档
            const hasPendingOrIndexing = data.status_breakdown.pending > 0 || data.status_breakdown.indexing > 0;

            if (!hasPendingOrIndexing) {
                // 索引完成，停止轮询并刷新完整状态
                if (indexingPollInterval) {
                    clearInterval(indexingPollInterval);
                    indexingPollInterval = null;
                }
                // 刷新文档列表（清除错误消息）和状态
                await loadDocumentList(currentDetailKbId);
                await loadIndexingStatus(currentDetailKbId);
                alert('索引完成！');
            } else {
                // 仍在索引中，仅更新状态显示（不刷新文档列表）
                await loadIndexingStatus(currentDetailKbId);
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 2000);

    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${currentDetailKbId}/index`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy })
        });

        const result = await res.json();

        if (!res.ok) {
            if (indexingPollInterval) {
                clearInterval(indexingPollInterval);
                indexingPollInterval = null;
            }
            throw new Error(result.detail || '索引失败');
        }

        // 索引请求成功，等待 500ms 后开始轮询检查状态
        console.log('索引请求成功:', result.message);

        // 延迟启动轮询，确保后端已开始处理
        await new Promise(resolve => setTimeout(resolve, 500));

    } catch (e) {
        if (indexingPollInterval) {
            clearInterval(indexingPollInterval);
            indexingPollInterval = null;
        }
        alert('索引失败：' + e.message);
        // 刷新状态和文档列表以显示错误
        await loadIndexingStatus(currentDetailKbId);
        await loadDocumentList(currentDetailKbId);
    }
}

// 删除文档
async function deleteDocument(kbId, docId) {
    if (!confirm('确定要删除此文档吗？')) return;

    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${kbId}/documents/${docId}`, {
            method: 'DELETE'
        });

        if (!res.ok) throw new Error('删除失败');

        await loadKnowledgeBases();
        await loadDocumentList(kbId);
        await loadIndexingStatus(kbId);

    } catch (e) {
        alert('删除失败：' + e.message);
    }
}

// ==================== Image Upload Functions ====================

function initImageUpload() {
    const messagesContainer = document.getElementById('messages');
    const inputContainer = document.querySelector('.input-container');

    // Drag over
    inputContainer.addEventListener('dragover', (e) => {
        e.preventDefault();
        inputContainer.classList.add('drag-over');
    });

    // Drag leave
    inputContainer.addEventListener('dragleave', () => {
        inputContainer.classList.remove('drag-over');
    });

    // Drop
    inputContainer.addEventListener('drop', (e) => {
        e.preventDefault();
        inputContainer.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        handleFiles(files);
    });

    // Paste
    document.addEventListener('paste', (e) => {
        const items = e.clipboardData.items;
        for (let item of items) {
            if (item.type.indexOf('image') !== -1) {
                const file = item.getAsFile();
                handleFiles([file]);
                break;
            }
        }
    });
}

function handleFiles(files) {
    for (let file of files) {
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                pendingImages.push(e.target.result);
                renderImagePreviews();
            };
            reader.readAsDataURL(file);
        }
    }
}

function handleImageFileSelect(event) {
    const files = event.target.files;
    handleFiles(files);
    event.target.value = ''; // Reset input
}

function renderImagePreviews() {
    const container = document.getElementById('imagePreviewContainer');
    if (pendingImages.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = pendingImages.map((img, index) => `
        <div class="image-preview-item">
            <img src="${img}" alt="preview" />
            <button class="btn-remove-image" onclick="removeImage(${index})">×</button>
        </div>
    `).join('');
}

function removeImage(index) {
    pendingImages.splice(index, 1);
    renderImagePreviews();
}

function clearImages() {
    pendingImages = [];
    renderImagePreviews();
}

// ==================== Knowledge Base Edit & Delete Functions ====================

// 编辑知识库
async function editKnowledgeBase(kbId) {
    currentEditKbId = kbId;
    const kb = allKnowledgeBases.find(k => k.id === kbId);
    if (!kb) return;

    document.getElementById('editKnowledgeName').value = kb.name;
    document.getElementById('editKnowledgeDesc').value = kb.description || '';

    document.getElementById('editKnowledgeModal').style.display = 'flex';
}

// 关闭编辑知识库 Modal
function closeEditKnowledgeModal() {
    document.getElementById('editKnowledgeModal').style.display = 'none';
    currentEditKbId = null;
}

// 保存编辑的知识库
async function saveEditKnowledgeBase() {
    if (!currentEditKbId) return;

    const name = document.getElementById('editKnowledgeName').value.trim();
    const description = document.getElementById('editKnowledgeDesc').value.trim();

    if (!name) {
        alert('请输入知识库名称');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${currentEditKbId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '保存失败');
        }

        await loadKnowledgeBases();
        closeEditKnowledgeModal();

        // 如果正在查看该知识库详情，也刷新详情
        if (currentDetailKbId === currentEditKbId) {
            await loadIndexingStatus(currentDetailKbId);
        }

    } catch (e) {
        alert('保存失败：' + e.message);
    }
}

// 确认删除知识库
function confirmDeleteKnowledgeBase(kbId) {
    if (!confirm('确定要删除此知识库吗？\n\n警告：此操作将删除知识库及其所有文档和索引数据，且无法恢复！')) {
        return;
    }
    deleteKnowledgeBase(kbId);
}

// 删除知识库
async function deleteKnowledgeBase(kbId) {
    try {
        const res = await fetch(`${API_BASE}/api/knowledge/${kbId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '删除失败');
        }

        // 如果正在查看该知识库详情，关闭详情面板
        if (currentDetailKbId === kbId) {
            closeKnowledgeDetailModal();
        }

        // 从启用列表中移除
        if (enabledKnowledgeBases.includes(kbId)) {
            enabledKnowledgeBases = enabledKnowledgeBases.filter(id => id !== kbId);
            renderKnowledgeSelector();
        }

        await loadKnowledgeBases();

    } catch (e) {
        alert('删除失败：' + e.message);
    }
}
