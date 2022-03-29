#!/usr/bin/env python3

import argparse
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

    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

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
            ssh_host_1 + [f"{cmd_prefix}{cmd}{cmd_postfix}".format(ip=args.server_ip)],
            text=True,
            stdout=DEVNULL,
            stderr=DEVNULL,
        )

        sleep(0.5)

        ib_client = run(
            ssh_host_2
            + [
                f"{cmd_prefix}{cmd} {args.server_ip}{cmd_postfix}".format(
                    ip=args.client_ip
                )
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        ib_server.wait(timeout=15)

        print(ib_client.stdout)

        with open(f"{data_dir}/{c}_{args.data_suffix}.txt", "w") as f:
            f.write(ib_client.stdout)

        sleep(1)

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
