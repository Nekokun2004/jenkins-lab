const express = require('express');
const { getRepository } = require('../repositories');

const router = express.Router();

router.get('/', async (req, res, next) => {
  try {
    const repo = getRepository();
    const tasks = await repo.list();
    res.json(tasks);
  } catch (err) {
    next(err);
  }
});

router.post('/', async (req, res, next) => {
  try {
    const { title } = req.body;
    if (!title || typeof title !== 'string' || !title.trim()) {
      return res.status(400).json({ error: 'title is required' });
    }
    const repo = getRepository();
    const task = await repo.create({ title: title.trim() });
    res.status(201).json(task);
  } catch (err) {
    next(err);
  }
});

router.patch('/:id/done', async (req, res, next) => {
  try {
    const repo = getRepository();
    const task = await repo.markDone(req.params.id);
    if (!task) {
      return res.status(404).json({ error: 'task not found' });
    }
    res.json(task);
  } catch (err) {
    next(err);
  }
});

router.delete('/:id', async (req, res, next) => {
  try {
    const repo = getRepository();
    const ok = await repo.remove(req.params.id);
    if (!ok) {
      return res.status(404).json({ error: 'task not found' });
    }
    res.status(204).send();
  } catch (err) {
    next(err);
  }
});

module.exports = router;
