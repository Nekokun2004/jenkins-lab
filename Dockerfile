FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY src ./src

# There is no compile step today. Keep this stage for future build steps, then
# leave only runtime dependencies; remove source maps and test files for the final image.
RUN npm prune --omit=dev \
    && find src node_modules -type f \( -name '*.map' -o -name '*.test.js' -o -name '*.spec.js' \) -delete \
    && npm cache clean --force

FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080

COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/src ./src

USER node

EXPOSE 8080

CMD ["node", "src/index.js"]
