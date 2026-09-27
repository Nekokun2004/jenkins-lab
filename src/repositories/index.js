const memoryRepo = require('./memoryTaskRepository');

function getRepository() {
  if (process.env.DATABASE_URL) {
    // Lazily required so `pg` is never touched during unit tests without a DB.
    // eslint-disable-next-line global-require
    return require('./pgTaskRepository');
  }
  return memoryRepo;
}

module.exports = { getRepository };
