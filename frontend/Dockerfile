FROM node:23.5.0-alpine3.20 AS builder
RUN npm install -g @angular/cli

WORKDIR /usr/src/app

COPY ./ ./
RUN npm ci && npm run build



FROM nginx:latest

COPY ./nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /usr/src/app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80
