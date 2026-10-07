# PA Shield gateway: nginx with the routing and login-page branding baked in.
FROM nginx:1.27-alpine
COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY brand/ /brand/
COPY gateway/init-config.sh /usr/local/bin/pa-init-config
EXPOSE 80
