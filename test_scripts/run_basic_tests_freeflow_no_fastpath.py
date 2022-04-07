#!/usr/bin/env python3
# Freeflow Fastpath can't complete `ib_*_* -a` so we need to run each size iteratively.

import argparse
import shlex
import sys
from os import getpid, makedirs
from subprocess import DEVNULL, Popen, TimeoutExpired, run
from time import sleep

import psutil

IB_COMMANDS = [
    "ib_read_lat",
    "ib_write_lat",
    "ib_send_lat",
    "ib_read_bw",
    "ib_write_bw",
    "ib_send_bw",
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
]

# Sometimes no-fastpath gets wedged so we need to reset the client.
def reset(args: argparse.Namespace) -> None:
    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

    run(
        ssh_host_1
        + ["docker kill router1 node1 || true; ./Freeflow/start-containers.sh"],
        check=True,
    )
    run(
        ssh_host_2
        + ["docker kill router1 node1 || true; ./Freeflow/start-containers.sh"],
        check=True,
    )
    sleep(1)


def main(args: argparse.Namespace) -> int:
    if not args.server_ip:
        args.server_ip = args.host1

    if not args.client_ip:
        args.client_ip = args.host2

    ssh_host_1 = ["ssh", "-t", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", "-t", f"{args.user}@{args.host2}"]

    cli_command = psutil.Process(getpid()).cmdline()
    data_dir = f"../data/raw/{args.data_dir}_basic_tests"

    makedirs(data_dir, exist_ok=True)
    with open(f"{data_dir}/metadata_{args.data_suffix}", "w") as f:
        f.write(f"host1: {args.host1}\nhost2: {args.host2}\ncommand: {cli_command}")

    cmd_prefix = f"{args.wrapper} '" if args.wrapper else ""
    cmd_postfix = "'" if args.wrapper else ""

    for c in IB_COMMANDS:
        print()

        idx = 0
        output = ""
        while idx < len(SIZES):
            s = SIZES[idx]
            cmd = f"{c} --size={s}{' ' + args.args if args.args else ''}"
            print(f"Running `{cmd_prefix}{cmd}{cmd_postfix}`...")

            ib_server = Popen(
                " ".join(
                    ssh_host_1
                    + [
                        shlex.quote(
                            f"{cmd_prefix}{cmd}{cmd_postfix}".format(ip=args.server_ip)
                        )
                    ]
                ),
                text=True,
                stdout=DEVNULL,
                stderr=DEVNULL,
                shell=True,
            )

            sleep(args.sleep)

            try:
                ib_client = run(
                    " ".join(
                        ssh_host_2
                        + [
                            shlex.quote(
                                f"{cmd_prefix}{cmd} {args.server_ip}{cmd_postfix}".format(
                                    ip=args.client_ip
                                )
                            )
                        ]
                    ),
                    capture_output=True,
                    text=True,
                    check=True,
                    shell=True,
                    timeout=args.timeout,
                )
            except TimeoutExpired:
                print(
                    "Something is wedged, resetting server and client and trying again..."
                )
                reset(args)
                continue

            ib_server.wait(timeout=args.timeout)

            cl_stdout = ib_client.stdout
            lines = cl_stdout.split("\n")

            while lines[-1].strip() == "":
                lines = lines[:-1]

            if idx == 0:
                output += "\n".join(
                    (lines[:-1] if lines[-1].startswith("----") else lines)
                )
            else:
                output += "\n" + lines[-2] if lines[-1].startswith("----") else lines[-1]

            print(output)
            idx += 1

        output += "\n---------------------------------------------------------------------------------------"
        with open(f"{data_dir}/{c}_{args.data_suffix}.txt", "w") as f:
            f.write(output)

        sleep(args.sleep)

    return 0


parser = argparse.ArgumentParser(
    description="Run basic ib_[read|write|send]_[lat|bw] tests between two hosts."
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--host2", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--server-ip", metavar="IP", type=str)
parser.add_argument("--client-ip", metavar="IP", type=str)
parser.add_argument("--user", metavar="USERNAME", type=str, required=True)
parser.add_argument("--data-dir", type=str, required=True)
parser.add_argument("--data-suffix", type=str, required=True)
parser.add_argument("--wrapper", type=str)
parser.add_argument("--args", type=str)
parser.add_argument("--sleep", type=int, default=1)
parser.add_argument("--timeout", type=int, default=15)


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
            p.kill()
