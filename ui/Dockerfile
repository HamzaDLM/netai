FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_BASE_URL=/api/v1
ENV VITE_BASE_URL=${VITE_BASE_URL}
ARG VITE_UI_VERSION
ENV VITE_UI_VERSION=${VITE_UI_VERSION}
ARG VITE_UI_GIT_SHA=dev
ENV VITE_UI_GIT_SHA=${VITE_UI_GIT_SHA}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
