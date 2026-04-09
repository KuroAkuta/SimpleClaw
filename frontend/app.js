// Configuration
const API_BASE = 'http://localhost:8000';
let currentSessionId = null;
let isStreaming = false;
let waitingForConfirmation = false;
let pendingToolCalls = null;
let pendingImages = []; // 待发送的图片（base64）

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

    const messagesContainer = document.getElementById('messages');
    let streamDone = false;

    try {
        const res = await fetch(`${API_BASE}/api/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: messageToSend,
                session_id: currentSessionId,
                images: imagesForApi.length > 0 ? imagesForApi : undefined
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
