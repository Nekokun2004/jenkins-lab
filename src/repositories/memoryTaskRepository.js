let tasks = [];
let nextId = 1;

function reset() {
  tasks = [];
  nextId = 1;
}

async function list() {
  return tasks;
}

async function create({ title }) {
  const task = { id: nextId++, title, done: false, createdAt: new Date().toISOString() };
  tasks.push(task);
  return task;
}

async function markDone(id) {
  const task = tasks.find((t) => t.id === Number(id));
  if (!task) return null;
  task.done = true;
  return task;
}

async function remove(id) {
  const index = tasks.findIndex((t) => t.id === Number(id));
  if (index === -1) return false;
  tasks.splice(index, 1);
  return true;
}

module.exports = { list, create, markDone, remove, reset };
