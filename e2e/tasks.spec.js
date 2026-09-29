const { test, expect } = require('@playwright/test');

test('list tasks returns 200 and an array', async ({ request }) => {
  const res = await request.get('/api/tasks');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body)).toBe(true);
});

test('create task returns 201 with the created task', async ({ request }) => {
  const res = await request.post('/api/tasks', { data: { title: 'E2E test task' } });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.title).toBe('E2E test task');
  expect(body.done).toBe(false);
});

test('mark task done updates its status', async ({ request }) => {
  const created = await (await request.post('/api/tasks', { data: { title: 'to complete' } })).json();
  const res = await request.patch(`/api/tasks/${created.id}/done`);
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.done).toBe(true);
});
