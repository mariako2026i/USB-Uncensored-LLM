window.personalMode = true;

(() => {
  const commands = new Map([
    ['покажи систему', 'system'],
    ['открой проект', 'project'],
    ['открой консоль', 'console'],
    ['покажи статус проекта', 'status'],
    ['разверни проект', 'deploy'],
  ]);
  const mic = document.getElementById('personal-mic');
  const button = document.getElementById('personal-command');
  const input = document.getElementById('msg-inp');
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
  if (synthesis && window.SpeechSynthesisUtterance) {
    const preference = 'usb-ai-speak-replies';
    let enabled = true;
    let active = null;
    try { enabled = localStorage.getItem(preference) !== 'off'; } catch {}

    function updateVoiceButton() {
      voiceButton.textContent = enabled ? '🔊' : '🔇';
      voiceButton.setAttribute('aria-label', 'Озвучивание ответов');
      voiceButton.setAttribute('aria-pressed', String(enabled));
      voiceButton.title = enabled ? 'Озвучивание включено' : 'Озвучивание выключено';
    }

    function stopVoice() {
      active = null;
      synthesis.cancel();
    }

    function startVoice() {
      stopVoice();
      if (!enabled) return;
      let pending = '';
      let inCodeBlock = false;
      const session = {
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
        const line = new SpeechSynthesisUtterance(text);
        const lang = /[А-Яа-яЁё]/.test(text) ? 'ru' : 'en';
        line.lang = lang === 'ru' ? 'ru-RU' : 'en-US';
        const voice = synthesis.getVoices().find(
          (candidate) => candidate.localService && candidate.lang.toLowerCase().split(/[-_]/)[0] === lang,
        );
        if (voice) line.voice = voice;
        line.onerror = (event) => {
          if (active === session && !['canceled', 'interrupted'].includes(event.error)) {
            stopVoice();
            say('Не удалось озвучить ответ. Проверьте доступность голоса в браузере.');
          }
        };
        synthesis.speak(line);
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

    window.personalVoice = {start: startVoice, stop: stopVoice};
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

  async function run(text) {
    const phrase = text.trim().toLowerCase().replace(/[.!?]+$/, '');
    const action = commands.get(phrase);
    if (!action) return false;
    if (!window.confirm('Выполнить команду «' + phrase + '»?')) return true;
    say('Выполняется…');
    try {
      const response = await fetch('/api/personal/action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action}),
      });
      const data = await response.json();
      say(data.exit_code === undefined ? data.output : 'Код выхода ' + data.exit_code + '\n' + data.output);
    } catch {
      say('Не удалось получить результат команды.');
    }
    return true;
  }

  button.hidden = false;
  button.addEventListener('click', async () => {
    const text = window.prompt('Команда:\n' + Array.from(commands.keys()).join('\n'));
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
      window.personalVoice?.stop();
      speech.start();
    } catch {
      say('Микрофон уже используется.');
    }
  });
})();
