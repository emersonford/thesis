#!/usr/bin/env python3

import argparse
import sys
from dataclasses import dataclass
from subprocess import PIPE, Popen, run
from time import sleep

import psutil

RDMA_SIZE = 65536

IB_COMMANDS = ["read", "write", "send"]

PAIRS_COUNT = list(range(1, 32 + 1))


def main(args: argparse.Namespace) -> int:
    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

    host1_cpu_count = run(
        ssh_host_1 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    host2_cpu_count = run(
        ssh_host_2 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    for c in IB_COMMANDS:
        with (
            open(
                f"../data/raw/softroce_multi_vdev/ib_{c}_bw_{args.mode}.txt", "w"
            ) as bw_file,
            open(
                f"../data/raw/softroce_multi_vdev/{c}_cpu_server_{args.mode}.txt", "w"
            ) as cpu_file_server,
            open(
                f"../data/raw/softroce_multi_vdev/{c}_cpu_client_{args.mode}.txt", "w"
            ) as cpu_file_client,
        ):
            bw_file.write("#pairs\tBW average[MB/sec]\tMsgRate[Mpps]\n")
            cpu_file_server.write("#pairs\tCPU Usage %\n")
            cpu_file_client.write("#pairs\tCPU Usage %\n")

    if args.mode == "host":
        for c in IB_COMMANDS:
            for pair_count in PAIRS_COUNT:
                print(
                    f"Running IB command `ib_{c}_bw` with pair_count = {pair_count}..."
                )

                ib_server = Popen(
                    ssh_host_1
                    + [
                        f"ib_{c}_bw -d {args.if_name} -q {pair_count} -D 5 --run_infinitely -s {RDMA_SIZE}"
                    ],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                sleep(1)

                ib_client = Popen(
                    ssh_host_2
                    + [
                        f"ib_{c}_bw -d {args.if_name} -q {pair_count} -D 5 --run_infinitely -s {RDMA_SIZE} {args.host1}"
                    ],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                sleep(1)

                if ib_server.returncode is not None or ib_client.returncode is not None:
                    if ib_server.returncode is not None:
                        print(
                            f"Failed to run IB command on {args.host1}: {ib_server.communicate()}"
                        )

                    if ib_client.returncode is not None:
                        print(
                            f"Failed to run IB command on {args.host2}: {ib_client.communicate()}"
                        )

                    return 1

                cpu_server = Popen(
                    ssh_host_1 + ["sar 10 1"],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                cpu_client = Popen(
                    ssh_host_2 + ["sar 10 1"],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                cpu_server_data, cpu_server_stderr = cpu_server.communicate()
                cpu_client_data, cpu_client_stderr = cpu_client.communicate()

                if cpu_server.returncode != 0 or cpu_client.returncode != 0:
                    if cpu_server.returncode != 0:
                        print(
                            f"Failed to run `sar 10 1` on {args.host1}: {cpu_server_stderr}"
                        )

                    if cpu_client.returncode != 0:
                        print(
                            f"Failed to run `sar 10 1` on {args.host2}: {cpu_client_stderr}"
                        )

                    return 1

                ib_server.terminate()
                ib_client.terminate()

                ib_server_data, ib_server_stderr = ib_server.communicate()
                ib_client_data, ib_client_stderr = ib_client.communicate()

                if ib_server.returncode != 0 or ib_client.returncode != 0:
                    if ib_server.returncode != 0:
                        print(
                            f"Failed to run IB command on {args.host1}: {ib_server_stderr}"
                        )

                    if ib_client.returncode != 0:
                        print(
                            f"Failed to run IB command on {args.host2}: {ib_client_stderr}"
                        )

                    return 1

                ib_bw_results = list(
                    filter(lambda s: len(s) > 0, ib_client_data.split("\n"))
                )
                bw_avg = ib_bw_results[-1].split()[3]
                bw_msg_rate = ib_bw_results[-1].split()[4]

                cpu_server_avg = (
                    float(
                        list(filter(lambda s: len(s) > 0, cpu_server_data.split("\n")))[
                            -1
                        ].split()[-1]
                    )
                    * host1_cpu_count
                )

                cpu_client_avg = (
                    float(
                        list(filter(lambda s: len(s) > 0, cpu_client_data.split("\n")))[
                            -1
                        ].split()[-1]
                    )
                    * host2_cpu_count
                )

                with (
                    open(
                        f"../data/raw/softroce_multi_vdev/ib_{c}_bw_{args.mode}.txt",
                        "a",
                    ) as bw_file,
                    open(
                        f"../data/raw/softroce_multi_vdev/{c}_cpu_server_{args.mode}.txt",
                        "a",
                    ) as cpu_file_server,
                    open(
                        f"../data/raw/softroce_multi_vdev/{c}_cpu_client_{args.mode}.txt",
                        "a",
                    ) as cpu_file_client,
                ):
                    bw_file.write(f"{pair_count}\t{bw_avg}\t{bw_msg_rate}\n")
                    cpu_file_server.write(f"{pair_count}\t{cpu_server_avg}\n")
                    cpu_file_client.write(f"{pair_count}\t{cpu_client_avg}\n")

        return 0

    for pair_count in PAIRS_COUNT:
        pass

    return 0


parser = argparse.ArgumentParser(
    description="Run multi virtual RDMA device tests on two hosts."
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str)
parser.add_argument("--host2", metavar="HOSTNAME", type=str)
parser.add_argument("--if-name", type=str)
parser.add_argument("--user", metavar="USERNAME", type=str)
parser.add_argument("--mode", type=str, choices=["softroce", "host"])

if __name__ == "__main__":
    try:
        sys.exit(main(parser.parse_args()))
    finally:
        procs = psutil.Process().children()
        for p in procs:
            p.terminate()

        gone, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            p.kill()
