#!/usr/bin/env python3

import argparse
import sys
from os import makedirs, getpid
from subprocess import PIPE, Popen, run
from time import sleep

import psutil

RDMA_SIZE = 65536

CPU_MEASURE_TIME = 10

IB_REPORTING_INTERVAL = 5

IB_COMMANDS = ["read", "write", "send"]

PAIRS_COUNT = list(range(1, 32 + 1))


def main(args: argparse.Namespace) -> int:
    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

    data_dir = f"../data/raw/{args.data_dir}_multi_qp_test"
    makedirs(data_dir, exist_ok=True)

    cli_command = psutil.Process(getpid()).cmdline()
    with open(f"{data_dir}/metadata_{args.data_suffix}", "w") as f:
        f.write(f"host1: {args.host1}\nhost2: {args.host2}\ncommand: {cli_command}")

    host1_cpu_count = run(
        ssh_host_1 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    host2_cpu_count = run(
        ssh_host_2 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    for c in IB_COMMANDS:
        with (
            open(
                f"{data_dir}/ib_{c}_bw_{args.data_suffix}.txt", "w"
            ) as bw_file,
            open(
                f"{data_dir}/{c}_cpu_server_{args.data_suffix}.txt", "w"
            ) as cpu_file_server,
            open(
                f"{data_dir}/{c}_cpu_client_{args.data_suffix}.txt", "w"
            ) as cpu_file_client,
        ):
            bw_file.write("#pairs\tBW average[MB/sec]\tMsgRate[Mpps]\n")
            cpu_file_server.write("#pairs\tCPU Usage %\n")
            cpu_file_client.write("#pairs\tCPU Usage %\n")

    for c in IB_COMMANDS:
        for pair_count in PAIRS_COUNT:
            print(
                f"Running IB command `ib_{c}_bw` with pair_count = {pair_count}..."
            )

            # So turns out SSH won't propagate SIGTERM (especially if you're not allocating a pty),
            # which could leave behind zombie servers. Ensure we nuke them before our tests.
            run(ssh_host_1 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])
            run(ssh_host_2 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])

            ib_server = Popen(
                ssh_host_1
                + [
                    f"ib_{c}_bw -d {args.if_name} -q {pair_count} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE}"
                ],
                text=True,
                stdout=PIPE,
                stderr=PIPE,
            )

            sleep(1)

            ib_client = Popen(
                ssh_host_2
                + [
                    f"ib_{c}_bw -d {args.if_name} -q {pair_count} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE} {args.host1}"
                ],
                text=True,
                stdout=PIPE,
                stderr=PIPE,
            )

            sleep(2)

            if ib_server.returncode is not None or ib_client.returncode is not None:
                if ib_server.returncode is not None:
                    print(
                        f"Failed to start IB command on {args.host1}: {ib_server.communicate()}"
                    )

                if ib_client.returncode is not None:
                    print(
                        f"Failed to start IB command on {args.host2}: {ib_client.communicate()}"
                    )

                return 1

            cpu_server = Popen(
                ssh_host_1 + [f"sar {CPU_MEASURE_TIME} 1"],
                text=True,
                stdout=PIPE,
                stderr=PIPE
            )

            cpu_client = Popen(
                ssh_host_2 + [f"sar {CPU_MEASURE_TIME} 1"],
                text=True,
                stdout=PIPE,
                stderr=PIPE,
            )

            cpu_server.wait(timeout=CPU_MEASURE_TIME + 5)
            cpu_client.wait(timeout=CPU_MEASURE_TIME + 5)

            if cpu_server.returncode != 0 or cpu_client.returncode != 0:
                if cpu_server.returncode != 0:
                    print(f"Failed to get CPU measurements on {args.host1}: {cpu_server.communicate()}")

                if cpu_client.returncode != 0:
                    print(f"Failed to get CPU measurements on {args.host2}: {cpu_client.communicate()}")

                return 1

            cpu_server_data, _ = cpu_server.communicate()
            cpu_client_data, _ = cpu_client.communicate()

            ib_client.terminate()
            ib_server.terminate()

            ib_client_data, _ = ib_client.communicate()
            ib_server.communicate()

            ib_bw_results = list(
                filter(lambda s: len(s) > 0, ib_client_data.split("\n"))
            )
            bw_avg = ib_bw_results[-1].split()[3]
            bw_msg_rate = ib_bw_results[-1].split()[4]

            cpu_server_avg = (
                100
                - float(
                    list(
                        filter(lambda s: len(s) > 0, cpu_server_data.split("\n"))
                    )[-1].split()[-1]
                )
            ) * host1_cpu_count

            cpu_client_avg = (
                100
                - float(
                    list(
                        filter(lambda s: len(s) > 0, cpu_client_data.split("\n"))
                    )[-1].split()[-1]
                )
            ) * host2_cpu_count

            with (
                open(
                    f"{data_dir}/ib_{c}_bw_{args.data_suffix}.txt", "a"
                ) as bw_file,
                open(
                    f"{data_dir}/{c}_cpu_server_{args.data_suffix}.txt", "a"
                ) as cpu_file_server,
                open(
                    f"{data_dir}/{c}_cpu_client_{args.data_suffix}.txt", "a"
                ) as cpu_file_client,
            ):
                bw_file.write(f"{pair_count}\t{bw_avg}\t{bw_msg_rate}\n")
                cpu_file_server.write(f"{pair_count}\t{cpu_server_avg}\n")
                cpu_file_client.write(f"{pair_count}\t{cpu_client_avg}\n")

    return 0


parser = argparse.ArgumentParser(
    description="Run multi QP tests on two hosts."
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str)
parser.add_argument("--host2", metavar="HOSTNAME", type=str)
parser.add_argument("--user", metavar="USERNAME", type=str)
parser.add_argument("--data-dir", type=str, required=True)
parser.add_argument("--data-suffix", type=str, required=True)
parser.add_argument("--if-name", type=str, required=True)

if __name__ == "__main__":
    args = parser.parse_args()
    try:
        sys.exit(main(args))
    finally:
        procs = psutil.Process().children()
        for p in procs:
            p.terminate()

        gone, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            print(f"pid {p} took too long, killing...")
            p.kill()

        # Cleanup any lingering servers that might stick around.
        run(["ssh", f"{args.user}@{args.host1}", "pkill 'ib_(send|read|write)_(bw|lat)'"])
        run(["ssh", f"{args.user}@{args.host2}", "pkill 'ib_(send|read|write)_(bw|lat)'"])
