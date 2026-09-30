FROM node:16-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY src ./src

# There is no compile step today. Keep this stage for future build steps, then
# leave only runtime dependencies; remove source maps and test files for the final image.
RUN npm prune --omit=dev \
    && find src node_modules -type f \( -name '*.map' -o -name '*.test.js' -o -name '*.spec.js' \) -delete \
    && npm cache clean --force

FROM node:16-alpine

WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080

COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/src ./src

# Lab 07 container-scan hardening (Trivy HIGH/CRITICAL gate): the runtime never runs npm/npx/corepack, and
# npm's own bundled deps (tar, glob, minimatch, ...) account for every Node.js finding; OpenSSL has a patched apk.
RUN apk upgrade --no-cache libssl3 libcrypto3 \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

USER node

EXPOSE 8080

CMD ["node", "src/index.js"]
