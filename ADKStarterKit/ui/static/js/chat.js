// Session (persisted in memory for the tab lifetime)
let currentSessionId = null;

function getTime() {
  const now = new Date();
  let h = now.getHours(), m = now.getMinutes();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${m.toString().padStart(2,'0')} ${ampm}`;
}

function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function scrollToBottom() {
  const el = document.getElementById('chatMessages');
  el.scrollTop = el.scrollHeight;
}

function botAvatarSVG() {
  return `<div class="bot-bubble-avatar">
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="16" cy="16" r="16" fill="#1a56db"/>
      <rect x="6" y="14" width="20" height="12" rx="2.5" fill="white" opacity="0.9"/>
      <rect x="9" y="17" width="3.5" height="3.5" rx="0.8" fill="#1a56db"/>
      <rect x="14" y="17" width="3.5" height="3.5" rx="0.8" fill="#1a56db"/>
      <rect x="19" y="17" width="3.5" height="3.5" rx="0.8" fill="#1a56db"/>
      <rect x="13" y="7" width="6" height="8" rx="1.5" fill="white" opacity="0.9"/>
      <circle cx="16" cy="6.5" r="1.5" fill="white" opacity="0.7"/>
    </svg>
  </div>`;
}

function appendUserMessage(text) {
  const messages = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message user-message';
  div.innerHTML = `<div class="bubble-content"><p>${escapeHtml(text)}</p><span class="msg-time">${getTime()}</span></div>`;
  messages.appendChild(div);
  scrollToBottom();
}

function showTyping() {
  const messages = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message bot-message';
  div.id = 'typingIndicator';
  div.innerHTML = `${botAvatarSVG()}<div class="typing-bubbles"><span></span><span></span><span></span></div>`;
  messages.appendChild(div);
  scrollToBottom();
}

function removeTyping() {
  const t = document.getElementById('typingIndicator');
  if (t) t.remove();
}

function createStreamingBubble() {
  const messages = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message bot-message';
  div.id = 'streamingBubble';
  div.innerHTML = `${botAvatarSVG()}<div class="bubble-content" id="streamingContent"><p id="streamingText"></p><span class="msg-time" id="streamingTime"></span></div>`;
  messages.appendChild(div);
  scrollToBottom();
  return document.getElementById('streamingText');
}

function finalizeStreamingBubble(fullText) {
  const bubble = document.getElementById('streamingBubble');
  if (!bubble) return;
  bubble.removeAttribute('id');
  const content = document.getElementById('streamingContent');
  content.removeAttribute('id');
  const timeEl = document.getElementById('streamingTime');
  if (timeEl) { timeEl.textContent = getTime(); timeEl.removeAttribute('id'); }

  const dayPattern = /day\s*\d+/gi;
  const hasItinerary = (fullText.match(dayPattern) || []).length >= 2;

  if (hasItinerary) {
    content.innerHTML = renderItineraryHTML(fullText) + `<span class="msg-time">${getTime()}</span>`;
  } else {
    const p = content.querySelector('p');
    if (p) p.innerHTML = formatBotText(fullText);
  }
  scrollToBottom();
}

function formatBotText(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

function getActivityIcon(text) {
  const l = text.toLowerCase();
  if (/museum|gallery|chapel|exhibit/.test(l)) return '🏛️';
  if (/church|basilica|cathedral|temple/.test(l)) return '⛪';
  if (/fountain|piazza|square|plaza/.test(l)) return '⛲';
  if (/dinner|food|restaur|cuisine|eat|café|cafe/.test(l)) return '🍽️';
  if (/lunch/.test(l)) return '🥗';
  if (/breakfast/.test(l)) return '☕';
  if (/shop|market|corso|store/.test(l)) return '🛍️';
  if (/sunset|sunrise|view|hill/.test(l)) return '🌅';
  if (/park|garden|villa/.test(l)) return '🌿';
  if (/colosseum|forum|ruin|ancient/.test(l)) return '🏟️';
  if (/castle|fortress|bridge/.test(l)) return '🏰';
  if (/art|paint|sistine/.test(l)) return '🎨';
  if (/morning/.test(l)) return '🌄';
  if (/afternoon/.test(l)) return '☀️';
  if (/evening|night/.test(l)) return '🌙';
  return '📍';
}

function renderItineraryHTML(text) {
  const blocks = text.split(/(?=\bDay\s+\d+)/gi).filter(b => b.trim());
  let intro = '', cards = '', hasCards = false, startIdx = 0;

  if (blocks.length > 0 && !/^\s*Day\s+\d+/i.test(blocks[0])) {
    intro = `<p style="margin-bottom:10px">${formatBotText(blocks[0].trim())}</p>`;
    startIdx = 1;
  }

  for (let i = startIdx; i < blocks.length; i++) {
    const block = blocks[i].trim();
    const m = block.match(/^(Day\s+\d+)[:\s\-–]*(.*?)(\n|$)/i);
    if (!m) continue;
    hasCards = true;
    const dayLabel = m[1], dayTitle = m[2].trim();
    const lines = block.slice(m[0].length).trim().split('\n').filter(l => l.trim());

    const items = lines.map((line, idx) => {
      const cleaned = line.replace(/^[-•*]\s*/, '').replace(/^\d+\.\s*/, '').trim();
      if (!cleaned) return '';
      const icon = getActivityIcon(cleaned);
      const hasDot = idx === 0 || idx === lines.length - 1;
      const parts = cleaned.split(':');
      const content = parts.length >= 2
        ? `<span style="color:#6b7a99;font-size:0.82rem">${escapeHtml(parts[0])}:</span> <strong>${escapeHtml(parts.slice(1).join(':').trim())}</strong>`
        : escapeHtml(cleaned);
      return `<div class="timeline-item${hasDot?' has-dot':''}"><span class="item-icon">${icon}</span><span class="item-text">${content}</span></div>`;
    }).join('');

    cards += `<div class="itinerary-card">
      <div class="day-header">
        <span class="day-badge">${escapeHtml(dayLabel)}</span>
        ${dayTitle ? `<span class="day-title">${escapeHtml(dayTitle)}</span>` : ''}
      </div>
      <div class="timeline">${items}</div>
    </div>`;
  }

  const btns = hasCards ? `<div class="action-btns">
    <button class="action-btn" onclick="downloadItinerary()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      Download PDF
    </button>
    <button class="action-btn" onclick="makeChanges()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      Make Changes
    </button>
  </div>` : '';

  return intro + cards + btns;
}

function appendErrorBubble(text) {
  const messages = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message bot-message';
  div.innerHTML = `${botAvatarSVG()}<div class="bubble-content"><p>${escapeHtml(text)}</p><span class="msg-time">${getTime()}</span></div>`;
  messages.appendChild(div);
  scrollToBottom();
}

// ── SEND (SSE streaming) ──────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  sendBtn.disabled = true;
  appendUserMessage(text);
  showTyping();

  let fullText = '', streamingTextEl = null;

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: currentSessionId })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const jsonStr = line.slice('data:'.length).trim();
        if (!jsonStr) continue;
        let evt;
        try { evt = JSON.parse(jsonStr); } catch { continue; }

        if (evt.type === 'session') {
          currentSessionId = evt.session_id;
        } else if (evt.type === 'token') {
          if (!streamingTextEl) { removeTyping(); streamingTextEl = createStreamingBubble(); }
          fullText += evt.text;
          streamingTextEl.textContent = fullText;
          scrollToBottom();
        } else if (evt.type === 'error') {
          removeTyping();
          appendErrorBubble(evt.text);
        } else if (evt.type === 'done') {
          if (streamingTextEl) finalizeStreamingBubble(fullText);
          else if (!fullText) { removeTyping(); appendErrorBubble('The agent returned an empty response.'); }
          break;
        }
      }
    }

    if (streamingTextEl && fullText) finalizeStreamingBubble(fullText);

  } catch (err) {
    removeTyping();
    appendErrorBubble(`⚠️ Error: ${err.message}`);
  }

  sendBtn.disabled = false;
  input.focus();
}

document.getElementById('messageInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function downloadItinerary() {
  alert('Connect to your backend to generate a PDF from the itinerary.');
}

function makeChanges() {
  const input = document.getElementById('messageInput');
  input.value = 'I would like to make some changes: ';
  input.focus();
}