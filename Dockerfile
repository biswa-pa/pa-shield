# Official NetBird dashboard, plus Predicta branding.
# Bump NETBIRD_DASHBOARD_TAG and rebuild when NetBird ships a new dashboard.
# Branding is applied every time the container starts, so the new HTML is patched
# without editing files inside the upstream image.
ARG NETBIRD_DASHBOARD_TAG=v2.90.3
FROM netbirdio/dashboard:${NETBIRD_DASHBOARD_TAG}

COPY brand/ /opt/pa-netbird/brand/
COPY docker/apply-branding.sh /opt/pa-netbird/apply-branding.sh
COPY docker/pa-branding.ini /tmp/pa-branding.ini
COPY docker/apply-theme.sh /opt/pa-netbird/apply-theme.sh

RUN chmod 755 /opt/pa-netbird/apply-branding.sh /opt/pa-netbird/apply-theme.sh \
    && /opt/pa-netbird/apply-theme.sh \
    && printf '\n' >> /etc/supervisord.conf \
    && cat /tmp/pa-branding.ini >> /etc/supervisord.conf \
    && rm /tmp/pa-branding.ini
