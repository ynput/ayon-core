
"""Executing the shell scripts via Zscript"""
import os
from aiohttp_json_rpc import JsonRpcClient
import asyncio
import argparse


async def host_tools_widget(launcher_type=None):
    """Connect to WEBSOCKET_URL, call ping() and disconnect."""
    rpc_client = JsonRpcClient()
    ws_port = os.environ["WEBSOCKET_URL"].split(":")[-1]
    try:
        await rpc_client.connect('localhost', ws_port)
        await rpc_client.call(launcher_type)
    finally:
        await rpc_client.disconnect()


def run_with_zscript(launcher_type):
    return asyncio.run(host_tools_widget(launcher_type))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calling Ayon plugins.")
    parser.add_argument(
        "launchertype", type=str,
        help='Arguments to call the launchers')
    args = parser.parse_args()
    if args.launchertype:
        run_with_zscript(args.launchertype)
