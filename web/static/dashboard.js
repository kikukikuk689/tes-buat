(() => {
  const tokenParam = new URLSearchParams(location.search).get('token') || '';
  const tokenHeader = tokenParam ? { 'X-Auth-Token': tokenParam } : {};
  const connection = document.getElementById('connection');
  const ffmpegState = document.getElementById('ffmpegState');
  const liveCount = document.getElementById('liveCount');
  const totalCount = document.getElementById('totalCount');
  const cpuValue = document.getElementById('cpuValue');
  const netValue = document.getElementById('netValue');
  const channelsBody = document.getElementById('channelsBody');
  const events = document.getElementById('events');

  function setConnection(state, label) {
    connection.className = `pill pill-${state}`;
    connection.textContent = label;
  }

  function fmtBitrate(kbps) {
    if (!kbps) return '0 kbps';
    if (kbps >= 1000) return `${(kbps / 1000).toFixed(2)} Mbps`;
    return `${Math.round(kbps)} kbps`;
  }

  function fmtDuration(sec) {
    sec = Math.floor(sec);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
      : `${m}:${String(s).padStart(2, '0')}`;
  }

  function appendEvent(text) {
    const li = document.createElement('li');
    li.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    events.prepend(li);
    while (events.childElementCount > 200) events.lastChild.remove();
  }

  function renderChannels(channels) {
    channelsBody.innerHTML = '';
    let live = 0;
    for (const ch of channels) {
      if (['live', 'starting', 'reconnecting'].includes(ch.state)) live++;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${ch.name}</td>
        <td>${ch.platform}</td>
        <td><span class="state-${ch.state}">${ch.state}</span></td>
        <td>${(ch.fps || 0).toFixed(0)}</td>
        <td>${fmtBitrate(ch.bitrate_kbps || 0)}</td>
        <td>${fmtDuration(ch.uptime_sec || 0)}</td>
        <td>
          <button data-action="start" data-id="${ch.id}">▶</button>
          <button class="danger" data-action="stop" data-id="${ch.id}">■</button>
          <button data-action="restart" data-id="${ch.id}">↻</button>
        </td>
      `;
      channelsBody.appendChild(tr);
    }
    liveCount.textContent = live;
    totalCount.textContent = channels.length;
  }

  function renderSystem(sys) {
    cpuValue.textContent = `${(sys.cpu_percent || 0).toFixed(1)}%`;
    netValue.textContent = fmtBitrate(sys.net_up_kbps || 0);
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const id = btn.dataset.id;
    const action = btn.dataset.action;
    try {
      await fetch(`/api/channels/${id}/${action}`, {
        method: 'POST',
        headers: tokenHeader,
      });
      appendEvent(`Channel #${id} → ${action}`);
    } catch (err) {
      appendEvent(`Failed: ${err}`);
    }
  });

  async function fetchInitial() {
    try {
      const r = await fetch('/api/status', { headers: tokenHeader });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      renderChannels(data.channels);
      renderSystem(data.system);
      ffmpegState.textContent = `ffmpeg: ${data.ffmpeg.state}`;
      setConnection('info', 'connected (HTTP)');
    } catch (err) {
      setConnection('error', 'auth failed or offline');
      appendEvent(`Initial fetch failed: ${err.message}`);
    }
  }

  function connectWs() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const tokenSegment = tokenParam ? `?token=${encodeURIComponent(tokenParam)}` : '';
    const ws = new WebSocket(`${scheme}://${location.host}/ws${tokenSegment}`);
    ws.onopen = () => setConnection('live', 'realtime connected');
    ws.onclose = () => {
      setConnection('error', 'reconnecting…');
      setTimeout(connectWs, 2500);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'snapshot') {
          renderChannels(msg.data.channels);
          renderSystem(msg.data.system);
        } else if (msg.type === 'system.stats') {
          renderSystem(msg.data);
        } else if (msg.type === 'stream.state' || msg.type === 'stream.stats') {
          fetchInitial();
          if (msg.type === 'stream.state') {
            appendEvent(`State → ${JSON.stringify(msg.data)}`);
          }
        } else if (msg.type === 'notification') {
          appendEvent(`${msg.data.title}: ${msg.data.message}`);
        }
      } catch (err) {
        appendEvent(`Bad WS payload: ${err}`);
      }
    };
  }

  fetchInitial();
  connectWs();
  setInterval(fetchInitial, 8000);
})();
