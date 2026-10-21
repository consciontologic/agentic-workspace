# Replace the base with a digest-pinned image (FROM name@sha256:...) before the first release.
FROM docker.io/nginxinc/nginx-unprivileged:stable-alpine
COPY {{ARTIFACT_DIR}}/ /usr/share/nginx/html/
USER 101
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
