#!/usr/bin/env python3

import argparse
import sys
from os import getpid, makedirs
from subprocess import PIPE, Popen, run
from time import sleep

import psutil

IB_COMMANDS = [
    "send",
    "read",
    "write",
]

SIZES = [
  2,
  4,
  8,
  16,
  32,
  64,
  128,
  256,
  512,
  1024,
  2048,
  4096,
  8192,
  16384,
  32768,
  65536,
  131072,
  262144,
  524288,
  1048576,
  2097152,
  4194304,
  8388608,
]


def main(args: argparse.Namespace) -> int:
    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

    cli_command = psutil.Process(getpid()).cmdline()
    data_dir = f"../data/raw/{args.data_dir}_cpu_tests"

    makedirs(data_dir, exist_ok=True)
    with open(f"{data_dir}/metadata", "w") as f:
        f.write(f"host1: {args.host1}\nhost2: {args.host2}\ncommand: {cli_command}")

    cmd_prefix = f"{args.wrapper} '" if args.wrapper else ""
    cmd_postfix = "'" if args.wrapper else ""

    host1_cpu_count = run(
        ssh_host_1 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    host2_cpu_count = run(
        ssh_host_2 + ["cat /proc/cpuinfo"], check=True, capture_output=True, text=True
    ).stdout.count("processor\t:")

    for c in IB_COMMANDS:
        cmd = f"ib_{c}_bw{' ' + args.args if args.args else ''}"
        print(f"Running CPU test for `{cmd_prefix}{cmd}{cmd_postfix}`...")

        with open(f"{data_dir}/{c}_cpu_server_{args.data_suffix}.txt", "w") as data_file_server, open(f"{data_dir}/{c}_cpu_client_{args.data_suffix}.txt", "w") as data_file_client:
            data_file_server.write("msg bytes\tcpu util pct\n")
            data_file_client.write("msg bytes\tcpu util pct\n")

            for s in SIZES:
                print(f"  with size {s}...")
                data_file_server.write(f"{s}\t")
                data_file_client.write(f"{s}\t")

                # So turns out SSH won't propagate SIGTERM (especially if you're not allocating a pty),
                # which could leave behind zombie servers. Ensure we nuke them before our tests.
                run(ssh_host_1 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])
                run(ssh_host_2 + ["pkill 'ib_(send|read|write)_(bw|lat)'"])

                ib_server = Popen(
                    ssh_host_1
                    + [f"{cmd_prefix}{cmd} -s {s} -D 10 --run_infinitely{cmd_postfix}"],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                sleep(1)

                ib_client = Popen(
                    ssh_host_2
                    + [
                        f"{cmd_prefix}{cmd} -s {s} -D 10 --run_infinitely {args.host1}{cmd_postfix}"
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
                    ssh_host_1 + [f"sar {args.cpu_measure_time} 1"],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE
                )

                cpu_client = Popen(
                    ssh_host_2 + [f"sar {args.cpu_measure_time} 1"],
                    text=True,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                cpu_server.wait(timeout=args.cpu_measure_time + 5)
                cpu_client.wait(timeout=args.cpu_measure_time + 5)

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

                ib_client.communicate()
                ib_server.communicate()

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

                data_file_server.write(f"{cpu_server_avg}\n")
                data_file_client.write(f"{cpu_client_avg}\n")

    return 0


parser = argparse.ArgumentParser(
    description="Run CPU PCT usage tests with ib_[read|write|send]_bw between two hosts."
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--host2", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--user", metavar="USERNAME", type=str, required=True)
parser.add_argument("--cpu-measure-time", metavar="SECONDS", type=int, required=True)
parser.add_argument("--data-dir", type=str, required=True)
parser.add_argument("--data-suffix", type=str, required=True)
parser.add_argument("--wrapper", type=str)
parser.add_argument("--args", type=str)


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
