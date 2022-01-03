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

sizes=(
  2
  4
  8
  16
  32
  64
  128
  256
  512
  1024
  2048
  4096
  8192
  16384
  32768
  65536
  131072
  262144
  524288
  1048576
  2097152
  4194304
  8388608
)

commands=(
  "read"
  "write"
  "send"
)

quote=""

if [[ -n "${WRAPPER:-}" ]]; then
  quote="'"
fi

for c in "${commands[@]}"; do
  data_file_host1="../data/raw/${DATA_DIR}/${c}_cpu_server_${DATA_SUFFIX}.txt"
  data_file_host2="../data/raw/${DATA_DIR}/${c}_cpu_client_${DATA_SUFFIX}.txt"
  echo -n "" > "$data_file_host1"
  echo -n "" > "$data_file_host2"

  host1_cpu_count=$(ssh -t "${SSH_USER}@${HOST1}" "cat /proc/cpuinfo" | grep -c 'processor')
  host2_cpu_count=$(ssh -t "${SSH_USER}@${HOST2}" "cat /proc/cpuinfo" | grep -c 'processor') 

  for s in "${sizes[@]}"; do
    echo -n "$s " >> "$data_file_host1"
    echo -n "$s " >> "$data_file_host2"

    ssh -t "${SSH_USER}@${HOST1}" "${WRAPPER:-} ${quote}ib_${c}_bw ${ARGS} -s ${s} -D 16${quote}" &
    sleep 1
    ssh -t "${SSH_USER}@${HOST2}" "${WRAPPER:-} ${quote}ib_${c}_bw ${ARGS} -s ${s} -D 16 ${HOST1}${quote}" &
    sleep 1


    (echo "$(( (10000 - $(ssh -t "${SSH_USER}@${HOST1}" "sar 10 1 | tail -n 1 | awk '{print \$8}' | tr -d '.\r\n'")) * host1_cpu_count ))" | sed -E 's/([0-9]*)([0-9]{2})/\1.\2/g' >> "$data_file_host1") &
    (echo "$(( (10000 - $(ssh -t "${SSH_USER}@${HOST2}" "sar 10 1 | tail -n 1 | awk '{print \$8}' | tr -d '.\r\n'")) * host2_cpu_count ))" | sed -E 's/([0-9]*)([0-9]{2})/\1.\2/g' >> "$data_file_host2")

    wait 
    sleep 1
  done
done
