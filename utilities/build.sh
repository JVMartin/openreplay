#!/bin/bash

# Script to build api module
# flags to accept:
# Default will be OSS build.

# Usage: IMAGE_TAG=latest DOCKER_REPO=myDockerHubID bash build.sh <ee>

git_sha=$(git rev-parse --short HEAD)
image_tag=${IMAGE_TAG:-git_sha}
check_prereq() {
    which docker || {
        echo "Docker not installed, please install docker."
        exit 1
    }
}

function build_api(){
    destination="_utilities"
    [[ $1 == "ee" ]] && {
        destination="_utilities_ee"
    }
    cp -R ../utilities ../${destination}
    cd ../${destination}

    # Copy enterprise code
    [[ $1 == "ee" ]] && {
        cp -rf ../ee/utilities/* ./
    }
    docker build -f ./Dockerfile --build-arg GIT_SHA=$git_sha -t ${DOCKER_REPO:-'local'}/assist:${image_tag} .

    cd ../utilities
    rm -rf ../${destination}
    [[ $PUSH_IMAGE -eq 1 ]] && {
        docker push ${DOCKER_REPO:-'local'}/assist:${image_tag}
        docker tag ${DOCKER_REPO:-'local'}/assist:${image_tag} ${DOCKER_REPO:-'local'}/assist:latest
        docker push ${DOCKER_REPO:-'local'}/assist:latest
    }
    [[ $SIGN_IMAGE -eq 1 ]] && {
        cosign sign --key $SIGN_KEY ${DOCKER_REPO:-'local'}/assist:${image_tag}
    }
    echo "build completed for assist"
}

check_prereq
build_api $1
