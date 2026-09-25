FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_WS_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S -g 10001 deetrader && adduser -S -u 10001 -G deetrader deetrader
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY --from=build --chown=10001:10001 /app/dist ./dist
COPY --from=build --chown=10001:10001 /app/public ./public
USER deetrader
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O - http://localhost:3000/ >/dev/null || exit 1
CMD ["npm","run","start","--","--hostname","0.0.0.0","--port","3000"]
