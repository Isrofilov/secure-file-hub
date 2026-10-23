(() => {
  const input = document.getElementById('code');
  const form = document.getElementById('login-form');
  const toggle = document.getElementById('toggle-mode');
  let backup = false;

  input.addEventListener('input', () => {
    if (backup) return;
    input.value = input.value.replace(/\D/g, '').slice(0, 6);
    if (input.value.length === 6) form.requestSubmit();
  });

  form.addEventListener('submit', () => {
    form.querySelector('button[type="submit"]').disabled = true;
  });

  toggle.addEventListener('click', () => {
    backup = !backup;
    input.value = '';
    input.classList.toggle('is-backup', backup);
    if (backup) {
      input.removeAttribute('pattern');
      input.maxLength = 64;
      input.inputMode = 'text';
      input.placeholder = '';
      input.autocomplete = 'off';
    } else {
      input.pattern = '[0-9]{6}';
      input.maxLength = 6;
      input.inputMode = 'numeric';
      input.placeholder = '000000';
      input.autocomplete = 'one-time-code';
    }
    document.querySelectorAll('[data-mode-text]').forEach((el) => {
      el.hidden = el.dataset.modeText !== (backup ? 'backup' : 'totp');
    });
    toggle.textContent = backup ? toggle.dataset.backup : toggle.dataset.totp;
    input.focus();
  });
})();
