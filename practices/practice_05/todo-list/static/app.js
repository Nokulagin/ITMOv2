// Todo list UI: plain browser JavaScript, no framework and no build step.
// Endpoints and status codes: specs/001-todo-list/contract.md (sections 3 and 5).
// Texts: specs/001-todo-list/ui/spec.md, section "Тексты интерфейса".

const API_TODOS = '/api/todos';
const TITLE_MAX_LENGTH = 200;

// Characters trimmed from both ends of a title. The set matches the server trimming
// in server/validation.py (Python str.strip()): Unicode whitespace plus U+001C-U+001F.
const EDGE_SPACE_PATTERN = /^[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g;

// Trim the title the same way the server does. Used for the empty check, the length check and the request.
function normalizeTitle(value) {
  return value.replace(EDGE_SPACE_PATTERN, '');
}

const TEXT = {
  loading: 'Загрузка…',
  empty: 'Задач пока нет. Добавьте первую.',
  emptyTitle: 'Введите название задачи.',
  tooLongTitle: 'Название не длиннее 200 символов.',
  loadError: 'Не удалось загрузить список. Обновите страницу.',
  saveError: 'Не удалось сохранить изменения. Попробуйте ещё раз.',
  networkError: 'Нет связи с сервером. Проверьте подключение и попробуйте ещё раз.',
  notFound: 'Задача не найдена. Обновите страницу.',
};

const titleForm = document.getElementById('add-form');
const titleInput = document.getElementById('title-input');
const addButton = document.getElementById('add-button');
const titleError = document.getElementById('title-error');
const listMessage = document.getElementById('list-message');
const listStatus = document.getElementById('list-status');
const counter = document.getElementById('counter');
const taskList = document.getElementById('task-list');

let addPending = false;
const pendingDeletes = new Set();

// Selector of the element to focus after the next list render, or null.
let focusTarget = null;

// Send a request and return { ok, status, network, data }. Never throws.
// A network failure is reported as status 0 with network set to true.
async function request(method, path, body) {
  const options = { method, cache: 'no-store', headers: {} };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    return { ok: false, status: 0, network: true, data: null };
  }

  let data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }
  }
  return { ok: response.ok, status: response.status, network: false, data };
}

// Pick the UI text for a failed request. The server's `error` text is never shown.
// context: 'load', 'add', 'patch' or 'delete'.
// The 400 on add (title checks) is handled in the submit handler, not here.
function statusToMessage(status, context) {
  if (status === 0) return TEXT.networkError;
  if (context === 'load') return TEXT.loadError;
  if (status === 404 && context !== 'add') return TEXT.notFound;
  return TEXT.saveError;
}

// Show a message under the title field ('title') or above the list ('list').
function showMessage(text, field) {
  if (field === 'title') {
    titleError.textContent = text;
    titleInput.setAttribute('aria-describedby', 'title-error');
  } else {
    listMessage.textContent = text;
  }
}

function clearMessage() {
  titleError.textContent = '';
  titleInput.removeAttribute('aria-describedby');
  listMessage.textContent = '';
}

function taskSelector(id, part) {
  return `.task-item[data-task-id="${id}"] ${part}`;
}

function applyFocusTarget() {
  if (focusTarget === null) return;
  const target = document.querySelector(focusTarget);
  focusTarget = null;
  if (target) target.focus();
}

// Build one list row. Text is set with textContent, never as HTML.
function createTaskItem(task) {
  const item = document.createElement('li');
  item.className = 'task-item';
  item.dataset.taskId = String(task.id);

  const label = document.createElement('label');
  label.className = 'task-item__label';

  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.className = 'task-item__check';
  checkbox.checked = task.done === true;

  const title = document.createElement('span');
  title.className = 'task-item__title';
  if (task.done) {
    title.classList.add('task-item__title--done');
  }
  title.textContent = task.title;

  label.append(checkbox, title);

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'button task-item__delete';
  remove.textContent = 'Удалить';
  remove.setAttribute('aria-label', `Удалить задачу «${task.title}»`);

  item.append(label, remove);
  return item;
}

// Draw the list in the order the server sent it (no sorting on the client).
function renderTasks(tasks) {
  taskList.replaceChildren(...tasks.map(createTaskItem));

  const total = tasks.length;
  const done = tasks.filter((task) => task.done === true).length;
  counter.textContent = total > 0 ? `Выполнено: ${done} из ${total}` : '';
  counter.hidden = total === 0;
  listStatus.textContent = total === 0 ? TEXT.empty : '';
}

// Fetch the list and draw it, or show the load error state.
async function loadTasks() {
  const result = await request('GET', API_TODOS);

  if (result.ok && Array.isArray(result.data)) {
    renderTasks(result.data);
  } else {
    taskList.replaceChildren();
    counter.textContent = '';
    counter.hidden = true;
    listStatus.textContent = '';
    showMessage(statusToMessage(result.status, 'load'), 'list');
  }

  applyFocusTarget();
}

async function handleSubmit(event) {
  event.preventDefault();
  if (addPending) return;

  clearMessage();
  const title = normalizeTitle(titleInput.value);
  if (title === '') {
    showMessage(TEXT.emptyTitle, 'title');
    titleInput.focus();
    return;
  }

  // Length is counted in Unicode code points after trimming (contract, section 6).
  if ([...title].length > TITLE_MAX_LENGTH) {
    showMessage(TEXT.tooLongTitle, 'title');
    titleInput.focus();
    return;
  }

  addPending = true;
  // A disabled button loses focus, so remember whether it had focus.
  const hadButtonFocus = document.activeElement === addButton;
  addButton.disabled = true;

  const result = await request('POST', API_TODOS, { title });

  addPending = false;
  addButton.disabled = false;

  if (result.status === 201) {
    titleInput.value = '';
    titleInput.focus();
    await loadTasks();
    return;
  }

  if (result.status === 400) {
    // Fallback: the client already rejects empty and too long titles, so this is rare.
    // Pick the text by length: the server may trim a character that JS does not (e.g. \u001c).
    showMessage([...title].length > TITLE_MAX_LENGTH ? TEXT.tooLongTitle : TEXT.emptyTitle, 'title');
    titleInput.focus();
    return;
  }

  showMessage(statusToMessage(result.status, 'add'), 'list');
  if (hadButtonFocus) {
    addButton.focus();
  }
}

async function handleToggle(checkbox) {
  const id = checkbox.closest('.task-item').dataset.taskId;
  const done = checkbox.checked;

  clearMessage();
  const result = await request('PATCH', `${API_TODOS}/${id}`, { done });

  if (result.ok) {
    focusTarget = taskSelector(id, '.task-item__check');
    await loadTasks();
    return;
  }

  // Put the checkbox back to its previous position.
  checkbox.checked = !done;
  showMessage(statusToMessage(result.status, 'patch'), 'list');
  if (result.status === 404) {
    await loadTasks();
  }
}

async function handleDelete(button) {
  const item = button.closest('.task-item');
  const id = item.dataset.taskId;
  if (pendingDeletes.has(id)) return;

  clearMessage();
  pendingDeletes.add(id);
  const result = await request('DELETE', `${API_TODOS}/${id}`);
  pendingDeletes.delete(id);

  if (result.ok) {
    // Focus moves to the delete button of the next task, or to the input if none is left.
    const next = item.nextElementSibling;
    focusTarget = next ? taskSelector(next.dataset.taskId, '.task-item__delete') : '#title-input';
    await loadTasks();
    return;
  }

  showMessage(statusToMessage(result.status, 'delete'), 'list');
  if (result.status === 404) {
    await loadTasks();
  }
}

function init() {
  titleForm.addEventListener('submit', handleSubmit);

  taskList.addEventListener('change', (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.classList.contains('task-item__check')) {
      handleToggle(target);
    }
  });

  taskList.addEventListener('click', (event) => {
    const button = event.target.closest('.task-item__delete');
    if (button) {
      handleDelete(button);
    }
  });

  listStatus.textContent = TEXT.loading;
  loadTasks();
}

document.addEventListener('DOMContentLoaded', init);
