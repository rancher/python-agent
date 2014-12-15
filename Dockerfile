FROM rancher/docker-dind-base:v3
ENV DOCKER_DRIVER vfs
COPY ./scripts/bootstrap /scripts/bootstrap
RUN /scripts/bootstrap
WORKDIR /source
