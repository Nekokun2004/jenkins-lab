# taskflow-api

Task-tracking API (Node.js 20 / Express / PostgreSQL) — the case-study app for the
Jenkins CI/CD Pipeline Lab Manual (Labs 01–10).

## Quick start (local, no Docker)

```bash
npm ci
npm run lint
npm test
npm start        # listens on http://localhost:8080
```

`GET /health` → `{"status":"ok"}`

## Quick start (Docker Compose — API + Postgres)

```bash
docker compose up -d --build
curl http://localhost:8080/health
```

Without `DATABASE_URL` set, the API uses an in-memory task store (fast, no DB
needed — this is what `npm test` runs against). With `DATABASE_URL` set (as
docker-compose does), it talks to real Postgres using `db/schema.sql`.

## API

| Method | Path                  | Body            | Notes                        |
|--------|-----------------------|------------------|-------------------------------|
| GET    | `/health`             | –                | liveness check                |
| GET    | `/api/tasks`          | –                | list tasks                    |
| POST   | `/api/tasks`          | `{ "title" }`    | create task                   |
| PATCH  | `/api/tasks/:id/done` | –                | mark task done                |
| DELETE | `/api/tasks/:id`      | –                | delete task                   |

## Unit test coverage scope

`collectCoverageFrom` in `package.json` excludes two files from the unit coverage
denominator:

- `src/index.js` — pure process bootstrap (starts the HTTP server on a port);
  no branching logic worth unit-testing.
- `src/repositories/pgTaskRepository.js` — the real PostgreSQL-backed
  repository implementation. It's only meaningfully exercised against a real
  database, which the Playwright E2E suite does via `docker compose` (see
  Lab 05); mocking the `pg` driver to unit-test it would test the mock, not
  the SQL. `memoryTaskRepository.js` (used by `npm test`) already covers the
  same interface contract with real assertions.

This keeps the SonarQube `taskflow-gate-70` coverage gate meaningful — it
measures how well the code that *can* be unit-tested actually is, rather than
being dragged down by files that are legitimately covered by a different test
layer.

## Push this to your own GitHub repo

```bash
cd taskflow-api
git init
git add .
git commit -m "Initial taskflow-api scaffold"
git branch -M main
git remote add origin https://github.com/Nekokun2004/jenkins-lab.git
git push -u origin main
```

## Where each file is used across the labs

- `Dockerfile`, `docker-compose.yml` → Lab 01 (agent), Lab 03 (Docker agent), Lab 07 (build/scan/deploy)
- `src/app.js` `/health` route → Lab 07 blue/green smoke test
- `npm run lint` / `.eslintrc.json` (with `eslint-plugin-security`) → Lab 03 Lint stage, Lab 06 SAST stage
- `npm run test:ci` (Jest + `jest-junit` + cobertura coverage) → Lab 05 JUnit/coverage publishing, SonarQube gate
- `tests/tasks.test.js` (list / create / mark-done) → mirrors the 3 Playwright specs required in Lab 05
- `db/schema.sql` → Lab 08 Ansible-provisioned host, Lab 07 Postgres-backed deploy
- `package.json` deps (`express`, `pg`) → scanned by `npm audit` (Lab 06) and Trivy (Lab 07)
