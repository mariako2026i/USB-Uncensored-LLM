'use strict';

const $ = (id) => document.getElementById(id);
const connect = $('connect');
const input = $('message');
const mic = $('mic');
const command = $('command');
const status = $('status');
const messages = $('messages');
const storageKey = 'mira-android-session';
let code = '';
let busy = false;
let recording = null;
let playing = null;
try { code = sessionStorage.getItem(storageKey) || ''; } catch {}

function showChat(connected) {
  $('connection').hidden = connected;
  $('chat').hidden = !connected;
  $('disconnect').hidden = !connected;
}

async function request(path, body, contentType = 'application/json') {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + code, 'Content-Type': contentType},
    body,
  });
  if (response.ok) return response;
  if (response.status === 401) disconnect();
  const data = await response.json();
  throw new Error(data.error || 'Запрос не выполнен.');
}

async function verify() {
  await request('/api/connect');
  try { sessionStorage.setItem(storageKey, code); } catch {}
  showChat(true);
  status.textContent = 'Ноутбук подключён.';
}

function disconnect() {
  code = '';
  try { sessionStorage.removeItem(storageKey); } catch {}
  if (recording) releaseRecording(recording);
  playing?.pause();
  playing = null;
  messages.replaceChildren();
  showChat(false);
  status.textContent = 'Сеанс завершён.';
}

function addMessage(role, text) {
  const message = document.createElement('article');
  message.className = role;
  const title = document.createElement('strong');
  title.textContent = role === 'user' ? 'Вы' : 'Мира';
  const body = document.createElement('p');
  body.textContent = text;
  message.append(title, body);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function withBusy(value) {
  busy = value;
  mic.disabled = value;
  command.querySelector('button[type=submit]').disabled = value;
}

async function send(text) {
  if (busy || recording || !text.trim()) return;
  const sessionCode = code;
  addMessage('user', text);
  input.value = '';
  withBusy(true);
  status.textContent = 'Ноутбук выполняет запрос…';
  try {
    const response = await request('/api/message', JSON.stringify({text}));
    const {text: answer} = await response.json();
    if (sessionCode !== code) return;
    const reply = addMessage('assistant', answer);
    const listen = document.createElement('button');
    listen.type = 'button';
    listen.textContent = answer.length > 300 ? 'Озвучить начало' : 'Озвучить';
    listen.addEventListener('click', () => listenTo(answer));
    reply.append(listen);
    status.textContent = '';
  } catch (error) {
    status.textContent = error instanceof TypeError ? 'Нет связи с ноутбуком. Проверьте, запущена ли Мира.' : error.message;
  } finally {
    withBusy(false);
  }
}

async function listenTo(text) {
  const sessionCode = code;
  playing?.pause();
  const spoken = text.replace(/```[\s\S]*?```/g, '').trim().slice(0, 300);
  if (!spoken) return;
  let url;
  try {
    const response = await request('/api/speak', JSON.stringify({text: spoken}));
    const audio = await response.blob();
    if (sessionCode !== code) return;
    url = URL.createObjectURL(audio);
    playing = new Audio(url);
    playing.controls = true;
    playing.addEventListener('ended', () => URL.revokeObjectURL(url), {once: true});
    try {
      await playing.play();
    } catch {
      const reply = messages.lastElementChild;
      reply?.append(playing);
    }
  } catch (error) {
    if (url) URL.revokeObjectURL(url);
    status.textContent = error.message;
  }
}

function makeWav(chunks) {
  const count = chunks.reduce((size, part) => size + part.length, 0);
  const buffer = new DataView(new ArrayBuffer(44 + count * 2));
  for (const [offset, tag] of [[0, 'RIFF'], [8, 'WAVE'], [12, 'fmt '], [36, 'data']]) {
    for (let i = 0; i < tag.length; i++) buffer.setUint8(offset + i, tag.charCodeAt(i));
  }
  [[4, 36 + count * 2], [16, 16], [24, 16000], [28, 32000], [40, count * 2]]
    .forEach(([offset, value]) => buffer.setUint32(offset, value, true));
  [[20, 1], [22, 1], [32, 2], [34, 16]]
    .forEach(([offset, value]) => buffer.setUint16(offset, value, true));
  let offset = 44;
  for (const part of chunks) {
    for (const sample of part) {
      buffer.setInt16(offset, Math.min(1, Math.max(-1, sample)) * 32767, true);
      offset += 2;
    }
  }
  return buffer.buffer;
}

function releaseRecording(session) {
  recording = null;
  clearTimeout(session.timer);
  session.processor?.disconnect();
  session.stream?.getTracks().forEach((track) => track.stop());
  session.context?.close().catch(() => {});
  mic.textContent = 'Микрофон';
  mic.setAttribute('aria-pressed', 'false');
}

async function stopRecording(session) {
  releaseRecording(session);
  if (!session.chunks.length) return;
  const sessionCode = code;
  withBusy(true);
  status.textContent = 'Ноутбук распознаёт речь…';
  try {
    const response = await request('/api/transcribe', makeWav(session.chunks), 'audio/wav');
    const {text} = await response.json();
    if (sessionCode !== code) return;
    input.value = text;
    status.textContent = text ? 'Проверьте текст и нажмите «Отправить».' : 'Речь не распознана. Попробуйте ещё раз.';
  } catch (error) {
    status.textContent = error instanceof TypeError ? 'Нет связи с ноутбуком.' : error.message;
  } finally {
    withBusy(false);
  }
}

async function startRecording() {
  if (!window.isSecureContext || !navigator.mediaDevices) {
    status.textContent = 'Для микрофона откройте приложение по HTTPS.';
    return;
  }
  const session = {chunks: []};
  recording = session;
  mic.textContent = 'Завершить запись';
  mic.setAttribute('aria-pressed', 'true');
  try {
    session.context = new AudioContext({sampleRate: 16000});
    await session.context.resume();
    if (session.context.sampleRate !== 16000) throw new Error('Браузер не поддерживает запись на 16 кГц.');
    const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1}});
    if (recording !== session) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    session.stream = stream;
    const processor = session.context.createScriptProcessor(2048, 1, 1);
    session.processor = processor;
    processor.onaudioprocess = (event) => {
      if (recording === session) session.chunks.push(event.inputBuffer.getChannelData(0).slice());
    };
    session.context.createMediaStreamSource(stream).connect(processor);
    processor.connect(session.context.destination);
    session.timer = setTimeout(() => stopRecording(session), 10000);
    status.textContent = 'Говорите. Нажмите ещё раз, чтобы завершить запись.';
  } catch (error) {
    if (recording === session) releaseRecording(session);
    status.textContent = 'Микрофон недоступен: ' + error.message;
  }
}

connect.addEventListener('submit', (event) => {
  event.preventDefault();
  code = $('code').value.trim();
  $('code').value = '';
  verify().catch((error) => { status.textContent = error.message; });
});
$('disconnect').addEventListener('click', disconnect);
command.addEventListener('submit', (event) => {
  event.preventDefault();
  send(input.value.trim());
});
mic.addEventListener('click', () => recording ? stopRecording(recording) : startRecording());
window.addEventListener('pagehide', () => { if (recording) releaseRecording(recording); });
if (code) verify().catch((error) => { status.textContent = error.message; });
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
