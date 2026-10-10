// Row navigation, foreign key pickers, and the stacked CRUD modal.
(() => {
  // Sidebar groups: remember which ones the viewer closed (per browser). Storage may be
  // unavailable (private windows, blocked site data), so every access is guarded.
  const NAV_KEY = 'dbml-crud.closed-groups';
  const closedGroups = (() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(NAV_KEY) || '[]'));
    } catch {
      return new Set();
    }
  })();
  const saveClosedGroups = () => {
    try {
      localStorage.setItem(NAV_KEY, JSON.stringify([...closedGroups]));
    } catch {
      // not remembered this time; the sidebar still works
    }
  };
  document.querySelectorAll('[data-nav-group]').forEach((body) => {
    const name = body.dataset.navGroup;
    const toggle = document.querySelector(`[data-bs-target="#${body.id}"]`);
    // The group holding the current page always stays open.
    if (closedGroups.has(name) && !body.querySelector('.active')) {
      body.classList.remove('show');
      toggle.classList.add('collapsed');
      toggle.setAttribute('aria-expanded', 'false');
    }
    body.addEventListener('shown.bs.collapse', () => {
      closedGroups.delete(name);
      saveClosedGroups();
    });
    body.addEventListener('hidden.bs.collapse', () => {
      closedGroups.add(name);
      saveClosedGroups();
    });
  });

  const modalEl = document.getElementById('crudModal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const body = modalEl.querySelector('.modal-body');
  const titleEl = modalEl.querySelector('.modal-title');
  const headerBack = modalEl.querySelector('.modal-header [data-modal-back]');

  // Each entry: {node, title, url, onSelect?, onDone?}. The top entry is shown.
  const stack = [];

  const top = () => stack[stack.length - 1];

  function fragment(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    return div;
  }

  // Text areas grow to fit their content.
  function autogrow(el) {
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight + 2}px`;
  }
  const growAll = (root) => root.querySelectorAll('textarea[data-autogrow]').forEach(autogrow);
  document.addEventListener('input', (e) => {
    if (e.target.matches('textarea[data-autogrow]')) autogrow(e.target);
  });
  growAll(document);

  // Enum dropdowns show the DBML note for the chosen value underneath.
  document.addEventListener('change', (e) => {
    const select = e.target.closest('select[data-enum-hint]');
    if (!select) return;
    const hint = select.closest('.field').querySelector('[data-enum-hint-text]');
    hint.textContent = select.selectedOptions[0]?.dataset.note || '';
  });

  function render() {
    const entry = top();
    body.replaceChildren(entry.node);
    growAll(entry.node);
    titleEl.textContent = entry.title;
    headerBack.classList.toggle('d-none', stack.length < 2);
  }

  function showError(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger';
    alert.textContent = message;
    top().node.prepend(alert);
  }

  async function load(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return fragment(await response.text());
  }

  async function push(url, title, handlers = {}) {
    try {
      stack.push({ node: await load(url), title, url, ...handlers });
    } catch (err) {
      console.error('Could not open', url, err);
      return;
    }
    render();
    modal.show();
  }

  async function reload(entry, url = entry.url) {
    entry.url = url;
    entry.node = await load(url);
    if (entry === top()) render();
  }

  function pop() {
    stack.pop();
    if (stack.length) render();
    else modal.hide();
  }

  // Text areas cannot be measured while the modal is hidden; size them once it is shown.
  modalEl.addEventListener('shown.bs.modal', () => growAll(body));

  modalEl.addEventListener('hidden.bs.modal', () => {
    stack.length = 0;
    body.replaceChildren();
  });

  function addChip(widget, id, label) {
    const name = widget.dataset.name;
    if ([...widget.querySelectorAll(`input[name="${name}"]`)].some((i) => i.value === id)) return;
    const chip = document.createElement('span');
    chip.className = 'm2m-chip';
    chip.dataset.m2mItem = '';
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = id;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn-close btn-close-white';
    remove.dataset.m2mRemove = '';
    remove.setAttribute('aria-label', 'Remove');
    chip.append(input, label, remove);
    widget.querySelector('[data-pick]').before(chip);
  }

  function setFk(widget, id, label) {
    widget.querySelector('[data-fk-value]').value = id;
    widget.querySelector('[data-fk-label]').value = label;
  }

  document.addEventListener('click', (e) => {
    const target = e.target;

    const pick = target.closest('[data-pick]');
    if (pick) {
      e.preventDefault();
      const multi = pick.closest('[data-m2m]');
      const widget = pick.closest('[data-fk]');
      const onSelect = multi
        ? (id, label) => addChip(multi, id, label)
        : (id, label) => setFk(widget, id, label);
      push(pick.href, pick.dataset.title, { onSelect });
      return;
    }

    const removeChip = target.closest('[data-m2m-remove]');
    if (removeChip) {
      removeChip.closest('[data-m2m-item]').remove();
      return;
    }

    // Clicking the read-only label of a picker opens the picker too.
    const fkLabel = target.closest('[data-fk-label]');
    if (fkLabel) {
      fkLabel.closest('[data-fk]').querySelector('[data-pick]').click();
      return;
    }

    const clear = target.closest('[data-fk-clear]');
    if (clear) {
      setFk(clear.closest('[data-fk]'), '', '');
      return;
    }

    if (target.closest('[data-modal-back]')) {
      pop();
      return;
    }

    const reveal = target.closest('[data-confirm-reveal]');
    if (reveal) {
      reveal.classList.add('d-none');
      reveal.parentElement.querySelector('[data-confirm-submit]').classList.remove('d-none');
      return;
    }

    const pushLink = target.closest('[data-modal-push]');
    if (pushLink) {
      e.preventDefault();
      const list = top();
      const selectOnSave = 'selectOnSave' in pushLink.dataset;
      push(pushLink.href, pushLink.dataset.title, {
        onDone: (result) => {
          if (selectOnSave && result.id !== undefined && list.onSelect) {
            pop();
            list.onSelect(String(result.id), result.label);
          } else {
            reload(list);
          }
        },
      });
      return;
    }

    const link = target.closest('[data-modal-link]');
    if (link) {
      e.preventDefault();
      reload(top(), link.href);
      return;
    }

    const select = target.closest('tr[data-select]');
    if (select) {
      const entry = top();
      pop();
      entry.onSelect?.(select.dataset.id, select.dataset.label);
      return;
    }

    const row = target.closest('tr[data-href]');
    if (row && !target.closest('a, button')) {
      window.location = row.dataset.href;
    }
  });

  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!modalEl.contains(form)) return;
    e.preventDefault();
    const entry = top();

    if (form.hasAttribute('data-modal-search')) {
      const url = `${form.action}?${new URLSearchParams(new FormData(form))}`;
      reload(entry, url);
      return;
    }

    let result;
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form) });
      result = await response.json();
    } catch (err) {
      console.error('Save failed', err);
      showError('Save failed — see the browser console.');
      return;
    }
    if (!result.ok) {
      if (result.html) {
        entry.node = fragment(result.html);
        render();
      } else {
        showError(result.error);
      }
      return;
    }
    pop();
    entry.onDone?.(result);
  });
})();
