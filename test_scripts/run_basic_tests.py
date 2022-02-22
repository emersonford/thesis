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
    ssh_host_1 = ["ssh", f"{args.user}@{args.host1}"]
    ssh_host_2 = ["ssh", f"{args.user}@{args.host2}"]

    cli_command = psutil.Process(getpid()).cmdline()

    makedirs(f"../data/raw/{args.data_dir}", exist_ok=True)
    with open(f"../data/raw/{args.data_dir}/metadata", "w") as f:
        f.write(f"host1: {args.host1}\nhost2: {args.host2}\ncommand: {cli_command}")

    cmd_prefix = f"{args.wrapper} '" if args.wrapper else ""
    cmd_postfix = "'" if args.wrapper else ""

    for c in IB_COMMANDS:
        print(f"Running {c}{' ' + args.args if args.args else ' '}...")

        ib_server = Popen(
            ssh_host_1
            + [f"{cmd_prefix}{c} {args.args if args.args else ''}{cmd_postfix}"],
            text=True,
            stdout=DEVNULL,
            stderr=DEVNULL,
        )

        sleep(1)

        ib_client = run(
            ssh_host_2
            + [
                f"{cmd_prefix}{c}{' ' + args.args if args.args else ' '} {args.host1}{cmd_postfix}"
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        ib_server.wait(timeout=15)

        print(ib_client.stdout)

        with open(f"../data/raw/{args.data_dir}/{c}_{args.data_suffix}.txt", "w") as f:
            f.write(ib_client.stdout)

        sleep(1)

    return 0


parser = argparse.ArgumentParser(
    description="Run basic ib_[read|write|send]_[lat|bw] tests between two hosts."
)
parser.add_argument("--host1", metavar="HOSTNAME", type=str, required=True)
parser.add_argument("--host2", metavar="HOSTNAME", type=str, required=True)
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