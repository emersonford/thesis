#!/usr/bin/env python3

import argparse
import shlex
import sys
from os import getpid, makedirs
from subprocess import DEVNULL, Popen, run
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
        cmd = f"{c}{' ' + args.args if args.args else ''}"
        print(f"Running `{cmd_prefix}{cmd}{cmd_postfix}`...")

        ib_server = Popen(
            " ".join(
                ssh_host_1
                + [
                    shlex.quote(
                        f"{cmd_prefix}{cmd}{cmd_postfix}".format(client_id=1)
                    )
                ]
            ),
            text=True,
            stdout=DEVNULL,
            stderr=DEVNULL,
            shell=True,
        )

        sleep(args.sleep)

        ib_client = run(
            " ".join(
                ssh_host_2
                + [
                    shlex.quote(
                        f"{cmd_prefix}{cmd} {args.server_ip}{cmd_postfix}".format(
                            client_id=2
                        )
                    )
                ]
            ),
            capture_output=True,
            text=True,
            check=True,
            shell=True,
        )

        ib_server.wait(timeout=15)

        print(ib_client.stdout)

        with open(f"{data_dir}/{c}_{args.data_suffix}.txt", "w") as f:
            f.write(ib_client.stdout)

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
