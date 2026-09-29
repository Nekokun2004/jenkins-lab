FROM postgres:16-alpine
# Bake the schema into the image instead of bind-mounting it: the Jenkins agent talks to the
# host's Docker daemon, so a relative bind mount is resolved on the host, not in the agent.
COPY schema.sql /docker-entrypoint-initdb.d/schema.sql
