// Historial en sessionStorage — persiste al recargar, se borra al cerrar la pestaña
const _CHAT_KEY = 'aliv_chat_history';
const _chatHistory = JSON.parse(sessionStorage.getItem(_CHAT_KEY) || '[]');
let _chatBusy = false;

function _chatSaveHistory() {
    sessionStorage.setItem(_CHAT_KEY, JSON.stringify(_chatHistory));
}

function chatToggle() {
    const panel = document.getElementById('chatPanel');
    const fab   = document.getElementById('chatFab');
    const isOpen = panel.classList.toggle('chat-open');
    fab.classList.toggle('chat-fab-active', isOpen);
    if (isOpen) document.getElementById('chatInput').focus();
}

function chatSend() {
    if (_chatBusy) return;
    const input = document.getElementById('chatInput');
    const text  = input.value.trim();
    if (!text) return;

    input.value = '';
    _chatHistory.push({ role: 'user', content: text });
    _chatSaveHistory();
    _chatAppend('user', text);
    _chatSetBusy(true);

    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: _chatHistory }),
    })
    .then(r => r.json())
    .then(data => {
        _chatSetBusy(false);
        const reply = data.reply || ('❌ ' + (data.error || 'Error desconocido'));
        _chatHistory.push({ role: 'assistant', content: reply });
        _chatSaveHistory();
        _chatAppend('ai', reply);
    })
    .catch(() => {
        _chatSetBusy(false);
        _chatAppend('ai', '❌ Error de conexión. Verifica tu red e intenta de nuevo.');
    });
}

function _chatSetBusy(busy) {
    _chatBusy = busy;
    document.getElementById('chatSendBtn').disabled = busy;
    document.getElementById('chatInput').disabled   = busy;

    const typing = document.getElementById('chatTyping');
    if (busy) {
        if (!typing) {
            const wrap = document.getElementById('chatMessages');
            const div  = document.createElement('div');
            div.id        = 'chatTyping';
            div.className = 'chat-msg chat-msg-ai';
            div.innerHTML = '<div class="chat-bubble chat-typing"><span></span><span></span><span></span></div>';
            wrap.appendChild(div);
            wrap.scrollTop = wrap.scrollHeight;
        }
    } else {
        if (typing) typing.remove();
        document.getElementById('chatInput').focus();
    }
}

function _chatAppend(role, text) {
    const wrap   = document.getElementById('chatMessages');
    const div    = document.createElement('div');
    div.className = `chat-msg chat-msg-${role}`;
    const bubble  = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.innerHTML = _chatFormat(text);
    div.appendChild(bubble);
    wrap.appendChild(div);
    wrap.scrollTop = wrap.scrollHeight;
}

function _chatFormat(raw) {
    // Escapar HTML para seguridad
    let s = raw
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Negrita
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Itálica
    s = s.replace(/(?<!\*)\*([^\s*][^*]*?)\*(?!\*)/g, '<em>$1</em>');
    // Código inline
    s = s.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,.12);padding:1px 5px;border-radius:4px;font-size:12px">$1</code>');

    // Listas: líneas que empiezan con - o •
    const lines = s.split('\n');
    const out   = [];
    let inList   = false;
    for (const line of lines) {
        const li = line.match(/^[-•]\s+(.+)$/);
        if (li) {
            if (!inList) { out.push('<ul class="chat-list">'); inList = true; }
            out.push(`<li>${li[1]}</li>`);
        } else {
            if (inList) { out.push('</ul>'); inList = false; }
            out.push(line);
        }
    }
    if (inList) out.push('</ul>');

    return out.join('<br>').replace(/<br>(<ul)/g, '$1').replace(/(<\/ul>)<br>/g, '$1');
}

document.addEventListener('DOMContentLoaded', () => {
    // Restaurar mensajes guardados (sobreescribe el saludo del HTML si hay historial)
    if (_chatHistory.length > 0) {
        const wrap = document.getElementById('chatMessages');
        wrap.innerHTML = '';
        _chatHistory.forEach(m => _chatAppend(m.role === 'user' ? 'user' : 'ai', m.content));
    }

    // Enviar con Enter
    const input = document.getElementById('chatInput');
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatSend(); }
        });
    }
});
