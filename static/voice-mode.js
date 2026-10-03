/* SilentHelp — Voice mode (BETA, local prototype)
 * ------------------------------------------------
 * Loaded ONLY when the app is opened with ?voice=1 (see the tiny loader at the
 * bottom of templates/app.html). Nothing here replaces the text chat or its
 * safety logic: a spoken turn is sent through the SAME App.send() path, so the
 * instant keyword scan, /api/chat detection, the in-chat resource message and
 * the urgent popup all run exactly as they do for typed messages. Voice only
 * adds: mic -> local STT -> App.send() -> reply spoken by local TTS.
 *
 * Local voice service: http://127.0.0.1:5077 (~/silenthelp-voice, VibeVoice).
 * Audio never leaves this Mac; the transcript goes to the chat backend exactly
 * like typed text does.
 */
(function () {
  'use strict';
  if (window.SHVoice) return;
  var SVC = (window.SH_VOICE_URL || 'http://127.0.0.1:5077');
  var WS_SVC = SVC.replace(/^http/, 'ws');
  var CRISIS_LINE = 'If you might be in danger, please call or text 988, or text HOME to 741741, right now. Real people are there any time.';

  var css = `
  #shv-btn{height:48px;min-width:48px;padding:0 16px;border-radius:13px;border:1px solid rgba(255,255,255,.25);background:rgba(20,28,40,.55);color:#fff;font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:8px;backdrop-filter:blur(8px)}
  #shv-btn:hover{background:rgba(40,56,80,.7)}
  #shv-btn .shv-dot{width:14px;height:14px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#fff,#9cc8ff 45%,#6a8dff 80%);box-shadow:0 0 10px rgba(140,180,255,.8)}
  .shv-beta{font-size:9.5px;letter-spacing:.14em;font-weight:700;padding:2px 6px;border-radius:6px;background:rgba(255,214,150,.18);color:#ffd79a;border:1px solid rgba(255,214,150,.35)}
  #shv-overlay{position:fixed;inset:0;z-index:250;display:none;flex-direction:column;align-items:center;color:#fff;
    background:radial-gradient(1200px 700px at 50% 38%,#1c2a44 0%,#0d1422 55%,#070b13 100%);font-family:inherit;overflow:hidden}
  #shv-overlay.on{display:flex;animation:shvFade .45s ease}
  @keyframes shvFade{from{opacity:0}to{opacity:1}}
  .shv-top{width:100%;max-width:880px;display:flex;justify-content:space-between;align-items:center;padding:22px 28px 0}
  .shv-title{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:600;letter-spacing:.01em}
  .shv-x{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);color:#fff;border-radius:999px;padding:8px 16px;font-size:12.5px;cursor:pointer}
  .shv-stage{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;max-width:760px;padding:0 28px;min-height:0}
  #shv-orb{--lvl:0;width:210px;height:210px;border-radius:50%;position:relative;transform:scale(calc(1 + var(--lvl)*.18));transition:transform .09s linear;
    background:radial-gradient(circle at 34% 30%,#ffffff 0%,#d9ecff 18%,#8fbaff 46%,#5b6fe0 72%,#3b3f9e 100%);
    box-shadow:0 0 60px rgba(120,160,255,.45),0 0 140px rgba(90,110,230,.25),inset -18px -24px 60px rgba(30,30,90,.45)}
  #shv-orb::after{content:"";position:absolute;inset:-18px;border-radius:50%;border:1px solid rgba(160,190,255,.25);animation:shvRing 4.5s ease-in-out infinite}
  #shv-orb.idle{animation:shvBreathe 6s ease-in-out infinite}
  #shv-orb.listening{background:radial-gradient(circle at 34% 30%,#fff 0%,#e3fff4 18%,#8fe0c4 46%,#3fa58f 74%,#1f5f63 100%);box-shadow:0 0 60px rgba(120,230,190,.45),0 0 140px rgba(60,170,150,.25),inset -18px -24px 60px rgba(10,50,50,.45)}
  #shv-orb.thinking{animation:shvThink 1.6s ease-in-out infinite}
  #shv-orb.speaking{background:radial-gradient(circle at 34% 30%,#fff 0%,#fff1e2 16%,#ffc9a3 42%,#e08a8a 70%,#8a4f8f 100%);box-shadow:0 0 70px rgba(255,190,150,.45),0 0 150px rgba(220,140,160,.25),inset -18px -24px 60px rgba(70,30,70,.45)}
  #shv-orb.crisis{box-shadow:0 0 70px rgba(255,170,120,.55),0 0 160px rgba(255,140,90,.25)}
  @keyframes shvBreathe{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
  @keyframes shvThink{0%,100%{transform:scale(.96);filter:brightness(.95)}50%{transform:scale(1.03);filter:brightness(1.12)}}
  @keyframes shvRing{0%,100%{transform:scale(1);opacity:.6}50%{transform:scale(1.08);opacity:.15}}
  #shv-status{margin-top:34px;font-size:15px;color:rgba(255,255,255,.78);font-weight:400;min-height:22px;text-align:center}
  #shv-live{margin-top:12px;font-size:17px;line-height:1.55;color:#fff;font-weight:300;text-align:center;min-height:52px;max-width:640px}
  #shv-live .you{color:rgba(255,255,255,.55)}
  #shv-reply{margin-top:10px;font-size:15px;line-height:1.65;color:rgba(255,236,220,.92);font-weight:300;text-align:center;max-width:640px;max-height:22vh;overflow:auto}
  .shv-controls{display:flex;gap:16px;align-items:center;justify-content:center;padding:18px 0 10px}
  .shv-mic{width:74px;height:74px;border-radius:50%;border:none;cursor:pointer;background:#fff;color:#0d1422;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 30px rgba(0,0,0,.35)}
  .shv-mic.live{background:#ff6b6b;color:#fff;animation:shvPulse 1.4s ease-in-out infinite}
  @keyframes shvPulse{0%,100%{box-shadow:0 0 0 0 rgba(255,107,107,.5)}50%{box-shadow:0 0 0 16px rgba(255,107,107,0)}}
  .shv-round{height:48px;padding:0 20px;border-radius:999px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;font-size:13px;font-weight:600;cursor:pointer}
  .shv-round[disabled]{opacity:.35;cursor:default}
  .shv-opts{display:flex;gap:18px;align-items:center;justify-content:center;font-size:12px;color:rgba(255,255,255,.6)}
  .shv-opts label{display:flex;gap:6px;align-items:center;cursor:pointer}
  #shv-typed{display:none;gap:10px;width:100%;max-width:560px;margin-top:10px}
  #shv-typed input{flex:1;height:44px;border-radius:12px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;padding:0 14px;font-size:14px;outline:none}
  .shv-foot{width:100%;max-width:880px;padding:10px 28px 18px;display:flex;flex-direction:column;gap:8px;align-items:center}
  .shv-help{font-size:12.5px;color:#ffd9a8;background:rgba(255,190,120,.10);border:1px solid rgba(255,190,120,.28);border-radius:12px;padding:9px 14px;text-align:center}
  .shv-help b{color:#ffe2b8}
  #shv-crisis{display:none;width:100%;max-width:640px;margin-top:18px;padding:16px 18px;border-radius:16px;background:rgba(255,120,80,.14);border:1px solid rgba(255,150,110,.55);text-align:left}
  #shv-crisis.on{display:block;animation:shvFade .4s ease}
  #shv-crisis .h{font-size:14px;font-weight:700;color:#ffd2bd;letter-spacing:.02em}
  #shv-crisis .r{margin-top:8px;font-size:14px;line-height:1.7;color:#fff}
  #shv-crisis a{color:#fff;font-weight:700}
  .shv-meta{font-size:10.5px;color:rgba(255,255,255,.38);text-align:center;line-height:1.5}
  `;

  var S = {
    open: false, state: 'idle', health: null, autoListen: true,
    mic: null, micCtx: null, proc: null, chunks: [], recording: false,
    speechStarted: false, silenceMs: 0, noise: 0.006, startedAt: 0, lastPartialAt: 0, partialBusy: false,
    play: null, playHead: 0, sources: [], ws: null, analyser: null, speakToken: 0,
    pendingChat: null, crisis: false, t: {}
  };

  function $(id) { return document.getElementById(id); }
  // app.html declares `const App = {...}` (a global lexical binding, not window.App).
  function A() { try { return App; } catch (_) { return window.App; } }
  function esc(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  // ------------------------------------------------------------------ UI
  function build() {
    var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    var ov = document.createElement('div'); ov.id = 'shv-overlay';
    ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-label', 'SilentHelp voice mode (beta)');
    ov.innerHTML = `
      <div class="shv-top">
        <div class="shv-title"><span>Voice</span><span class="shv-beta">BETA</span></div>
        <button class="shv-x" id="shv-close">Back to text chat</button>
      </div>
      <div class="shv-stage">
        <div id="shv-orb" class="idle" aria-hidden="true"></div>
        <div id="shv-status">Tap the mic and say what's on your mind.</div>
        <div id="shv-live"></div>
        <div id="shv-reply"></div>
        <div id="shv-crisis" role="alert" aria-live="assertive">
          <div class="h">You deserve real support right now</div>
          <div class="r">Call or text <a href="tel:988">988</a> (Suicide &amp; Crisis Lifeline), or text <b>HOME</b> to <b>741741</b> (Crisis Text Line). Real people, any time. If you're in immediate danger, call 911.</div>
        </div>
        <div id="shv-typed"><input id="shv-typed-in" placeholder="Voice input isn't available — type here and I'll answer out loud" /><button class="shv-round" id="shv-typed-go">Send</button></div>
      </div>
      <div class="shv-controls">
        <button class="shv-round" id="shv-stop" disabled title="Stop speaking (Esc)">Stop</button>
        <button class="shv-mic" id="shv-mic" title="Tap to talk · or hold Space">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 17v4"/></svg>
        </button>
        <button class="shv-round" id="shv-end" title="End this voice session">End</button>
      </div>
      <div class="shv-opts">
        <label><input type="checkbox" id="shv-auto" checked /> Keep listening after each reply</label>
        <span>Tap to talk · hold <b>Space</b> to push-to-talk · <b>Esc</b> stops</span>
      </div>
      <div class="shv-foot">
        <div class="shv-help"><b>If you're in crisis:</b> call or text <b>988</b>, or text <b>HOME to 741741</b>. Real people, any time.</div>
        <div class="shv-meta" id="shv-meta">Beta research prototype · voice by Microsoft VibeVoice, running on this Mac. Your audio stays on this device; the words are sent to the chat just like typing. Not a therapist, and not for emergencies.</div>
      </div>`;
    document.body.appendChild(ov);

    $('shv-close').onclick = close; $('shv-end').onclick = close;
    $('shv-mic').onclick = function () { S.recording ? finishUtterance('tap') : startListening(); };
    $('shv-stop').onclick = function () { stopSpeaking(true); setState('idle'); };
    $('shv-auto').onchange = function (e) { S.autoListen = e.target.checked; };
    $('shv-typed-go').onclick = sendTyped;
    $('shv-typed-in').addEventListener('keydown', function (e) { if (e.key === 'Enter') sendTyped(); });

    document.addEventListener('keydown', function (e) {
      if (!S.open) return;
      if (e.key === 'Escape') { stopSpeaking(true); if (S.recording) cancelListening(); setState('idle'); }
      if (e.code === 'Space' && !e.repeat && document.activeElement && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault(); S.ptt = true; if (!S.recording) startListening();
      }
    });
    document.addEventListener('keyup', function (e) {
      if (S.open && e.code === 'Space' && S.ptt) { S.ptt = false; if (S.recording) finishUtterance('ptt'); }
    });

    // Entry button next to the chat's Send button.
    var input = $('chatInput');
    if (input && input.parentElement && !$('shv-btn')) {
      var b = document.createElement('button');
      b.id = 'shv-btn'; b.title = 'Voice mode (beta)';
      b.innerHTML = '<span class="shv-dot"></span>Voice <span class="shv-beta">BETA</span>';
      b.onclick = openVoice;
      input.parentElement.appendChild(b);
    }
  }

  function setState(s, msg) {
    S.state = s;
    var orb = $('shv-orb'); orb.className = s + (S.crisis ? ' crisis' : '');
    if (s !== 'speaking' && s !== 'listening') orb.style.setProperty('--lvl', 0);
    var m = { idle: "Tap the mic and say what's on your mind.", listening: 'Listening… take your time.',
      transcribing: 'Got it…', thinking: 'Thinking…', speaking: 'Speaking… tap the mic to cut in.' };
    $('shv-status').textContent = msg || m[s] || '';
    $('shv-mic').classList.toggle('live', S.recording);
    $('shv-stop').disabled = (s !== 'speaking');
  }

  function stepAside(on) {
    var ov = $('shv-overlay'); if (!ov) return;
    if (on) { S.hiddenForUrgent = true; if (S.recording) cancelListening(); ov.style.display = 'none'; }
    else if (S.hiddenForUrgent) { S.hiddenForUrgent = false; ov.style.display = ''; }
  }

  function showCrisis() {
    S.crisis = true;
    var c = $('shv-crisis'); if (c) c.classList.add('on');
    var orb = $('shv-orb'); if (orb) orb.classList.add('crisis');
  }

  async function openVoice() {
    if (A() && A().go) { try { A().go('chat'); } catch (_) {} }
    S.open = true; $('shv-overlay').classList.add('on'); setState('idle', 'Connecting to the on-device voice…');
    try {
      var r = await fetch(SVC + '/health', { cache: 'no-store' });
      S.health = await r.json();
    } catch (e) { S.health = null; }
    var h = S.health;
    if (!h) {
      setState('idle', "The local voice service isn't running. Start it with ~/silenthelp-voice/start.sh — text chat still works.");
      $('shv-typed').style.display = 'none';
      return;
    }
    var sttOk = h.stt && h.stt.ready, ttsOk = h.tts && h.tts.ready;
    $('shv-mic').style.display = sttOk ? '' : 'none';
    $('shv-typed').style.display = sttOk ? 'none' : 'flex';
    $('shv-meta').innerHTML = 'Beta research prototype · speech: ' + esc(ttsOk ? 'VibeVoice-Realtime-0.5B (' + h.tts.device + ', voice ' + h.tts.voice.replace(/^en-|_\w+$/g, '') + ')' : 'unavailable — replies shown as text') +
      ' · listening: ' + esc(sttOk ? h.stt.engine : 'unavailable — type instead') +
      '<br/>Runs on this Mac; your audio is never uploaded. The words go to the chat just like typing. Not a therapist, and not for emergencies.';
    setState('idle', sttOk ? null : 'Voice input is unavailable — type below and I\'ll answer out loud.');
  }

  function close() {
    stopSpeaking(true); cancelListening();
    S.open = false; S.hiddenForUrgent = false; $('shv-overlay').style.display = ''; $('shv-overlay').classList.remove('on');
  }

  // ------------------------------------------------------------------ mic + end-of-speech
  async function ensureMic() {
    if (S.mic) return true;
    try {
      S.mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    } catch (e) {
      setState('idle', 'Microphone permission was blocked. You can allow it in the browser, or type instead.');
      $('shv-typed').style.display = 'flex';
      return false;
    }
    S.micCtx = new (window.AudioContext || window.webkitAudioContext)();
    var src = S.micCtx.createMediaStreamSource(S.mic);
    S.proc = S.micCtx.createScriptProcessor(2048, 1, 1);
    S.proc.onaudioprocess = onAudio;
    src.connect(S.proc); S.proc.connect(S.micCtx.destination);
    return true;
  }

  async function startListening() {
    stopSpeaking(true);                 // barge-in: cut off any reply in progress
    if (!(await ensureMic())) return;
    if (S.micCtx.state === 'suspended') await S.micCtx.resume();
    S.chunks = []; S.speechStarted = false; S.speechIdx = 0; S.silenceMs = 0; S.startedAt = performance.now(); S.lastPartialAt = 0;
    S.recording = true; $('shv-live').innerHTML = ''; setState('listening');
  }

  function cancelListening() { S.recording = false; S.chunks = []; if (S.open) setState('idle'); }

  function onAudio(ev) {
    if (!S.recording) return;
    var d = ev.inputBuffer.getChannelData(0);
    S.chunks.push(new Float32Array(d));
    var sum = 0; for (var i = 0; i < d.length; i++) sum += d[i] * d[i];
    var rms = Math.sqrt(sum / d.length);
    $('shv-orb').style.setProperty('--lvl', Math.min(1, rms * 9).toFixed(3));
    var ms = d.length / S.micCtx.sampleRate * 1000;
    var thresh = Math.max(0.012, S.noise * 3);
    if (rms > thresh) { if (!S.speechStarted) S.speechIdx = Math.max(0, S.chunks.length - 6); S.speechStarted = true; S.silenceMs = 0; }
    else {
      if (!S.speechStarted) S.noise = S.noise * 0.95 + rms * 0.05;   // learn the room's noise floor
      S.silenceMs += ms;
    }
    var elapsed = performance.now() - S.startedAt;
    if (S.ptt) return;                                             // push-to-talk: release ends it
    if (S.speechStarted && S.silenceMs > 1100) finishUtterance('silence');
    else if (!S.speechStarted && elapsed > 12000) { cancelListening(); setState('idle', "I didn't catch anything — tap the mic when you're ready."); }
    else if (elapsed > 45000) finishUtterance('max');
    else if (S.speechStarted && S.silenceMs < 300 && elapsed - S.lastPartialAt > 2500 && !S.partialBusy && elapsed > 2000) partial();
  }

  // Trim leading silence (keep ~250 ms pre-roll) and most of the trailing
  // end-of-speech silence, so STT only works on the words.
  function collect() {
    var ch = S.chunks.slice(S.speechStarted ? (S.speechIdx || 0) : 0);
    if (S.speechStarted && S.micCtx && S.silenceMs > 400) {
      var drop = Math.floor((S.silenceMs - 350) / 1000 * S.micCtx.sampleRate / 2048);
      if (drop > 0 && drop < ch.length) ch = ch.slice(0, ch.length - drop);
    }
    var n = 0; ch.forEach(function (c) { n += c.length; });
    var all = new Float32Array(n), o = 0; ch.forEach(function (c) { all.set(c, o); o += c.length; });
    return all;
  }

  function toWav16k(f32, inRate) {
    var ratio = inRate / 16000, n = Math.floor(f32.length / ratio), pcm = new Int16Array(n);
    for (var i = 0; i < n; i++) {
      var a = Math.floor(i * ratio), b = Math.min(f32.length, Math.floor((i + 1) * ratio)), s = 0;
      for (var j = a; j < b; j++) s += f32[j];
      var v = Math.max(-1, Math.min(1, s / Math.max(1, b - a)));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    var buf = new ArrayBuffer(44 + pcm.length * 2), dv = new DataView(buf);
    function w(o, s) { for (var k = 0; k < s.length; k++) dv.setUint8(o + k, s.charCodeAt(k)); }
    w(0, 'RIFF'); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
    dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, 16000, true);
    dv.setUint32(28, 32000, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, 'data');
    dv.setUint32(40, pcm.length * 2, true); new Int16Array(buf, 44).set(pcm);
    return new Blob([buf], { type: 'audio/wav' });
  }

  async function stt(blob) {
    var r = await fetch(SVC + '/stt', { method: 'POST', body: blob, headers: { 'Content-Type': 'audio/wav' } });
    if (!r.ok) throw new Error('stt ' + r.status);
    return r.json();
  }

  // Live transcript: re-transcribe the utterance so far every ~2.5 s while speaking.
  async function partial() {
    S.partialBusy = true; S.lastPartialAt = performance.now() - S.startedAt;
    try {
      var j = await stt(toWav16k(collect(), S.micCtx.sampleRate));
      if (S.recording && j.text) $('shv-live').innerHTML = '<span class="you">' + esc(j.text) + '…</span>';
    } catch (_) {} finally { S.partialBusy = false; }
  }

  async function finishUtterance(why) {
    if (!S.recording) return;
    S.recording = false;
    var audio = collect(); S.chunks = [];
    if (audio.length < S.micCtx.sampleRate * 0.35) { setState('idle', "That was very short — tap the mic and try again."); return; }
    setState('transcribing');
    fetch(SVC + '/warm', { method: 'POST' }).catch(function () {});   // wake the GPU while we transcribe + think
    var t0 = performance.now();
    try {
      var j = await stt(toWav16k(audio, S.micCtx.sampleRate));
      S.t.stt = Math.round(performance.now() - t0);
      var text = (j.text || '').trim();
      if (!text) { setState('idle', "I couldn't make that out — want to try again?"); return; }
      $('shv-live').innerHTML = '<span class="you">You:</span> ' + esc(text);
      await turn(text);
    } catch (e) {
      setState('idle', 'Voice input hiccup — you can try again or type instead.');
      $('shv-typed').style.display = 'flex';
    }
  }

  function sendTyped() {
    var i = $('shv-typed-in'), text = (i.value || '').trim(); if (!text) return;
    i.value = ''; $('shv-live').innerHTML = '<span class="you">You:</span> ' + esc(text); turn(text);
  }

  // ------------------------------------------------------------------ chat turn (reuses App.send)
  function turn(text) {
    return new Promise(function (resolve) {
      var App = A();
      if (!App || !App.send) { setState('idle', 'Chat is not ready.'); return resolve(); }
      if (App._sending) { setState('idle', 'Still answering your last message…'); return resolve(); }
      setState('thinking'); $('shv-reply').textContent = '';
      var t0 = performance.now();
      var finished = false;
      function handle(data, err) {
        if (finished) return;
        finished = true;
        S.pendingChat = null;
        S.t.chat = Math.round(performance.now() - t0);
        if (err || !data) {
          var fallback = "I'm here with you. I had a connection hiccup — try again in a moment.";
          $('shv-reply').textContent = fallback; speak(fallback).then(resolve);
          return;
        }
        var act = data.action || {}, lvl = (data.judgment || {}).risk_level;
        var risky = act.route_to_human || lvl === 'crisis' || lvl === 'high';
        if (risky) showCrisis();               // on-screen resources, never voice-only
        var say = data.reply || '';
        if (risky && !/988/.test(say)) say += ' ' + CRISIS_LINE;
        $('shv-reply').textContent = data.reply || '';
        if (!say) {
          setState('idle', "I heard you — tap the mic if you want to keep going.");
          return resolve();
        }
        speak(say).then(resolve);
      }
      S.pendingChat = handle;
      var inp = $('chatInput'); inp.value = text;
      var ret = App.send();                    // same path as typing: scan + detection + popups
      // Fallback: if the api hook missed (race / early return), still speak the
      // assistant line App.send just pushed into history.
      Promise.resolve(ret).then(function () {
        if (finished) return;
        var hist = App.history || [];
        var last = hist[hist.length - 1];
        if (last && last.role === 'assistant' && last.content) {
          handle({ reply: last.content, action: {}, judgment: {} }, null);
        } else {
          handle(null, new Error('no_reply'));
        }
      }, function (e) { handle(null, e); });
    });
  }

  function hookApp() {
    var App = A();
    if (!App || App.__shvHooked) return !!App;
    App.__shvHooked = true;
    var origApi = App.api.bind(App);
    App.api = function (path, body) {
      var p = origApi.apply(null, arguments);
      if (path === '/api/chat' && S.pendingChat) {
        var cb = S.pendingChat;
        Promise.resolve(p).then(function (d) { cb(d, null); }, function (e) { cb(null, e); });
      }
      return p;
    };
    // Whenever the app's own safety path opens the urgent screen (instant scan
    // OR model verdict), mirror the resources inside the voice overlay too.
    // The urgent screen lives inside the app frame's stacking context, so the
    // voice overlay steps ASIDE while it is open (speech keeps going, the mic
    // stays off) and comes back, with the resources card, once it is closed.
    // In voice mode the overlay is the check-in — don't bury it under the
    // gentle popup (z-index 200). Crisis/urgent still steps the overlay aside.
    var origGentle = App.openGentle && App.openGentle.bind(App);
    if (origGentle) App.openGentle = function () {
      if (S.open) return;
      return origGentle.apply(null, arguments);
    };
    var origUrgent = App.openUrgent && App.openUrgent.bind(App);
    if (origUrgent) App.openUrgent = function () {
      var r = origUrgent.apply(null, arguments);
      if (S.open) { showCrisis(); stepAside(true); }
      return r;
    };
    var origClose = App.closePopup && App.closePopup.bind(App);
    if (origClose) App.closePopup = function () { var r = origClose.apply(null, arguments); stepAside(false); return r; };
    return true;
  }

  // ------------------------------------------------------------------ TTS streaming playback
  function stopSpeaking(sendStop) {
    S.speakToken++;
    if (S.ws) { try { if (sendStop && S.ws.readyState === 1) S.ws.send('stop'); S.ws.close(); } catch (_) {} S.ws = null; }
    S.sources.forEach(function (s) { try { s.stop(); } catch (_) {} }); S.sources = [];
    if (S.play) S.playHead = S.play.currentTime;
    if (S.raf) cancelAnimationFrame(S.raf);
  }

  function speak(text) {
    return new Promise(function (resolve) {
      var h = S.health;
      if (!text) { setState('idle'); return resolve(); }
      if (!h || !h.tts || !h.tts.ready) {
        // One refresh in case the service came up after the overlay opened.
        fetch(SVC + '/health', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (hh) {
          S.health = hh;
          if (!hh || !hh.tts || !hh.tts.ready) {
            setState('idle', 'Speech is unavailable right now — the reply is shown above.');
            return resolve();
          }
          speak(text).then(resolve);
        }).catch(function () { setState('idle', 'Speech is unavailable right now — the reply is shown above.'); resolve(); });
        return;
      }
      stopSpeaking(false);
      var token = S.speakToken;
      if (!S.play) {
        S.play = new (window.AudioContext || window.webkitAudioContext)();
        S.analyser = S.play.createAnalyser(); S.analyser.fftSize = 512; S.analyser.connect(S.play.destination);
      }
      var sr = 24000, rtf = 1.4, queue = [], buffered = 0, started = false, done = false, t0 = performance.now(), firstAt = 0;
      var estSec = Math.max(1.5, text.length / 14);
      S.t.underruns = 0; S.playHead = 0;
      setState('speaking', 'Finding the words…');
      function openWs() {
      var ws = new WebSocket(WS_SVC + '/tts?text=' + encodeURIComponent(text));
      ws.binaryType = 'arraybuffer'; S.ws = ws;

      function schedule(f32) {
        var b = S.play.createBuffer(1, f32.length, sr); b.copyToChannel(f32, 0);
        var s = S.play.createBufferSource(); s.buffer = b; s.connect(S.analyser);
        var at = Math.max(S.play.currentTime + 0.04, S.playHead);
        if (started && S.playHead > 0 && at > S.playHead + 0.02) S.t.underruns = (S.t.underruns || 0) + 1;  // audible gap
        s.start(at); S.playHead = at + b.duration; S.sources.push(s);
        s.onended = function () { S.sources = S.sources.filter(function (x) { return x !== s; }); maybeEnd(); };
      }
      function flush() { started = true; S.t.playbackStart = Math.round(performance.now() - t0); setState('speaking'); animate(token); queue.forEach(schedule); queue = []; }
      function maybeEnd() {
        if (token !== S.speakToken) return resolve();
        if (done && !S.sources.length && !queue.length) {
          if (S.raf) cancelAnimationFrame(S.raf);
          setState('idle'); resolve();
          if (S.open && S.autoListen && h.stt && h.stt.ready) setTimeout(function () { if (S.state === 'idle' && S.open && !S.hiddenForUrgent) startListening(); }, 450);
        }
      }
      ws.onmessage = function (ev) {
        if (token !== S.speakToken) return;
        if (typeof ev.data === 'string') {
          var m = {}; try { m = JSON.parse(ev.data); } catch (_) {}
          if (m.type === 'meta') { sr = m.sample_rate || 24000; rtf = Math.min(3, Math.max(0.5, m.rtf_hint || 1.4)); }
          if (m.type === 'done') { S.t.tts = m; done = true; if (!started) flush(); maybeEnd(); }
          if (m.type === 'error') { done = true; setState('idle', 'Speech is unavailable right now — the reply is shown above.'); resolve(); }
          return;
        }
        var i16 = new Int16Array(ev.data), f = new Float32Array(i16.length);
        for (var i = 0; i < i16.length; i++) f[i] = i16[i] / 32768;
        if (!firstAt) { firstAt = performance.now(); S.t.firstAudio = Math.round(firstAt - t0); }
        buffered += f.length / sr;
        if (started) { schedule(f); return; }
        queue.push(f);
        // Jitter buffer: on a base M4 generation runs a bit slower than real time
        // (RTF ~1.1-1.5), so hold back just enough audio (based on the server's
        // last measured RTF and the reply length) that playback doesn't stutter.
        // Cap the hold-back so we start hearing the reply within ~0.8s of first audio
        // even when RTF is high — otherwise a barge-in / popup can kill the socket
        // before playback ever starts, and it feels like "it's not talking".
        var need = rtf <= 1.05 ? 0.15 : Math.min(0.85, estSec * (1 - 1 / rtf) + 0.2);
        if (buffered >= need) flush();
      };
      ws.onclose = function () { if (token !== S.speakToken) return; done = true; if (!started && queue.length) flush(); maybeEnd(); };
      ws.onerror = function () { if (token !== S.speakToken) return; done = true; setState('idle', 'Speech is unavailable right now — the reply is shown above.'); resolve(); };
      }
      var ready = (S.play.state === 'suspended') ? S.play.resume() : Promise.resolve();
      Promise.resolve(ready).catch(function () {}).then(openWs);
    });
  }

  function animate(token) {
    var data = new Uint8Array(S.analyser.fftSize), orb = $('shv-orb');
    (function loop() {
      if (token !== S.speakToken) return;
      S.analyser.getByteTimeDomainData(data);
      var s = 0; for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; s += v * v; }
      orb.style.setProperty('--lvl', Math.min(1, Math.sqrt(s / data.length) * 5).toFixed(3));
      S.raf = requestAnimationFrame(loop);
    })();
  }

  // ------------------------------------------------------------------ boot
  function boot() {
    if (!document.getElementById('chatInput') || !A()) return setTimeout(boot, 300);
    build(); hookApp();
    window.SHVoice = { open: openVoice, close: close, speak: speak, turn: turn, state: S };
    if (/[?&]voice=open\b/.test(location.search)) openVoice();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
