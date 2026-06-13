"""TunnelManager — orchestrates SSH connection and port forwarding lifecycle."""

import logging
import sys
import threading
import time
from typing import List

from nice_tunnel.models import (
    ForwardRule,
    parse_local_rules,
    parse_remote_rules,
    parse_dynamic_rules,
    parse_legacy_rules,
)
from nice_tunnel.ssh_client import SSHConnector
from nice_tunnel.tunnel_engine import TunnelEngine

log = logging.getLogger(__name__)


class TunnelManager:
    """Manages the SSH connection and all port-forwarding tunnels."""

    def __init__(self, args):
        self.args = args
        self.client = None
        self.rules: List[ForwardRule] = []
        self._stop_event = threading.Event()
        self._reconnect_delay = 5
        self._threads: List[threading.Thread] = []

        # Sub-components are created lazily so they always see the latest client
        self._ssh: SSHConnector | None = None
        self._engine: TunnelEngine | None = None

    # Lifecycle

    def start(self):
        """Connect SSH and launch all forwarding rules."""
        # Collect rules from all forwarding flags
        self.rules = self._collect_rules()
        if not self.rules:
            log.error("No forwarding rules specified.")
            log.error("Use -L, -R, -D, or -f to add at least one.")
            sys.exit(1)

        log.info("%d forwarding rule(s):", len(self.rules))
        for r in self.rules:
            log.info("  %s", r.label)

        # Connect SSH
        self._ssh = SSHConnector(
            host=self.args.ssh_host,
            port=self.args.ssh_port,
            username=self.args.ssh_user,
            key_file=self.args.ssh_key_file,
            password=self.args.ssh_password,
            keepalive=self.args.keepalive,
        )
        self.client = self._ssh.connect()

        # Create engine (transport provider always returns current transport)
        self._engine = TunnelEngine(
            transport_provider=lambda: self.client.get_transport() if self.client else None
        )

        # Start all forwarding threads
        for rule in self.rules:
            t = self._engine.start_forward(rule, self._stop_event)
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
        for t in self._threads:
            t.join(timeout=3)

        # Close SSH connection
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        log.info("All tunnels closed.")

    def run(self):
        """Block and run until a stop signal is received.

        Monitors SSH health and attempts reconnection on disconnect.
        Local/Dynamic listeners survive reconnects because their sockets
        are bound independently. Remote forwards are re-requested
        automatically by the remote worker loop.
        """
        try:
            while not self._stop_event.is_set():
                transport = self.client.get_transport() if self.client else None
                if transport is None or not transport.is_active():
                    log.warning(
                        "SSH connection lost, reconnecting in %ds...",
                        self._reconnect_delay,
                    )
                    time.sleep(self._reconnect_delay)
                    try:
                        assert self._ssh is not None
                        self.client = self._ssh.connect()
                        log.info("Reconnected, tunnels restored.")
                    except Exception as e:
                        log.error("Reconnection failed: %s", e)
                        continue

                self._stop_event.wait(timeout=10)
        except KeyboardInterrupt:
            log.info("Interrupt signal received")
        finally:
            self.stop()

    # Rule collection

    def _collect_rules(self) -> List[ForwardRule]:
        """Gather forwarding rules from all CLI flags."""
        rules: List[ForwardRule] = []
        errors: List[str] = []

        for spec in self.args.local_forwards:
            try:
                rules.append(parse_local_rules([spec])[0])
            except ValueError as e:
                errors.append(str(e))

        for spec in self.args.remote_forwards:
            try:
                rules.append(parse_remote_rules([spec])[0])
            except ValueError as e:
                errors.append(str(e))

        for spec in self.args.dynamic_forwards:
            try:
                rules.append(parse_dynamic_rules([spec])[0])
            except ValueError as e:
                errors.append(str(e))

        for spec in self.args.legacy_forwards:
            try:
                rules.append(parse_legacy_rules([spec])[0])
            except ValueError as e:
                errors.append(str(e))

        if errors:
            for err in errors:
                log.error("Parse error: %s", err)
            sys.exit(1)

        return rules
