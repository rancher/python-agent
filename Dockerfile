FROM rancher/docker-dind-base:v0.4.1
ENV DOCKER_DRIVER vfs
COPY ./scripts/bootstrap /scripts/bootstrap
RUN /scripts/bootstrap
WORKDIR /source
