const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

async function list() {
  const { rows } = await pool.query('SELECT id, title, done, created_at AS "createdAt" FROM tasks ORDER BY id');
  return rows;
}

async function create({ title }) {
  const { rows } = await pool.query(
    'INSERT INTO tasks (title, done) VALUES ($1, false) RETURNING id, title, done, created_at AS "createdAt"',
    [title]
  );
  return rows[0];
}

async function markDone(id) {
  const { rows } = await pool.query(
    'UPDATE tasks SET done = true WHERE id = $1 RETURNING id, title, done, created_at AS "createdAt"',
    [id]
  );
  return rows[0] || null;
}

async function remove(id) {
  const result = await pool.query('DELETE FROM tasks WHERE id = $1', [id]);
  return result.rowCount > 0;
}

module.exports = { list, create, markDone, remove, pool };
