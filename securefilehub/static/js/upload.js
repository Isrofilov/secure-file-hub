(() => {
  const form = document.getElementById('uploader');
  const t = JSON.parse(document.getElementById('upload-i18n').textContent);
  const input = document.getElementById('file-input');
  const dropzone = document.getElementById('dropzone');
  const queueBox = document.getElementById('queue');
  const queueList = document.getElementById('queue-list');
  const queueSummary = document.getElementById('queue-summary');
  const totalBar = document.getElementById('total-progress');
  const startButton = document.getElementById('start-upload');
  const cancelButton = document.getElementById('cancel-upload');
  const template = document.getElementById('queue-item');

  const url = form.dataset.url;
  const crossOrigin = new URL(url, window.location.href).origin !== window.location.origin;
  const maxBytes = Number(form.dataset.maxBytes) || 0;
  const size = (bytes) => SFH.formatSize(bytes, t.units);
  const kindIcon = (file) => {
    const type = file.type.split('/')[0];
    if (type === 'image') return 'image';
    if (type === 'video') return 'video';
    if (type === 'audio') return 'audio';
    if (file.type === 'application/pdf') return 'pdf';
    if (/zip|compressed|tar|rar|7z/.test(file.type)) return 'archive';
    if (type === 'text') return 'text';
    return 'file';
  };

  let queue = [];
  let running = false;
  let currentXhr = null;

  const setStatus = (item, state, text, percent) => {
    item.state = state;
    item.el.classList.toggle('is-done', state === 'done');
    item.el.classList.toggle('is-failed', state === 'failed');
    item.meta.textContent = `${size(item.file.size)} · ${text}`;
    if (percent !== undefined) item.bar.style.width = `${percent}%`;
  };

  const refresh = () => {
    queueBox.hidden = queue.length === 0;
    const bytes = queue.reduce((sum, item) => sum + item.file.size, 0);
    queueSummary.textContent = SFH.format(t.selected, { count: queue.length, size: size(bytes) });
    startButton.disabled = running || !queue.some((item) => item.state === 'waiting');
    cancelButton.hidden = !running;
    document.getElementById('queue-clear').hidden = running;
  };

  const updateTotal = () => {
    const total = queue.reduce((sum, item) => sum + item.file.size, 0) || 1;
    const sent = queue.reduce((sum, item) => sum + (item.sent || 0), 0);
    totalBar.style.width = `${Math.min(100, (sent / total) * 100)}%`;
  };

  const add = (files) => {
    Array.from(files).forEach((file) => {
      const el = template.content.firstElementChild.cloneNode(true);
      const item = { file, el, meta: el.querySelector('.queue-meta'), bar: el.querySelector('.progress-bar'), sent: 0 };
      el.querySelector('.queue-name').textContent = file.name;
      el.querySelector('.queue-name').title = file.name;
      const iconBox = el.querySelector('.queue-icon');
      if (file.type.startsWith('image/') && file.size < 25 * 1024 * 1024) {
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.alt = '';
        img.onload = () => URL.revokeObjectURL(img.src);
        img.onerror = () => img.replaceWith(SFH.icon('image'));
        iconBox.append(img);
      } else {
        iconBox.append(SFH.icon(kindIcon(file)));
      }
      el.querySelector('.queue-remove').addEventListener('click', () => {
        if (item.state === 'uploading') return;
        queue = queue.filter((other) => other !== item);
        el.remove();
        refresh();
      });
      if (maxBytes && file.size > maxBytes) setStatus(item, 'failed', t.tooLarge, 100);
      else setStatus(item, 'waiting', t.waiting, 0);
      queue.push(item);
      queueList.append(el);
    });
    refresh();
  };

  const send = (item) => new Promise((resolve) => {
    const body = new FormData();
    body.append('file', item.file, item.file.name);
    const xhr = new XMLHttpRequest();
    currentXhr = xhr;
    xhr.open('POST', url);
    xhr.responseType = 'json';
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    if (!crossOrigin) xhr.setRequestHeader('X-CSRF-Token', SFH.config.csrf);
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      item.sent = (event.loaded / event.total) * item.file.size;
      setStatus(item, 'uploading', SFH.format(t.uploading, { percent }), percent);
      updateTotal();
    });
    xhr.addEventListener('load', () => {
      const data = xhr.response || {};
      if (xhr.status === 200 && data.ok) {
        const saved = data.saved && data.saved[0];
        item.sent = item.file.size;
        setStatus(item, 'done', saved && saved !== item.file.name ? SFH.format(t.renamed, { name: saved }) : t.done, 100);
      } else {
        setStatus(item, 'failed', data.error || (xhr.status === 413 ? t.tooLarge : `${t.failed} (${xhr.status})`), 100);
      }
      resolve();
    });
    xhr.addEventListener('error', () => { setStatus(item, 'failed', SFH.config.strings.networkError, 100); resolve(); });
    xhr.addEventListener('abort', () => { setStatus(item, 'failed', t.canceled, 0); resolve(); });
    xhr.send(body);
  });

  const start = async () => {
    running = true;
    refresh();
    for (const item of queue) {
      if (!running) break;
      if (item.state === 'waiting') await send(item);
      updateTotal();
    }
    running = false;
    currentXhr = null;
    refresh();
    const failed = queue.some((item) => item.state === 'failed');
    if (failed) {
      SFH.toast(t.someFailed, 'error');
    } else {
      SFH.toast(t.allDone, 'success');
      setTimeout(() => { window.location.href = form.dataset.doneUrl; }, 900);
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!running) start();
  });

  cancelButton.addEventListener('click', () => {
    running = false;
    queue.filter((item) => item.state === 'waiting').forEach((item) => setStatus(item, 'failed', t.canceled, 0));
    currentXhr?.abort();
  });

  document.getElementById('queue-clear').addEventListener('click', () => {
    queue = [];
    queueList.replaceChildren();
    totalBar.style.width = '0';
    refresh();
  });

  input.addEventListener('change', () => {
    add(input.files);
    input.value = '';
  });

  // Files can be dropped anywhere on the page
  let dragDepth = 0;
  const hasFiles = (event) => Array.from(event.dataTransfer?.types || []).includes('Files');
  document.addEventListener('dragenter', (event) => {
    if (!hasFiles(event)) return;
    dragDepth += 1;
    dropzone.classList.add('is-over');
  });
  document.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) dropzone.classList.remove('is-over');
  });
  document.addEventListener('dragover', (event) => {
    if (hasFiles(event)) event.preventDefault();
  });
  document.addEventListener('drop', (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove('is-over');
    add(event.dataTransfer.files);
  });

  document.addEventListener('paste', (event) => {
    const files = event.clipboardData?.files;
    if (files && files.length) add(files);
  });

  window.addEventListener('beforeunload', (event) => {
    if (running) {
      event.preventDefault();
      event.returnValue = t.leave;
    }
  });
})();
