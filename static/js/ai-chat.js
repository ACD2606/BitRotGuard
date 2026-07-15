/* ================================================================
   BitRot Guard — AI Chat Module
   ================================================================
   Handles the sliding chat panel, message rendering, typing
   indicators, and auto-explain after workflow steps.
   ================================================================ */

const AIChat = (() => {
    const panel = document.getElementById('aiChatPanel');
    const fab = document.getElementById('aiChatFab');
    const messages = document.getElementById('aiMessages');
    const input = document.getElementById('aiInput');
    const sendBtn = document.getElementById('aiSend');
    const badge = document.getElementById('aiBadge');

    let isOpen = false;
    let isConfigured = false;

    function init() {
        fab.addEventListener('click', toggle);
        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });

        // Check for saved API key
        const savedKey = localStorage.getItem('brg_api_key');
        if (savedKey) {
            setApiKey(savedKey, false);
        }
    }

    function toggle() {
        isOpen = !isOpen;
        panel.classList.toggle('open', isOpen);
        fab.classList.toggle('active', isOpen);
        fab.textContent = isOpen ? '✕' : '🤖';
        if (isOpen) {
            setTimeout(() => input.focus(), 300);
        }
    }

    function close() {
        isOpen = false;
        panel.classList.remove('open');
        fab.classList.remove('active');
        fab.textContent = '🤖';
    }

    async function setApiKey(key, save = true) {
        try {
            const res = await fetch('/api/ai/set-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key }),
            });
            const data = await res.json();
            isConfigured = data.configured;
            badge.textContent = isConfigured ? 'Gemini' : 'Offline';
            badge.style.background = isConfigured
                ? 'rgba(80, 250, 123, 0.15)'
                : 'rgba(255, 184, 108, 0.15)';
            badge.style.color = isConfigured ? '#50fa7b' : '#ffb86c';

            if (save && key) {
                localStorage.setItem('brg_api_key', key);
            }
        } catch (e) {
            console.error('Failed to set API key:', e);
        }
    }

    function addMessage(content, role = 'assistant') {
        const div = document.createElement('div');
        div.className = `ai-message ${role}`;

        if (role === 'assistant' || role === 'system') {
            // Simple markdown-like rendering
            div.innerHTML = renderMarkdown(content);
        } else {
            div.textContent = content;
        }

        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
        return div;
    }

    function renderMarkdown(text) {
        // Use marked library if available, otherwise basic rendering
        if (typeof marked !== 'undefined') {
            try {
                return marked.parse(text);
            } catch (e) {
                // Fall through to basic rendering
            }
        }

        // Basic markdown rendering
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/^/, '<p>').replace(/$/, '</p>');
    }

    function showTyping() {
        const div = document.createElement('div');
        div.className = 'ai-typing';
        div.id = 'aiTypingIndicator';
        div.innerHTML = '<div class="ai-typing-dot"></div><div class="ai-typing-dot"></div><div class="ai-typing-dot"></div>';
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    function hideTyping() {
        const indicator = document.getElementById('aiTypingIndicator');
        if (indicator) indicator.remove();
    }

    async function send() {
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        addMessage(text, 'user');
        showTyping();

        try {
            const res = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text }),
            });
            const data = await res.json();
            hideTyping();

            if (data.error) {
                addMessage('⚠️ ' + data.error, 'system');
            } else {
                addMessage(data.message, 'assistant');
            }
        } catch (e) {
            hideTyping();
            addMessage('⚠️ Failed to reach the server.', 'system');
        }
    }

    async function autoExplain(step) {
        try {
            const res = await fetch('/api/ai/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ step }),
            });
            const data = await res.json();
            if (data.explanation) {
                showExplanation(data.explanation);
            }
        } catch (e) {
            console.error('Auto-explain failed:', e);
        }
    }

    function showExplanation(text) {
        const section = document.getElementById('aiExplainSection');
        const content = document.getElementById('aiExplainText');
        if (!section || !content) return;

        content.innerHTML = renderMarkdown(text);
        section.classList.remove('hidden');

        // Scroll into view smoothly
        section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hideExplanation() {
        const section = document.getElementById('aiExplainSection');
        if (section) section.classList.add('hidden');
    }

    async function analyzeFile() {
        try {
            const res = await fetch('/api/ai/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await res.json();
            if (data.error) return;

            const riskSection = document.getElementById('riskAnalysis');
            const riskBadge = document.getElementById('riskBadge');
            const riskScore = document.getElementById('riskScore');
            const riskText = document.getElementById('riskText');

            if (!riskSection) return;

            riskBadge.textContent = data.risk_level;
            riskBadge.className = 'risk-badge ' + data.risk_level.toLowerCase();
            riskScore.textContent = data.risk_score + '/100';
            riskScore.style.color = data.risk_score > 70 ? 'var(--red)'
                : data.risk_score > 40 ? 'var(--orange)' : 'var(--green)';
            riskText.innerHTML = renderMarkdown(data.analysis);

            riskSection.classList.remove('hidden');
        } catch (e) {
            console.error('File analysis failed:', e);
        }
    }

    return {
        init, toggle, close, setApiKey, addMessage, autoExplain,
        hideExplanation, analyzeFile, showExplanation,
    };
})();
