# Build the interface, then serve static files with nginx.
# This is the single frontend image for local and offline installations.

FROM node:24-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# The interface calls the API through the same origin it was served from, so
# nginx can proxy /api and the browser never makes a cross-origin request.
ARG VITE_RENDER_DEMO=true
ENV VITE_RENDER_DEMO=${VITE_RENDER_DEMO}
ENV VITE_API_BASE_URL=""
RUN npm run build


FROM nginx:stable-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
