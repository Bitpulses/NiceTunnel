#!/usr/bin/env python3
"""NiceTunnel - A Nice and Elegant SSH Port Forwarding Tool

Forward ports from cluster compute nodes to your local machine via SSH tunnel.

Usage:
    python main.py --ssh-host 10.0.0.1 --ssh-user root \
        --forward 192.168.1.100:80 -> 8080 \
        --forward 192.168.1.101:3306 -> 3306

    python main.py -H jumpserver.example.com -u admin -p 22 \
        -f 10.0.0.50:8888>9999 -f 10.0.0.51:22>2222
"""

import argparse
import logging
import os
import socket
import sys
import time
import threading
from dataclasses import dataclass
from typing import List, Optional

import paramiko

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("NiceTunnel")


# Data model
@dataclass
class ForwardRule:
    """A single port-forwarding rule."""
    remote_host: str        # Target node IP inside the cluster
    remote_port: int        # Target port on the remote node
    local_host: str         # Local address to bind
    local_port: int         # Local port to listen on

    @property
    def label(self) -> str:
        return f"{self.local_host}:{self.local_port} -> {self.remote_host}:{self.remote_port}"


# Argument parsing
def parse_forward_spec(spec: str) -> ForwardRule:
    """
    Parse a forwarding specification string.

    Supported formats:
        "192.168.1.100:80 -> 8080"
        "192.168.1.100:80>8080"
        "10.0.0.50:8888>127.0.0.1:9999"
    """
    spec = spec.strip()
    if "->" in spec:
        remote_part, local_part = spec.split("->", 1)
    elif ">" in spec:
        remote_part, local_part = spec.split(">", 1)
    else:
        raise ValueError(
            f"Unable to parse forward spec '{spec}'. "
            f"Expected format: remote_host:port>local_port"
        )

    remote_part = remote_part.strip()
    local_part = local_part.strip()

    if ":" not in remote_part:
        raise ValueError(
            f"Invalid remote address '{remote_part}'. Expected host:port"
        )
    remote_host, remote_port_str = remote_part.rsplit(":", 1)
    try:
        remote_port = int(remote_port_str)
    except ValueError:
        raise ValueError(f"Invalid remote port '{remote_port_str}'")

    # Local part: "port" or "host:port"
    if ":" in local_part:
        local_host, local_port_str = local_part.rsplit(":", 1)
    else:
        local_host = "0.0.0.0"
        local_port_str = local_part
    try:
        local_port = int(local_port_str)
    except ValueError:
        raise ValueError(f"Invalid local port '{local_port_str}'")

    return ForwardRule(
        remote_host=remote_host,
        remote_port=remote_port,
        local_host=local_host,
        local_port=local_port,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NiceTunnel - SSH port forwarding tool for cluster compute nodes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Forward port 80 of cluster node 192.168.1.100 to local port 8080
  python main.py -H bastion.example.com -u root -f "192.168.1.100:80->8080"

  # Forward multiple ports simultaneously
  python main.py -H 10.0.0.1 -u admin --key ~/.ssh/id_rsa \\
      -f "node01:3306->3306" \\
      -f "node02:6379->6379" \\
      -f "node03:8080->8888"

  # Bind to localhost only instead of all interfaces
  python main.py -H gw -u ops -f "db.internal:5432->127.0.0.1:5432"
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

    # Forwarding rules
    parser.add_argument(
        "-f", "--forward", action="append", dest="forward_specs", default=[],
        help="Port forwarding rule. Format: remote_host:remote_port>local_host:local_port "
             "(local_host is optional, defaults to 0.0.0.0). "
             "Can be specified multiple times for multiple rules.",
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


# Core tunnel logic
class TunnelManager:
    """Manages the SSH connection and all port-forwarding tunnels."""

    def __init__(self, args):
        self.args = args
        self.client: Optional[paramiko.SSHClient] = None
        self.rules: List[ForwardRule] = []
        self._stop_event = threading.Event()
        self._reconnect_delay = 5  # Seconds between reconnection attempts

    # SSH connection 
    def _connect_ssh(self) -> paramiko.SSHClient:
        """Establish an SSH connection to the bastion host."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Determine authentication method
        pkey = None
        password = self.args.ssh_password

        if self.args.ssh_key_file:
            # User specified a key file
            pkey_path = os.path.expanduser(self.args.ssh_key_file)
            if not os.path.isfile(pkey_path):
                raise FileNotFoundError(f"SSH key file not found: {pkey_path}")
            pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
        elif password is None:
            # Try default keys
            for default_key in ["~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/id_ecdsa"]:
                pkey_path = os.path.expanduser(default_key)
                if os.path.isfile(pkey_path):
                    try:
                        pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
                        log.info("Using default key: %s", pkey_path)
                        break
                    except Exception:
                        continue

        if pkey is None and password is None:
            # Try SSH agent
            try:
                agent = paramiko.Agent()
                agent_keys = agent.get_keys()
                if agent_keys:
                    pkey = agent_keys[0]
                    log.info("Using SSH agent key")
            except Exception:
                pass

        connect_kwargs = {
            "hostname": self.args.ssh_host,
            "port": self.args.ssh_port,
            "username": self.args.ssh_user,
            "timeout": 15,
            "banner_timeout": 15,
        }
        if pkey:
            connect_kwargs["pkey"] = pkey
        if password:
            connect_kwargs["password"] = password

        log.info("Connecting to SSH: %s@%s:%d ...",
                 self.args.ssh_user, self.args.ssh_host, self.args.ssh_port)
        client.connect(**connect_kwargs)

        # Enable keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(self.args.keepalive)
            log.info("SSH connected (keepalive=%ds)", self.args.keepalive)

        return client

    #Forwarding
    def _start_forward(self, rule: ForwardRule) -> Optional[threading.Thread]:
        """Start port forwarding for a single rule."""
        transport = self.client.get_transport()
        if transport is None:
            log.error("SSH transport unavailable, cannot forward %s", rule.label)
            return None

        # Use Paramiko's direct-tcpip channel for port forwarding
        def forward_worker():
            log.info("[START] %s", rule.label)
            server_socket = None
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((rule.local_host, rule.local_port))
                server_socket.listen(128)
                server_socket.settimeout(1.0)  # Check stop signal every second
            except OSError as e:
                log.error("Failed to bind %s:%d - %s", rule.local_host, rule.local_port, e)
                return

            log.info("[LISTEN] %s", rule.label)

            while not self._stop_event.is_set():
                try:
                    client_sock, addr = server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                log.debug("New connection from %s -> %s", addr, rule.label)
                t = threading.Thread(
                    target=self._handle_forward_connection,
                    args=(client_sock, rule),
                    daemon=True,
                )
                t.start()

            server_socket.close()
            log.info("[STOP] %s", rule.label)

        thread = threading.Thread(target=forward_worker, daemon=True, name=rule.label)
        thread.start()
        return thread

    def _handle_forward_connection(
        self, local_sock: socket.socket, rule: ForwardRule
    ):
        """Handle a single forwarded connection: local -> SSH tunnel -> remote target."""
        transport = self.client.get_transport()
        if transport is None or not transport.is_active():
            log.error("SSH transport unavailable, dropping connection %s", rule.label)
            try:
                local_sock.close()
            except Exception:
                pass
            return

        try:
            # Open a channel through the SSH tunnel to the remote target
            chan = transport.open_channel(
                "direct-tcpip",
                (rule.remote_host, rule.remote_port),
                local_sock.getpeername(),
            )
        except Exception as e:
            log.error(
                "Failed to create tunnel to %s:%d - %s",
                rule.remote_host, rule.remote_port, e
            )
            try:
                local_sock.close()
            except Exception:
                pass
            return

        if chan is None:
            log.error("Tunnel creation failed %s:%d", rule.remote_host, rule.remote_port)
            try:
                local_sock.close()
            except Exception:
                pass
            return

        # Bidirectional data forwarding
        threading.Thread(
            target=self._pipe,
            args=(local_sock, chan),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe,
            args=(chan, local_sock),
            daemon=True,
        ).start()

    @staticmethod
    def _pipe(src, dst):
        """Bidirectionally copy data between two sockets."""
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try:
                src.close()
            except Exception:
                pass
            try:
                dst.close()
            except Exception:
                pass

    # Lifecycle
    def start(self):
        """Start the tunnel manager: connect SSH and launch all forwarding rules."""
        self.client = self._connect_ssh()
        self.rules = [parse_forward_spec(s) for s in self.args.forward_specs]

        if not self.rules:
            log.error("No forwarding rules specified. Use -f to add one.")
            sys.exit(1)

        log.info("%d forwarding rule(s):", len(self.rules))
        for r in self.rules:
            log.info("  %s", r.label)

        self._threads: List[threading.Thread] = []
        for rule in self.rules:
            t = self._start_forward(rule)
            if t:
                self._threads.append(t)

        if not self._threads:
            log.error("Failed to start any forwarding rule")
            sys.exit(1)

        log.info("All tunnels ready. Press Ctrl+C to exit...")

    def stop(self):
        """Gracefully shut down all tunnels and the SSH connection."""
        log.info("Shutting down all tunnels...")
        self._stop_event.set()

        # Wait for all forwarding threads to exit
        for t in getattr(self, "_threads", []):
            t.join(timeout=3)

        # Close SSH connection
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        log.info("All tunnels closed.")

    def run(self):
        """Block and run until a stop signal is received."""
        try:
            while not self._stop_event.is_set():
                # Monitor SSH connection health
                transport = self.client.get_transport() if self.client else None
                if transport is None or not transport.is_active():
                    log.warning(
                        "SSH connection lost, reconnecting in %ds...",
                        self._reconnect_delay,
                    )
                    time.sleep(self._reconnect_delay)
                    try:
                        self.client = self._connect_ssh()
                        log.info("Reconnected, tunnels restored.")
                    except Exception as e:
                        log.error("Reconnection failed: %s", e)
                        continue

                self._stop_event.wait(timeout=10)
        except KeyboardInterrupt:
            log.info("Interrupt signal received")
        finally:
            self.stop()


# Main entry
def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.forward_specs:
        parser.print_help()
        print("\nError: at least one forward rule (-f) is required")
        sys.exit(1)

    manager = TunnelManager(args)
    manager.start()
    manager.run()


if __name__ == "__main__":
    main()
