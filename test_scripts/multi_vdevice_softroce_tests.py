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

    data_dir = "../data/raw/softroce_multi_vdev"
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
            open(
                f"{data_dir}/ib_{c}_bw.txt", "w"
            ) as bw_file,
            open(
                f"{data_dir}/{c}_cpu_server.txt", "w"
            ) as cpu_file_server,
            open(
                f"{data_dir}/{c}_cpu_client.txt", "w"
            ) as cpu_file_client,
        ):
            bw_file.write(
                "#pairs\tAgg BW average[MB/sec]\tAgg MsgRate[Mpps]\tBW averages[MB/sec]\tMsgRates[Mpps]\n"
            )
            cpu_file_server.write("#pairs\tCPU Usage %\n")
            cpu_file_client.write("#pairs\tCPU Usage %\n")

    for pair_count in PAIRS_COUNT:
        if pair_count == 1:
            print("Creating SoftRoCE device rxe0...")

            run(
                ssh_host_1
                + [
                    "sudo bash -c 'for i in /sys/devices/system/cpu/cpu*/cpuidle/state*/disable; do echo 1 > $i; done'"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

            run(
                ssh_host_1
                + [
                    f"sudo rdma link | grep rxe0 || sudo rdma link add rxe0 type rxe netdev {args.if_name} && sudo devlink dev param set pci/{args.pcie_id} name enable_roce value false cmode driverinit && sudo devlink dev reload pci/{args.pcie_id}"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

            run(
                ssh_host_2
                + [
                    "sudo bash -c 'for i in /sys/devices/system/cpu/cpu*/cpuidle/state*/disable; do echo 1 > $i; done'"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

            run(
                ssh_host_2
                + [
                    f"sudo rdma link | grep rxe0 || sudo rdma link add rxe0 type rxe netdev {args.if_name} && sudo devlink dev param set pci/{args.pcie_id} name enable_roce value false cmode driverinit && sudo devlink dev reload pci/{args.pcie_id}"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

        elif pair_count > 1:
            rxe_iface_id = pair_count - 1
            print(f"Creating SoftRoCE device rxe{rxe_iface_id}...")

            run(
                ssh_host_1
                + [
                    f"sudo ip link add macvlan{rxe_iface_id} link {args.if_name} type macvlan mode private && sudo ip addr add 192.168.1.{pair_count * 2 - 1}/24 dev macvlan{rxe_iface_id} && sudo ip link set macvlan{rxe_iface_id} up && sudo rdma link add rxe{rxe_iface_id} type rxe netdev macvlan{rxe_iface_id}"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

            run(
                ssh_host_2
                + [
                    f"sudo ip link add macvlan{rxe_iface_id} link {args.if_name} type macvlan mode private && sudo ip addr add 192.168.1.{pair_count * 2}/24 dev macvlan{rxe_iface_id} && sudo ip link set macvlan{rxe_iface_id} up && sudo rdma link add rxe{rxe_iface_id} type rxe netdev macvlan{rxe_iface_id}"
                ],
                text=True,
                check=True,
                capture_output=True,
            )

        for c in IB_COMMANDS:
            print(
                f"Running IB command `ib_{c}_bw` with pair_count = {pair_count}..."
            )

            # So turns out SSH won't propagate SIGTERM (especially if you're not allocating a pty),
            # which could leave behind zombie servers. Ensure we nuke them before our tests.
            run(ssh_host_1 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])
            run(ssh_host_2 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])

            ib_servers: list[Popen] = []
            ib_clients: list[Popen] = []

            for pnum in range(1, pair_count + 1):
                ib_servers.append(
                    Popen(
                        ssh_host_1
                        + [
                            f"ib_{c}_bw -d rxe{pnum - 1} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE}"
                        ],
                        text=True,
                        stdout=PIPE,
                        stderr=PIPE,
                    )
                )

                sleep(1)

                ib_clients.append(
                    Popen(
                        ssh_host_2
                        + [
                            f"ib_{c}_bw -d rxe{pnum - 1} -D {IB_REPORTING_INTERVAL} --run_infinitely -s {RDMA_SIZE} {args.host1}"
                        ],
                        text=True,
                        stdout=PIPE,
                        stderr=PIPE,
                    )
                )

                sleep(1)

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

            ib_clients_data: list[str] = []

            for cl in ib_clients:
                cl.terminate()
                ib_clients_data.append(cl.communicate()[0])

            for s in ib_servers:
                s.terminate()

            run(ssh_host_1 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])
            run(ssh_host_2 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])

            ib_multi_bw_results = list(
                map(
                    lambda data: list(
                        filter(lambda s: len(s) > 0, data.split("\n"))
                    ),
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
                print(ib_multi_bw_results)

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
                    f"{data_dir}/ib_{c}_bw.txt", "a"
                ) as bw_file,
                open(
                    f"{data_dir}/{c}_cpu_server.txt", "a"
                ) as cpu_file_server,
                open(
                    f"{data_dir}/{c}_cpu_client.txt", "a"
                ) as cpu_file_client,
            ):
                bw_file.write(
                    f"{pair_count}\t{bw_agg_avg}\t{bw_agg_msg_rate}\t{bw_avgs}\t{bw_msg_rates}\n"
                )
                cpu_file_server.write(f"{pair_count}\t{cpu_server_avg}\n")
                cpu_file_client.write(f"{pair_count}\t{cpu_client_avg}\n")

    return 0


parser = argparse.ArgumentParser(
    description="""
Run multi virtual RDMA device tests on two hosts.

This assumes the first SoftRoCE device has already been setup on both hosts. This can be done with:
1. Uninstall MLNX_OFED and install `rdma-core` and `perftest`.
2. `sudo modprobe -rv mlx5_ib` and reboot.
"""
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str)
parser.add_argument("--host2", metavar="HOSTNAME", type=str)
parser.add_argument("--user", metavar="USERNAME", type=str)
parser.add_argument("--if-name", type=str)
parser.add_argument("--pcie_id", type=str)

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
