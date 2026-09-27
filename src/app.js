const express = require('express');
const tasksRouter = require('./routes/tasks');

const app = express();

app.use(express.json());

// Health endpoint - polled directly by the Lab 07 blue/green smoke test
// (kubectl run ... curl http://taskflow-<color>:8080/health)
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

app.use('/api/tasks', tasksRouter);

// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  // eslint-disable-next-line no-console
  console.error(err);
  res.status(500).json({ error: 'internal server error' });
});

module.exports = app;
