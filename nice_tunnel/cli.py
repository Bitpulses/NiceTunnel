"""Command-line argument parsing for NiceTunnel."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NiceTunnel - SSH port forwarding tool (Local / Remote / Dynamic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local forwarding: access cluster node's port 80 via local port 8080
  python NiceTunnel.py -H bastion.example.com -u root -L 8080:192.168.1.100:80

  # Multiple local forwards at once
  python NiceTunnel.py -H 10.0.0.1 -u admin --key ~/.ssh/id_rsa \\
      -L 3306:node01:3306  \\
      -L 6379:node02:6379  \\
      -L 8888:node03:8080

  # Bind to localhost only
  python NiceTunnel.py -H gw -u ops -L 127.0.0.1:5432:db.internal:5432

  # Remote forwarding: expose local port 3306 on the SSH server's port 13306
  python NiceTunnel.py -H jumper -u root -R 13306:localhost:3306

  # Dynamic SOCKS5 proxy on local port 1080
  python NiceTunnel.py -H jumper -u root -D 1080

  # Mix all three modes
  python NiceTunnel.py -H jumper -u root \\
      -L 8080:internal:80 \\
      -R 2222:localhost:22 \\
      -D 127.0.0.1:1080
        """,
    )

    # SSH connection parameters
    parser.add_argument(
        "-H", "--ssh-host", required=True,
        help="SSH bastion/jump host address",
    )
    parser.add_argument(
        "-p", "--ssh-port", type=int, default=22,
        help="SSH port (default: 22)",
    )
    parser.add_argument(
        "-u", "--ssh-user", required=True,
        help="SSH username",
    )
    parser.add_argument(
        "--key", dest="ssh_key_file", default=None,
        help="Path to SSH private key file (default: try ~/.ssh/id_rsa)",
    )
    parser.add_argument(
        "--password", dest="ssh_password", default=None,
        help="SSH password (not recommended; prefer key-based auth)",
    )

    # Forwarding rules — three modes + legacy alias

    local_help = (
        "Local port forwarding (-L). "
        "Format: [bind_host:]port:remote_host:remote_port. "
        "Can be specified multiple times."
    )
    parser.add_argument(
        "-L", "--local-forward",
        action="append", dest="local_forwards", default=[],
        metavar="SPEC", help=local_help,
    )

    remote_help = (
        "Remote port forwarding (-R). "
        "Format: [bind_host:]port:local_host:local_port. "
        "SSH server listens on bind_host:port and forwards to local_host:local_port."
    )
    parser.add_argument(
        "-R", "--remote-forward",
        action="append", dest="remote_forwards", default=[],
        metavar="SPEC", help=remote_help,
    )

    dynamic_help = (
        "Dynamic / SOCKS5 forwarding (-D). "
        "Format: [bind_host:]port. "
        "Starts a SOCKS5 proxy on the local side."
    )
    parser.add_argument(
        "-D", "--dynamic-forward",
        action="append", dest="dynamic_forwards", default=[],
        metavar="SPEC", help=dynamic_help,
    )

    legacy_help = (
        "Legacy forwarding alias (equivalent to -L). "
        "Format: remote_host:remote_port>[local_host:]local_port. "
        "Kept for backward compatibility."
    )
    parser.add_argument(
        "-f", "--forward",
        action="append", dest="legacy_forwards", default=[],
        metavar="SPEC", help=legacy_help,
    )

    # Miscellaneous options
    parser.add_argument(
        "-k", "--keepalive", type=int, default=30,
        help="SSH keepalive interval in seconds (default: 30)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose (debug) output",
    )

    return parser
