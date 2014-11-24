FROM rancher/docker-dind-base
ENV DOCKER_DRIVER vfs
COPY ./scripts/bootstrap /scripts/bootstrap
RUN /scripts/bootstrap
WORKDIR /source
