const request = require('supertest');
const app = require('../src/app');
const memoryRepo = require('../src/repositories/memoryTaskRepository');

beforeEach(() => {
  memoryRepo.reset();
});

describe('Tasks API', () => {
  it('starts with an empty list', async () => {
    const res = await request(app).get('/api/tasks');
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it('creates a task', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 'Write Jenkinsfile' });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ title: 'Write Jenkinsfile', done: false });
  });

  it('rejects a task with no title', async () => {
    const res = await request(app).post('/api/tasks').send({});
    expect(res.status).toBe(400);
  });

  it('marks a task done', async () => {
    const created = await request(app).post('/api/tasks').send({ title: 'Ship pipeline' });
    const res = await request(app).patch(`/api/tasks/${created.body.id}/done`);
    expect(res.status).toBe(200);
    expect(res.body.done).toBe(true);
  });

  it('404s marking a nonexistent task done', async () => {
    const res = await request(app).patch('/api/tasks/9999/done');
    expect(res.status).toBe(404);
  });

  it('deletes a task', async () => {
    const created = await request(app).post('/api/tasks').send({ title: 'Temp task' });
    const res = await request(app).delete(`/api/tasks/${created.body.id}`);
    expect(res.status).toBe(204);
  });
});
