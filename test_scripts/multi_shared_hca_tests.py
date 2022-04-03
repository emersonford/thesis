#!/usr/bin/env python3

import argparse
import sys
from os import getpid, makedirs
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

    data_dir = "../data/raw/shared_hca_multi_dev"
    makedirs(data_dir, exist_ok=True)

    cli_command = psutil.Process(getpid()).cmdline()
    with open(f"{data_dir}/metadata", "w") as f:
        f.write(f"host1: {args.host1}\nhost2: {args.host2}\ncommand: {cli_command}")

    host1_cpu_count = run(
        ssh_host_1 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    host2_cpu_count = run(
        ssh_host_2 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    for c in IB_COMMANDS:
        with (
            open(f"{data_dir}/ib_{c}_bw.txt", "w") as bw_file,
            open(f"{data_dir}/{c}_cpu_server.txt", "w") as cpu_file_server,
            open(f"{data_dir}/{c}_cpu_client.txt", "w") as cpu_file_client,
        ):
            bw_file.write(
                "#pairs\tAgg BW average[MB/sec]\tAgg MsgRate[Mpps]\tBW averages[MB/sec]\tMsgRates[Mpps]\n"
            )
            cpu_file_server.write("#pairs\tCPU Usage %\n")
            cpu_file_client.write("#pairs\tCPU Usage %\n")

    for pair_count in PAIRS_COUNT:
        if pair_count == 1:
            print("Checking if the docker network needs to be created...")

            run(
                ssh_host_1
                + [
                    f"docker network ls | grep mynet || docker network create -d macvlan --subnet=192.168.1.0/24 -o parent={args.if_name} -o macvlan_mode=private mynet"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

            run(
                ssh_host_2
                + [
                    f"docker network ls | grep mynet || docker network create -d macvlan --subnet=192.168.1.0/24 -o parent={args.if_name} -o macvlan_mode=private mynet"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

        idx = 0
        while idx < len(IB_COMMANDS):
            c = IB_COMMANDS[idx]
            print(f"Running IB command `ib_{c}_bw` with pair_count = {pair_count}...")

            # So turns out SSH won't propagate SIGTERM (especially if you're not allocating a pty),
            # which could leave behind zombie servers. Ensure we nuke them before our tests.
            run(ssh_host_1 + ["sudo pkill -9 'ib_(send|read|write)_(bw|lat)'"])
            run(ssh_host_2 + ["sudo pkill -9 'ib_(send|read|write)_(bw|lat)'"])

            ib_servers: list[Popen] = []
            ib_clients: list[Popen] = []

            for pnum in range(1, pair_count + 1):
                server_ip = f"192.168.1.{pnum * 2 + 1}"
                client_ip = f"192.168.1.{pnum * 2 + 2}"
                # Need to manually select the GID index since it selects the wrong one by default.
                gid_index = 2 * (pnum - 1) + args.gid_start

                ib_servers.append(
                    Popen(
                        ssh_host_1
                        + [
                            f"docker run --privileged --net=mynet --device=/dev/infiniband --ip {server_ip} rdma-mlnx bash -c 'ib_{c}_bw -d {args.ib_dev} -x {gid_index} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE}'"
                        ],
                        text=True,
                        stdout=PIPE,
                        stderr=PIPE,
                    )
                )

                sleep(0.5)

                ib_clients.append(
                    Popen(
                        ssh_host_2
                        + [
                            f"docker run --privileged --net=mynet --device=/dev/infiniband --ip {client_ip} rdma-mlnx bash -c 'ib_{c}_bw -d {args.ib_dev} -x {gid_index} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE} {server_ip}'"
                        ],
                        text=True,
                        stdout=PIPE,
                        stderr=PIPE,
                    )
                )

                sleep(0.5)

                if (
                    ib_servers[-1].returncode is not None
                    or ib_clients[-1].returncode is not None
                ):
                    if ib_servers[-1].returncode is not None:
                        print(
                            f"Failed to start IB command on {args.host1}: {ib_servers[-1].communicate()}"
                        )

                    if ib_clients[-1].returncode is not None:
                        print(
                            f"Failed to start IB command on {args.host2}: {ib_clients[-1].communicate()}"
                        )

                    return 1

            cpu_server = Popen(
                ssh_host_1 + [f"sar {CPU_MEASURE_TIME} 1"],
                text=True,
                stdout=PIPE,
                stderr=PIPE,
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
                    print(
                        f"Failed to get CPU measurements on {args.host1}: {cpu_server.communicate()}"
                    )

                if cpu_client.returncode != 0:
                    print(
                        f"Failed to get CPU measurements on {args.host2}: {cpu_client.communicate()}"
                    )

                return 1

            cpu_server_data, _ = cpu_server.communicate()
            cpu_client_data, _ = cpu_client.communicate()

            ib_clients_data: list[str] = []

            for cl in ib_clients:
                cl.terminate()
                ib_clients_data.append(cl.communicate()[0])

            for s in ib_servers:
                s.terminate()

            run(ssh_host_1 + ["sudo pkill -9 'ib_(send|read|write)_(bw|lat)'"])
            run(ssh_host_2 + ["sudo pkill -9 'ib_(send|read|write)_(bw|lat)'"])

            ib_multi_bw_results = list(
                map(
                    lambda data: list(filter(lambda s: len(s) > 0, data.split("\n"))),
                    ib_clients_data,
                )
            )

            try:
                bw_avgs = ",".join(
                    str(res[-1].split()[3]) for res in ib_multi_bw_results
                )
                bw_agg_avg = sum(
                    float(res[-1].split()[3]) for res in ib_multi_bw_results
                )

                bw_msg_rates = ",".join(
                    str(res[-1].split()[4]) for res in ib_multi_bw_results
                )
                bw_agg_msg_rate = sum(
                    float(res[-1].split()[4]) for res in ib_multi_bw_results
                )
            except IndexError:
                print("Error, retrying...")
                continue

            cpu_server_avg = (
                100
                - float(
                    list(filter(lambda s: len(s) > 0, cpu_server_data.split("\n")))[
                        -1
                    ].split()[-1]
                )
            ) * host1_cpu_count

            cpu_client_avg = (
                100
                - float(
                    list(filter(lambda s: len(s) > 0, cpu_client_data.split("\n")))[
                        -1
                    ].split()[-1]
                )
            ) * host2_cpu_count

            with (
                open(f"{data_dir}/ib_{c}_bw.txt", "a") as bw_file,
                open(f"{data_dir}/{c}_cpu_server.txt", "a") as cpu_file_server,
                open(f"{data_dir}/{c}_cpu_client.txt", "a") as cpu_file_client,
            ):
                bw_file.write(
                    f"{pair_count}\t{bw_agg_avg}\t{bw_agg_msg_rate}\t{bw_avgs}\t{bw_msg_rates}\n"
                )
                cpu_file_server.write(f"{pair_count}\t{cpu_server_avg}\n")
                cpu_file_client.write(f"{pair_count}\t{cpu_client_avg}\n")

            idx += 1

    return 0


parser = argparse.ArgumentParser(
    description="""
Run multi shared HCA RDMA device tests on two hosts.

This assumes the docker network has been configured. This can be done with docker network create -d macvlan --subnet=192.168.1.0/24 -o parent=ens3f0 -o macvlan_mode=private mynet. This also assumes the RoCE NIC is on subnet 192.168.1.0/24.
"""
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--host2", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--user", metavar="USERNAME", type=str, required=True)
parser.add_argument("--if-name", type=str, required=True)
parser.add_argument("--ib-dev", type=str, required=True)
parser.add_argument("--gid-start", type=int, required=True)

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
        run(
            [
                "ssh",
                f"{args.user}@{args.host1}",
                "sudo pkill -9 'ib_(send|read|write)_(bw|lat)'",
            ]
        )
        run(
            [
                "ssh",
                f"{args.user}@{args.host2}",
                "sudo pkill -9 'ib_(send|read|write)_(bw|lat)'",
            ]
        )
