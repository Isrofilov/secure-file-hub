// Shared helpers for every page: config, toasts, confirmation dialog, theme and language menus.
const SFH = (() => {
  const config = JSON.parse(document.getElementById('i18n').textContent);

  const format = (template, params = {}) =>
    template.replace(/%\((\w+)\)[sd]/g, (_, key) => (key in params ? params[key] : ''));

  const formatSize = (bytes, units) => {
    let value = bytes;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i += 1;
    }
    return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`;
  };

  const icon = (name) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `${config.icons}#${name}`);
    svg.append(use);
    return svg;
  };

  const dismiss = (toast) => {
    toast.classList.add('is-leaving');
    setTimeout(() => toast.remove(), 220);
  };

  const toast = (message, type = 'info') => {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const text = document.createElement('span');
    text.textContent = message;
    el.append(icon({ success: 'success', error: 'error', warning: 'warning' }[type] || 'info'), text);
    document.getElementById('toasts').append(el);
    el.addEventListener('click', () => dismiss(el));
    setTimeout(() => dismiss(el), type === 'error' ? 8000 : 4500);
  };

  const confirm = ({ title, body, items = [], ok }) => new Promise((resolve) => {
    const dialog = document.getElementById('confirm-dialog');
    dialog.querySelector('[data-slot="title"]').textContent = title;
    const content = dialog.querySelector('[data-slot="body"]');
    content.replaceChildren();
    if (items.length) {
      const list = document.createElement('ul');
      items.slice(0, 50).forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        list.append(li);
      });
      if (items.length > 50) list.append(Object.assign(document.createElement('li'), { textContent: '…' }));
      content.append(list);
    }
    if (body) content.append(Object.assign(document.createElement('p'), { className: 'muted', textContent: body }));
    if (ok) dialog.querySelector('[data-slot="ok"]').textContent = ok;
    dialog.returnValue = '';
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
    dialog.showModal();
    dialog.querySelector('[value="cancel"]').focus();
  });

  const request = async (url, { method = 'POST', body } = {}) => {
    let response;
    try {
      response = await fetch(url, {
        method,
        body,
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': config.csrf, 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
    } catch (e) {
      throw new Error(config.strings.networkError);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || config.strings.error);
    return data;
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast(config.strings.copied, 'success');
      return true;
    } catch (e) {
      toast(config.strings.copyFailed, 'warning');
      return false;
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.toast[data-autohide]').forEach((el) => {
      el.addEventListener('click', () => dismiss(el));
      setTimeout(() => dismiss(el), el.classList.contains('toast-error') ? 8000 : 4500);
    });

    // Theme: auto -> light -> dark -> auto
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.addEventListener('click', () => {
        const root = document.documentElement;
        const next = { undefined: 'light', light: 'dark', dark: undefined }[root.dataset.theme];
        try {
          if (next) localStorage.setItem('theme', next); else localStorage.removeItem('theme');
        } catch (e) { /* storage unavailable */ }
        if (next) root.dataset.theme = next; else delete root.dataset.theme;
      });
    });

    // Close open menus on outside click or Escape
    document.addEventListener('click', (event) => {
      document.querySelectorAll('details.menu[open]').forEach((menu) => {
        if (!menu.contains(event.target)) menu.open = false;
      });
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') document.querySelectorAll('details.menu[open]').forEach((m) => { m.open = false; });
    });

    document.querySelectorAll('[data-action="back"]').forEach((button) => {
      button.addEventListener('click', () => history.back());
    });
  });

  return { config, format, formatSize, icon, toast, confirm, request, copy };
})();
