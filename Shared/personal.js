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
      speech.start();
    } catch {
      say('Микрофон уже используется.');
    }
  });
})();
