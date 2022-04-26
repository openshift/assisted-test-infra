#!/bin/bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

export SERVICE_REPO=${SERVICE_REPO:-https://github.com/openshift/assisted-service}
export SERVICE_BRANCH=${SERVICE_BRANCH:-master}
export SERVICE_BASE_REF=${SERVICE_BASE_REF:-master}
export OPENSHIFT_CI=${OPENSHIFT_CI:-false}
export REPO_NAME=${REPO_NAME:-assisted-service}
export JOB_TYPE=${JOB_TYPE:-}
export PULL_BASE_REF=${PULL_BASE_REF:-master}

if ! [[ -d "assisted-service" ]]; then
  echo "Can't find assisted-service source locally, cloning ${SERVICE_REPO}"
  git clone "${SERVICE_REPO}"
fi

service_active_branch=$(cd assisted-service/ && git rev-parse --abbrev-ref HEAD)
pr_branch_name=assisted-service-pr-${PULL_NUMBER}

if [[ "${OPENSHIFT_CI}" == "true" && "${REPO_NAME}" == "assisted-service" && "${JOB_TYPE}" == "presubmit" ]]; then
  if [[ "${service_active_branch}" == "${pr_branch_name}" ]]; then
    # Assisted-Service source code is already updated and rebased with PULL_BASE_REF.
    # git fetch cannot be called twice after rebase so if the PR branch already exist the assumption is that it was
    # already fetched and rebased on another call of this target
    echo "Nothing to update. ${REPO_NAME} is already updated, branch: ${pr_branch_name}"
    exit 0
  fi

  echo "Running in assisted-service pull request"
  cd assisted-service
  git fetch -v origin "pull/${PULL_NUMBER}/head:${pr_branch_name}"
  git checkout "${pr_branch_name}"
  git rebase -v "origin/${PULL_BASE_REF}"
else
  cd assisted-service
  git fetch --force origin "${SERVICE_BASE_REF}:FETCH_BASE" "${SERVICE_BRANCH}"
  git reset --hard FETCH_HEAD
  git rebase FETCH_BASE
fi
