FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json /app/
RUN npm ci

COPY . /app

# Vite only reads env vars at build time.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
