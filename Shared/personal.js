window.personalMode = true;
window.parseMiraCodex = (text) => {
  const command = text.trim().replace(/^["«„“]|["»”]$/g, '').trim();
  const prefix = /^(?:[мн]ира[\s,!.?—:;-]+)?(?:\/codex|спроси\s+у\s+кодекс?а)(?=$|[\s,.!?—:;-])[\s,.!?—:;-]*/i;
  const match = prefix.exec(command);
  return match ? command.slice(match[0].length).trim() : null;
};

(() => {
  const commands = new Map([
    ['покажи систему', 'system'],
    ['открой проект', 'project'],
    ['открой консоль', 'console'],
    ['покажи статус проекта', 'status'],
    ['открой github', 'github'],
    ['открой гитхаб', 'github'],
    ['покажи задачи github', 'github-issues'],
    ['покажи задачи гитхаб', 'github-issues'],
    ['открой firstvds', 'ssh'],
    ['открой first vds', 'ssh'],
    ['открой консоль сервера', 'ssh'],
    ['открой youtube', 'youtube'],
    ['открой ютуб', 'youtube'],
    ['открой crm', 'crm'],
    ['открой црм', 'crm'],
    ['открой почту', 'mail'],
    ['открой gmail', 'gmail'],
    ['открой outlook', 'outlook'],
    ['открой яндекс почту', 'yandex-mail'],
  ]);
  const mic = document.getElementById('personal-mic');
  const button = document.getElementById('personal-command');
  const input = document.getElementById('msg-inp');
  input.placeholder = 'Сообщение или /codex вопрос';
  document.querySelector('.disc').textContent =
    'Ответы могут содержать ошибки. Облачные модели получают историю чата после подтверждения.';
  const output = document.createElement('pre');
  output.hidden = true;
  output.style.cssText = 'white-space:pre-wrap;max-height:10rem;overflow:auto';
  input.closest('.text-row').after(output);
  const say = (message) => {
    output.hidden = false;
    output.textContent = message;
  };

  const voiceButton = document.getElementById('personal-voice');
  const synthesis = window.speechSynthesis;
  if (voiceButton) {
    const preference = 'usb-ai-speak-replies';
    let enabled = true;
    let active = null;
    let piperAvailable = true;
    try { enabled = localStorage.getItem(preference) !== 'off'; } catch {}

    function updateVoiceButton() {
      voiceButton.textContent = enabled ? '🔊' : '🔇';
      voiceButton.setAttribute('aria-label', 'Озвучивание ответов');
      voiceButton.setAttribute('aria-pressed', String(enabled));
      voiceButton.title = enabled ? 'Озвучивание включено' : 'Озвучивание выключено';
    }

    function stopVoice() {
      active?.cancel();
      active = null;
      synthesis?.cancel();
    }

    function startVoice() {
      stopVoice();
      if (!enabled) return;
      let pending = '';
      let inCodeBlock = false;
      const abort = new AbortController();
      let queue = Promise.resolve();
      let waiting = 0;
      const session = {
        cancel() { abort.abort(); },
        playing() { return waiting > 0; },
        append(text) {
          if (active !== session) return;
          pending += text;
          flush(false);
        },
        finish() {
          if (active === session) flush(true);
        },
        stop() {
          if (active === session) stopVoice();
        },
      };

      function speak(chunk) {
        const parts = chunk.split('```');
        const prose = [];
        for (const [index, part] of parts.entries()) {
          if (index) inCodeBlock = !inCodeBlock;
          if (!inCodeBlock) prose.push(part);
        }
        const text = prose.join(' ').replace(/[*#_`]+/g, '').trim();
        if (!text) return;
        waiting++;
        queue = queue.then(async () => {
          if (abort.signal.aborted) return;
          const russian = /[А-Яа-яЁё]/.test(text);
          if (russian && piperAvailable && await playPiper(text)) return;
          if (!abort.signal.aborted) await playBrowser(text, russian);
        }).catch(() => {
          if (active === session) say('Не удалось озвучить ответ.');
        }).finally(() => { waiting--; });
      }

      async function playPiper(text) {
        try {
          const response = await fetch('/api/personal/speak', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text}), signal: abort.signal,
          });
          if (response.status === 404) piperAvailable = false;
          if (!response.ok) return false;
          const wav = await response.blob();
          if (abort.signal.aborted) return true;
          const url = URL.createObjectURL(wav);
          try {
            const audio = new Audio(url);
            let stop;
            try {
              await new Promise((resolve, reject) => {
                stop = () => { audio.pause(); resolve(); };
                abort.signal.addEventListener('abort', stop, {once: true});
                audio.onended = resolve;
                audio.onerror = reject;
                audio.play().catch(reject);
              });
            } finally {
              abort.signal.removeEventListener('abort', stop);
            }
          } finally {
            URL.revokeObjectURL(url);
          }
          return true;
        } catch {
          return false;
        }
      }

      function playBrowser(text, russian) {
        if (!synthesis || !window.SpeechSynthesisUtterance) {
          throw new Error('No browser speech synthesis');
        }
        return new Promise((resolve, reject) => {
          const line = new SpeechSynthesisUtterance(text);
          const lang = russian ? 'ru' : 'en';
          line.lang = russian ? 'ru-RU' : 'en-US';
          const voice = synthesis.getVoices().find(
            (candidate) => candidate.localService && candidate.lang.toLowerCase().split(/[-_]/)[0] === lang,
          );
          if (voice) line.voice = voice;
          line.onend = resolve;
          line.onerror = (event) => {
            if (['canceled', 'interrupted'].includes(event.error)) resolve();
            else reject(new Error(event.error));
          };
          synthesis.speak(line);
        });
      }

      function flush(final) {
        while (pending) {
          const limit = 180;
          const head = pending.slice(0, limit + 1);
          const boundary = /[.!?…](?:["»”])?\s|\n/.exec(head);
          let end = boundary ? boundary.index + boundary[0].length : 0;
          if (!end && pending.length > limit) {
            const space = head.lastIndexOf(' ');
            end = space >= limit / 2 ? space + 1 : limit;
          }
          if (!end) {
            if (!final) break;
            end = pending.length;
          }
          // Keep a Markdown fence together when the length limit splits a line.
          while (end < pending.length && pending[end - 1] === '`' && pending[end] === '`') end++;
          const chunk = pending.slice(0, end);
          pending = pending.slice(end);
          speak(chunk);
        }
      }

      active = session;
      return session;
    }

    window.personalVoice = {start: startVoice, stop: stopVoice, playing: () => active?.playing()};
    voiceButton.classList.add('ib2');
    voiceButton.hidden = false;
    updateVoiceButton();
    voiceButton.addEventListener('click', () => {
      enabled = !enabled;
      if (!enabled) stopVoice();
      try { localStorage.setItem(preference, enabled ? 'on' : 'off'); } catch {}
      updateVoiceButton();
    });
  }

  let githubIssue = '';
  let pendingDelete = null;

  async function runAction(action, argument) {
    say('Выполняется…');
    if (!['confirm-delete', 'cancel-delete', 'prepare-delete'].includes(action)) pendingDelete = null;
    try {
      const response = await fetch('/api/personal/action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action, argument}),
      });
      const data = await response.json();
      if (action === 'prepare-delete') {
        pendingDelete = data.delete_token ? {token: data.delete_token, expires: Date.now() + 30000} : null;
      }
      if (action === 'github-issue') githubIssue = data.exit_code === 0 ? data.output : '';
      say(data.exit_code === undefined ? data.output : 'Код выхода ' + data.exit_code + '\n' + data.output);
    } catch {
      say('Не удалось получить результат команды.');
    }
  }

  window.parseMiraTerminal = (text) => /^(\/(?:ps|ssh))(?=$|\s)[\t ]*([\s\S]*)$/i.exec(text.trim());
  window.runMiraTerminal = async (match) => {
    const argument = match[2].trim();
    if (!argument) {
      say('Укажите точную команду после /ps или /ssh.');
      return;
    }
    await runAction(match[1].toLowerCase() === '/ps' ? 'powershell' : 'ssh-command', argument);
  };

  async function run(text) {
    const phrase = text.trim().toLowerCase().replace(/[.!?]+$/, '');
    const action = commands.get(phrase);
    if (action) {
      if (window.confirm('Выполнить «' + phrase + '»?')) await runAction(action);
      return true;
    }

    const removal = /^(?:подготовь удаление файла|удали файл)\s+(.+)$/is.exec(text.trim());
    if (removal) {
      pendingDelete = null;
      await runAction('prepare-delete', removal[1]);
      return true;
    }

    const site = /^открой\s+сайт\s+(.+)$/i.exec(text.trim());
    const issue = /^покажи\s+(?:задачу|ишью)(?:\s+номер)?\s+(\d+)$/.exec(phrase);
    if (site) {
      let address = site[1].trim().replace(/\s+точка\s+/gi, '.');
      if (!/^https?:\/\//i.test(address)) address = 'https://' + address;
      if (window.confirm('Открыть ' + address + '?')) await runAction('website', address);
      return true;
    }
    if (issue) {
      await runAction('github-issue', issue[1]);
      return true;
    }

    const fromBlock = /^(?:подготовь|выполни) команду (?:из (ответа|задачи) )?(?:для|в) (powershell|пауэршелл|консоли|firstvds|first vds|на сервере)$/.exec(phrase);
    if (fromBlock) {
      const local = /^(?:powershell|пауэршелл|консоли)$/.test(fromBlock[2]);
      const reply = fromBlock[1] === 'задачи' ? githubIssue :
        getConv()?.msgs.findLast((msg) => msg.role === 'assistant' && msg.content)?.content || '';
      const blocks = [...reply.matchAll(/^```([\w-]*)[ \t]*\r?\n([\s\S]*?)^```[ \t]*$/gm)];
      const language = local ? /^(?:powershell|pwsh|ps1)$/i : /^(?:bash|sh|shell)$/i;
      const matching = blocks.filter((block) => language.test(block[1]));
      if (matching.length !== 1) {
        say('Нужен ровно один блок команды ' + (local ? 'PowerShell' : 'Bash') + ' в выбранном источнике.');
        return true;
      }
      await runAction(local ? 'powershell' : 'ssh-command', matching[0][2].trim());
      return true;
    }
    return false;
  }

  const miraButton = document.createElement('button');
  miraButton.type = 'button';
  miraButton.textContent = 'Мира';
  miraButton.title = 'Ожидание имени «Мира»';
  miraButton.style.cssText = 'padding:4px 8px;border:1px solid var(--t3);border-radius:8px;background:transparent;color:inherit';
  miraButton.setAttribute('aria-pressed', 'false');
  button.before(miraButton);
  let mira = null;

  function setCodexMode(session, enabled) {
    session.codexMode = enabled;
    miraButton.textContent = enabled ? 'Мира · Кодекс' : 'Мира';
  }

  function stopMira() {
    const session = mira;
    if (!session) return;
    mira = null;
    setCodexMode(session, false);
    pendingDelete = null;
    session.abort.abort();
    session.processor?.disconnect();
    session.stream?.getTracks().forEach((track) => track.stop());
    session.context?.close().catch(() => {});
    miraButton.setAttribute('aria-pressed', 'false');
    miraButton.style.background = 'transparent';
  }

  function toWav(chunks) {
    const samples = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const data = new DataView(new ArrayBuffer(44 + samples * 2));
    function tag(offset, text) {
      for (let i = 0; i < text.length; i++) data.setUint8(offset + i, text.charCodeAt(i));
    }
    tag(0, 'RIFF');
    data.setUint32(4, 36 + samples * 2, true);
    tag(8, 'WAVE');
    tag(12, 'fmt ');
    data.setUint32(16, 16, true);
    data.setUint16(20, 1, true);
    data.setUint16(22, 1, true);
    data.setUint32(24, 16000, true);
    data.setUint32(28, 32000, true);
    data.setUint16(32, 2, true);
    data.setUint16(34, 16, true);
    tag(36, 'data');
    data.setUint32(40, samples * 2, true);
    let offset = 44;
    for (const chunk of chunks) {
      for (const sample of chunk) {
        data.setInt16(offset, Math.max(-1, Math.min(1, sample)) * 32767, true);
        offset += 2;
      }
    }
    return data.buffer;
  }

  function replyInProgress() {
    return S.streaming || window.personalVoice?.playing() || window.speechSynthesis?.speaking;
  }

  async function recognizeMira(session, chunks, interruptOnly) {
    session.busy = true;
    try {
      const endpoint = interruptOnly ? '/api/personal/transcribe?interrupt=1' : '/api/personal/transcribe';
      const response = await fetch(endpoint, {
        method: 'POST', headers: {'Content-Type': 'audio/wav'},
        body: toWav(chunks), signal: session.abort.signal,
      });
      const result = await response.json();
      if (session !== mira) return;
      if (!response.ok) throw new Error(result.error);
      const text = result.text.trim().replace(/^["«„“]|["»”]$/g, '').trim();
      const wake = /^[мн]ира(?=$|[\s,!.?—:;-])[\s,!.?—:;-]*/i.exec(text);
      const stop = /^(?:мира|нира|мера)[\s,!.?—:;-]+(?:стоп|стой|столб)[.!?…]*$/i.test(text);
      if (stop && (wake || interruptOnly || replyInProgress())) {
        session.reply = null;
        pendingDelete = null;
        stopStream();
        session.until = Date.now() + 20000;
        say('Остановлено. Скажите исправленный вопрос.');
        return;
      }
      if (interruptOnly || replyInProgress()) return;
      const decision = /^(да|нет)[.!?…]*$/i.exec(wake ? text.slice(wake[0].length) : text);
      if (pendingDelete && decision) {
        const pending = pendingDelete;
        pendingDelete = null;
        const approve = decision[1].toLowerCase() === 'да' && Date.now() < pending.expires;
        await runAction(approve ? 'confirm-delete' : 'cancel-delete', pending.token);
        return;
      }
      if (!wake && (!session.until || Date.now() >= session.until)) return;
      pendingDelete = null;
      let question = wake ? text.slice(wake[0].length) : text;
      if (/^(стоп|закончи разговор)[.!?]*$/i.test(question)) {
        session.until = 0;
        setCodexMode(session, false);
        say('Скажите «Мира», чтобы начать разговор.');
        return;
      }
      session.until = Date.now() + 20000;
      if (/^(?:вернись в локальный режим|локально)[.!?…]*$/i.test(question)) {
        setCodexMode(session, false);
        say('Локальный режим включён.');
        return;
      }
      if (!question) {
        say('Слушаю. Задайте вопрос.');
        const acknowledgement = window.personalVoice?.start();
        acknowledgement?.append('Слушаю.');
        acknowledgement?.finish();
        return;
      }
      const codexQuestion = window.parseMiraCodex(question);
      if (codexQuestion !== null) {
        setCodexMode(session, true);
        question = codexQuestion;
        if (!question) {
          say('Режим Кодекса включён. Задайте вопрос.');
          const prompt = window.personalVoice?.start();
          prompt?.append('Какой вопрос передать Кодексу?');
          prompt?.finish();
          return;
        }
      }
      const codex = session.codexMode;
      if (codexQuestion === null && (!codex || wake) && await run(question)) return;
      if (session !== mira) return;
      if (!codex && (!S.engineReady || !S.model)) {
        say('Выберите модель в чате.');
        return;
      }
      if (S.streaming || input.value.trim() || S.attachments.length) {
        say('Завершите текущий ответ или очистите черновик и повторите вопрос.');
        return;
      }
      say(codex ? 'Спрашиваю Кодекса…' : 'Мира отвечает…');
      const reply = sendMsg(question, {codex});
      session.reply = reply;
      reply.then(() => {
        if (session !== mira || session.reply !== reply) return;
        session.reply = null;
        session.until = Date.now() + 20000;
        say(codex ? 'Режим Кодекса. Задайте следующий вопрос.'
                  : 'Задайте следующий вопрос или скажите «Мира, стоп».');
      }).catch(() => {
        if (session === mira && session.reply === reply) {
          session.reply = null;
          say('Не удалось получить ответ. Повторите вопрос.');
        }
      });
    } catch (error) {
      if (session !== mira) return;
      stopMira();
      say(error.message || 'Не удалось распознать речь.');
    } finally {
      session.busy = false;
    }
  }

  miraButton.addEventListener('click', async () => {
    if (mira) {
      stopMira();
      say('Ожидание имени выключено.');
      return;
    }
    const session = {abort: new AbortController(), until: 0, codexMode: false, busy: false};
    mira = session;
    miraButton.setAttribute('aria-pressed', 'true');
    miraButton.style.background = 'var(--grad1)';
    let chunks = [];
    let preroll = [];
    let voiced = 0;
    let silence = 0;
    let interruptOnly = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true},
      });
      if (session !== mira) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      session.stream = stream;
      const context = new AudioContext({sampleRate: 16000});
      session.context = context;
      await context.resume();
      if (session !== mira) return;
      if (context.sampleRate !== 16000) throw new Error('Браузер не поддерживает частоту 16 кГц.');
      const processor = context.createScriptProcessor(2048, 1, 1);
      session.processor = processor;
      processor.onaudioprocess = (event) => {
        const replying = replyInProgress();
        if (replying && session.until) session.until = Date.now() + 20000;
        if (session !== mira || session.busy) {
          chunks = [];
          preroll = [];
          voiced = silence = 0;
          interruptOnly = false;
          return;
        }
        const samples = event.inputBuffer.getChannelData(0);
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        const speaking = Math.sqrt(energy / samples.length) >= 0.012;
        if (!chunks.length && !speaking) {
          preroll.push(samples.slice());
          if (preroll.length > 2) preroll.shift();
          return;
        }
        if (!chunks.length) {
          chunks = preroll;
          preroll = [];
        }
        interruptOnly ||= replying;
        chunks.push(samples.slice());
        if (speaking) voiced++;
        silence = speaking ? 0 : silence + 1;
        const silenceLimit = interruptOnly ? 3 : 6;
        const clipLimit = interruptOnly ? 20 : 90;
        if (silence >= silenceLimit || chunks.length >= clipLimit) {
          if (voiced >= 2) recognizeMira(session, chunks, interruptOnly);
          chunks = [];
          voiced = silence = 0;
          interruptOnly = false;
        }
      };
      context.createMediaStreamSource(stream).connect(processor);
      processor.connect(context.destination);
      say('Скажите «Мира» или «Мира, привет».');
    } catch (error) {
      if (session !== mira) return;
      stopMira();
      say('Не удалось включить микрофон: ' + error.message);
    }
  });
  window.addEventListener('pagehide', stopMira);

  button.hidden = false;
  button.addEventListener('click', async () => {
    const text = window.prompt('Команда:\n' + Array.from(commands.keys()).join('\n') +
      '\nоткрой сайт example.com\nпокажи задачу 12\nподготовь команду из ответа для PowerShell\nподготовь удаление файла имя.txt');
    if (text && !(await run(text))) say('Команда не найдена.');
  });
  mic.hidden = false;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    mic.disabled = true;
    mic.title = 'Распознавание речи недоступно в этом браузере';
    return;
  }

  const speech = new Recognition();
  speech.lang = 'ru-RU';
  speech.onstart = () => { mic.disabled = true; say('Слушаю…'); };
  speech.onend = () => { mic.disabled = false; };
  speech.onerror = (event) => say('Ошибка распознавания речи: ' + event.error);
  speech.onresult = async (event) => {
    const text = event.results[0][0].transcript;
    if (await run(text)) return;
    output.hidden = true;
    input.value = [input.value, text].filter(Boolean).join(' ');
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.focus();
  };
  mic.addEventListener('click', () => {
    try {
      stopMira();
      window.personalVoice?.stop();
      speech.start();
    } catch {
      say('Микрофон уже используется.');
    }
  });
})();
