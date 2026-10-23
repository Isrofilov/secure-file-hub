(() => {
  const form = document.getElementById('files');
  if (!form) return;

  const t = JSON.parse(document.getElementById('files-i18n').textContent);
  const list = document.getElementById('file-list');
  const search = document.getElementById('search');
  const summary = document.getElementById('files-summary');
  const noResults = document.getElementById('no-results');
  const selectAll = document.getElementById('select-all');
  const selectionBar = document.getElementById('selection-bar');
  const selectionCount = document.getElementById('selection-count');

  const items = () => Array.from(list.children);
  const visibleItems = () => items().filter((li) => !li.hidden);
  const checkbox = (li) => li.querySelector('input[type="checkbox"]');
  const selected = () => items().filter((li) => checkbox(li).checked);
  const downloadUrl = (li) => li.querySelector('.file-name').getAttribute('href');

  // -- summary, search, selection ------------------------------------------

  const updateSummary = () => {
    const all = items();
    const shown = visibleItems().length;
    const size = all.reduce((sum, li) => sum + Number(li.dataset.size), 0);
    let text = SFH.format(t.summary, { count: all.length, size: SFH.formatSize(size, t.units) });
    if (shown !== all.length) text = SFH.format(t.shown, { shown, count: all.length });
    summary.textContent = text;
    noResults.hidden = shown > 0 || all.length === 0;
    if (all.length === 0) window.location.reload();
  };

  const updateSelection = () => {
    const chosen = selected();
    items().forEach((li) => li.classList.toggle('is-selected', checkbox(li).checked));
    selectionBar.hidden = chosen.length === 0;
    selectionCount.textContent = SFH.format(t.selected, { count: chosen.length });
    const visible = visibleItems();
    const visibleChosen = visible.filter((li) => checkbox(li).checked).length;
    selectAll.checked = visible.length > 0 && visibleChosen === visible.length;
    selectAll.indeterminate = visibleChosen > 0 && visibleChosen < visible.length;
  };

  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    items().forEach((li) => {
      li.hidden = query !== '' && !li.dataset.name.toLocaleLowerCase().includes(query);
    });
    updateSummary();
    updateSelection();
  });

  selectAll.addEventListener('change', () => {
    visibleItems().forEach((li) => { checkbox(li).checked = selectAll.checked; });
    updateSelection();
  });

  list.addEventListener('change', (event) => {
    if (event.target.matches('input[type="checkbox"]')) updateSelection();
  });

  document.getElementById('clear-selection').addEventListener('click', () => {
    items().forEach((li) => { checkbox(li).checked = false; });
    updateSelection();
  });

  // Clicking the empty part of a row toggles its selection
  list.addEventListener('click', (event) => {
    const li = event.target.closest('.file');
    if (!li || event.target.closest('a, button, input, label')) return;
    const box = checkbox(li);
    box.checked = !box.checked;
    updateSelection();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && document.activeElement !== search && !document.querySelector('dialog[open]')) {
      event.preventDefault();
      search.focus();
    }
  });

  // -- view and sorting ------------------------------------------------------

  const viewButtons = document.querySelectorAll('[data-view]:not(form)');
  const setView = (view) => {
    form.dataset.view = view;
    viewButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === view)));
    try { localStorage.setItem('view', view); } catch (e) { /* storage unavailable */ }
  };
  viewButtons.forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  try {
    const saved = localStorage.getItem('view');
    if (saved === 'grid' || saved === 'list') setView(saved);
  } catch (e) { /* storage unavailable */ }

  const collator = new Intl.Collator(document.documentElement.lang, { numeric: true, sensitivity: 'base' });
  document.querySelectorAll('.sort').forEach((button) => {
    button.addEventListener('click', () => {
      const key = button.dataset.sort;
      const ascending = button.getAttribute('aria-sort') !== 'ascending';
      document.querySelectorAll('.sort').forEach((b) => b.removeAttribute('aria-sort'));
      button.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
      const sorted = items().sort((a, b) => {
        const result = key === 'name'
          ? collator.compare(a.dataset.name, b.dataset.name)
          : Number(a.dataset[key]) - Number(b.dataset[key]);
        return ascending ? result : -result;
      });
      list.append(...sorted);
    });
  });

  // Thumbnails that cannot be generated fall back to the file type icon
  list.addEventListener('error', (event) => {
    if (event.target.tagName === 'IMG') event.target.remove();
  }, true);

  // -- delete ----------------------------------------------------------------

  const remove = async (lis) => {
    const names = lis.map((li) => li.dataset.name);
    const ok = await SFH.confirm({
      title: t.deleteTitle,
      body: (names.length === 1 ? SFH.format(t.deleteOne, { name: names[0] }) : SFH.format(t.deleteMany, { count: names.length }))
        + ' ' + t.deleteNote,
      items: names.length > 1 ? names : [],
    });
    if (!ok) return;
    const body = new FormData();
    names.forEach((name) => body.append('name', name));
    try {
      const result = await SFH.request(t.deleteUrl, { body });
      const gone = new Set(result.deleted);
      lis.filter((li) => gone.has(li.dataset.name)).forEach((li) => li.remove());
      if (result.deleted.length === 1) SFH.toast(SFH.format(t.deleted, { name: result.deleted[0] }), 'success');
      else if (result.deleted.length) SFH.toast(SFH.format(t.deletedMany, { count: result.deleted.length }), 'success');
      if (result.failed.length) SFH.toast(result.failed.join(', '), 'error');
    } catch (error) {
      SFH.toast(error.message, 'error');
    }
    updateSummary();
    updateSelection();
  };

  form.querySelector('[data-action="delete-selected"]').addEventListener('click', (event) => {
    event.preventDefault();
    remove(selected());
  });

  // -- share -----------------------------------------------------------------

  const shareDialog = document.getElementById('share-dialog');
  const shareUrl = document.getElementById('share-url');
  document.getElementById('share-copy').addEventListener('click', () => {
    shareUrl.select();
    SFH.copy(shareUrl.value);
  });

  const share = async (li) => {
    try {
      const result = await SFH.request(t.shareUrl.replace('__NAME__', encodeURIComponent(li.dataset.name)));
      shareUrl.value = result.url;
      document.getElementById('share-note').textContent = SFH.format(t.shareNote, { hours: result.hours });
      shareDialog.showModal();
      shareUrl.select();
    } catch (error) {
      SFH.toast(error.message, 'error');
    }
  };

  // -- preview ---------------------------------------------------------------

  const previewDialog = document.getElementById('preview-dialog');
  const previewBody = document.getElementById('preview-body');
  let current = null;
  let textRequest = null;

  const previewable = () => visibleItems().filter((li) => li.dataset.preview);

  const renderText = async (url) => {
    textRequest?.abort();
    textRequest = new AbortController();
    const limit = 512 * 1024;
    const pre = document.createElement('pre');
    previewBody.replaceChildren(Object.assign(document.createElement('div'), { className: 'spinner' }));
    try {
      const response = await fetch(url, { headers: { Range: `bytes=0-${limit - 1}` }, signal: textRequest.signal });
      const bytes = await response.arrayBuffer();
      pre.textContent = new TextDecoder().decode(bytes.slice(0, limit));
      previewBody.replaceChildren(pre);
      if (response.status === 206) {
        previewBody.append(Object.assign(document.createElement('span'), { className: 'preview-note', textContent: t.previewTooLarge }));
      }
    } catch (error) {
      if (error.name !== 'AbortError') previewBody.replaceChildren(SFH.icon('warning'));
    }
  };

  const showPreview = (li) => {
    current = li;
    const url = downloadUrl(li);
    const inline = `${url}?inline=1`;
    document.getElementById('preview-title').textContent = li.dataset.name;
    document.getElementById('preview-download').href = url;
    textRequest?.abort();
    let element;
    switch (li.dataset.preview) {
      case 'image':
        element = Object.assign(document.createElement('img'), { src: inline, alt: li.dataset.name });
        break;
      case 'video':
        element = Object.assign(document.createElement('video'), { src: inline, controls: true, autoplay: true, playsInline: true });
        break;
      case 'audio':
        element = Object.assign(document.createElement('audio'), { src: inline, controls: true, autoplay: true });
        break;
      case 'pdf':
        element = Object.assign(document.createElement('iframe'), { src: inline, title: li.dataset.name });
        break;
      default:
        renderText(inline);
    }
    if (element) previewBody.replaceChildren(element);
    const many = previewable().length > 1;
    previewDialog.querySelectorAll('.preview-nav').forEach((b) => { b.hidden = !many; });
    if (!previewDialog.open) previewDialog.showModal();
  };

  const step = (delta) => {
    const all = previewable();
    if (all.length < 2) return;
    const index = all.indexOf(current);
    showPreview(all[(index + delta + all.length) % all.length]);
  };

  previewDialog.querySelectorAll('.preview-nav').forEach((b) => b.addEventListener('click', () => step(Number(b.dataset.step))));
  previewDialog.querySelector('[data-close]').addEventListener('click', () => previewDialog.close());
  previewDialog.addEventListener('close', () => {
    textRequest?.abort();
    previewBody.replaceChildren(); // stops media playback
  });
  previewDialog.addEventListener('click', (event) => {
    if (event.target === previewDialog) previewDialog.close();
  });
  previewDialog.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') step(-1);
    if (event.key === 'ArrowRight') step(1);
  });

  // -- row actions -----------------------------------------------------------

  list.addEventListener('click', (event) => {
    const li = event.target.closest('.file');
    if (!li) return;
    const action = event.target.closest('[data-action]')?.dataset.action;
    const nameLink = event.target.closest('.file-name, .file-thumb');
    if (action === 'delete') remove([li]);
    else if (action === 'share') share(li);
    else if (action === 'preview' || (nameLink && li.dataset.preview && !event.ctrlKey && !event.metaKey)) {
      event.preventDefault();
      showPreview(li);
    }
  });

  updateSelection();
})();
