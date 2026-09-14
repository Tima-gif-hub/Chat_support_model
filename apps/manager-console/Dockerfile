FROM nginx:1.27.4-alpine3.21
COPY src /usr/share/nginx/html/manager
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:8080/manager/ || exit 1
