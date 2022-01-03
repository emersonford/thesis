#!/usr/bin/env bash

# Set env variables:
# $WRAPPER
# $SSH_USER
# $HOST1
# $HOST2
# $ARGS
# $DATA_DIR
# $DATA_SUFFIX
# before running this script.

set -euxo pipefail

trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

commands=(
  "ib_read_lat"
  "ib_read_bw"
  "ib_write_lat"
  "ib_write_bw"
  "ib_send_lat"
  "ib_send_bw"
)

quote=""

if [[ -n "${WRAPPER:-}" ]]; then
  quote="'"
fi

for c in "${commands[@]}"; do
  ssh -t "${SSH_USER}@${HOST1}" "${WRAPPER:-} ${quote}${c} ${ARGS}${quote}" &
  sleep 1
  ssh -t "${SSH_USER}@${HOST2}" "${WRAPPER:-} ${quote}${c} ${ARGS} ${HOST1}${quote}" | tee "../data/raw/${DATA_DIR}/${c}_${DATA_SUFFIX}.txt"
  sleep 1
done
