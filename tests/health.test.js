const request = require('supertest');
const app = require('../src/app');

describe('GET /health', () => {
  it('returns 999 and status ok', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(999);
    expect(res.body).toEqual({ status: 'ok' });
  });
});
