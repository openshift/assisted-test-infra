#!/bin/bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/utils.sh"

export SERVICE_REPO=${SERVICE_REPO:-https://github.com/openshift/assisted-service}
export SERVICE_BRANCH=${SERVICE_BRANCH:-master}
export SERVICE_BASE_REF=${SERVICE_BASE_REF:-master}
export OPENSHIFT_CI=${OPENSHIFT_CI:-false}
export REPO_NAME=${REPO_NAME:-assisted-service}
export JOB_TYPE=${JOB_TYPE:-}
export PULL_BASE_REF=${PULL_BASE_REF:-master}
export SERVICE_COMMIT_REF=${SERVICE_COMMIT_REF:-}


function clone_assisted_service() {
  if ! [[ -d "assisted-service" ]]; then
    echo "Can't find assisted-service source locally, cloning ${SERVICE_REPO}"
    retry -- git clone "${SERVICE_REPO}"
  elif [[ "${USE_LOCAL_SERVICE}" == "true" || "${DEBUG_SERVICE}" == "true" ]]; then
    echo "Using local assisted-service"
    exit 0
  elif [[ ${SERVICE_REPO} != $(cd assisted-service && git remote get-url origin) ]]; then
    echo "assisted-service repository found locally but with a different origin, replacing with ${SERVICE_REPO}"
    rm -rf ./assisted-service
    retry -- git clone "${SERVICE_REPO}"
  fi
}

function config_git() {
  if [[ "${OPENSHIFT_CI}" == "true" ]]; then
    # Some git commands require user/email to be set, use a dummy global
    # user/email for CI if one is not already configured

    if ! git config --global --get user.name; then
        git config --global user.name 'OpenShift CI'
    fi

    if ! git config --global --get user.email; then
        git config --global user.email 'fakeciemail@example.com'
    fi
  fi
}

function set_revision() {
  ## Testing a pull request code
  if [[ "${OPENSHIFT_CI}" == "true" && "${REPO_NAME}" == "assisted-service" && "${JOB_TYPE}" == "presubmit" ]]; then

    service_active_branch=$(cd assisted-service/ && git rev-parse --abbrev-ref HEAD)
    pr_branch_name=assisted-service-pr-${PULL_NUMBER}
    
    if [[ "${service_active_branch}" == "${pr_branch_name}" ]]; then
      # Assisted-Service source code is already updated and rebased with PULL_BASE_REF.
      # git fetch cannot be called twice after rebase so if the PR branch already exist the assumption is that it was
      # already fetched and rebased on another call of this target
      echo "Nothing to update. ${REPO_NAME} is already updated, branch: ${pr_branch_name}"
      return 0
    fi

    echo
    echo "Running in assisted-service pull request"
    cd assisted-service
    retry -- git fetch -v origin "pull/${PULL_NUMBER}/head:${pr_branch_name}"
    git checkout "${pr_branch_name}"
    git rebase -v "origin/${PULL_BASE_REF}"
    return 0
  fi

  cd assisted-service
  
  # Testing a specific commit reference code
  if [ "${SERVICE_COMMIT_REF}" != "" ]; then
    echo
    echo "Resetting to assisted-service commit: ${SERVICE_COMMIT_REF}"
    retry -- git reset --hard "${SERVICE_COMMIT_REF}"
    return 0
  fi
  
  # Testing a specific branch code
  echo
  echo "Switching to branch: ${SERVICE_BASE_REF}"
  retry -- git fetch --force origin "${SERVICE_BASE_REF}:FETCH_BASE" "${SERVICE_BRANCH}"
  git reset --hard FETCH_HEAD
  git rebase FETCH_BASE

  return 0
}

clone_assisted_service
config_git
set_revision
exit $?
