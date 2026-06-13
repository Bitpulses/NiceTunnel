"""
    NiceTunnel - A Nice and Elegant SSH Port Forwarding Tool

    Supports Local (-L), Remote (-R), and Dynamic/SOCKS5 (-D) forwarding.

    Usage:
        # Local forwarding
        python NiceTunnel.py -H jumper -u root -L 8080:internal:80

        # Remote forwarding
        python NiceTunnel.py -H jumper -u root -R 13306:localhost:3306

        # SOCKS5 proxy
        python NiceTunnel.py -H jumper -u root -D 1080

        # Mix all modes
        python NiceTunnel.py -H jumper -u root \\
            -L 8080:internal:80 -R 2222:localhost:22 -D 1080
"""

import logging
import sys

from nice_tunnel.cli import build_parser
from nice_tunnel.manager import TunnelManager

# Top-level logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # At least one forwarding spec must be provided across all flags
    has_any = any([
        args.local_forwards,
        args.remote_forwards,
        args.dynamic_forwards,
        args.legacy_forwards,
    ])
    if not has_any:
        parser.print_help()
        print("\nError: at least one forwarding rule (-L / -R / -D / -f) is required")
        sys.exit(1)

    manager = TunnelManager(args)
    manager.start()
    manager.run()


if __name__ == "__main__":
    main()
