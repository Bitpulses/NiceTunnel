"""Core port-forwarding tunnel engine.

Supports three forwarding modes:
  - Local  (-L): direct-tcpip channel through SSH
  - Remote (-R): server-side listener with forwarded-tcpip callback
  - Dynamic (-D): local SOCKS5 proxy with dynamic direct-tcpip channels
"""

import logging
import socket
import struct
import threading
from typing import Callable, Optional

from paramiko import Transport

from nice_tunnel.models import ForwardRule, ForwardType

log = logging.getLogger(__name__)


# Utilities

def _safe_close(*sockets):
    """Safely close one or more socket-like objects."""
    for sock in sockets:
        if sock is None:
            continue
        try:
            sock.close()
        except Exception:
            pass


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Receive exactly *n* bytes from *sock*, or raise ConnectionError."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed unexpectedly")
        data += chunk
    return data


# SOCKS5 constants

SOCKS5_VER = 5
SOCKS5_CMD_CONNECT = 1
SOCKS5_ATYP_IPV4 = 1
SOCKS5_ATYP_DOMAIN = 3
SOCKS5_ATYP_IPV6 = 4
SOCKS5_REP_SUCCEEDED = 0
SOCKS5_REP_GENERAL_FAILURE = 1
SOCKS5_REP_CMD_NOT_SUPPORTED = 7
SOCKS5_REP_ATYP_NOT_SUPPORTED = 8

SOCKS5_REPLY_TEMPLATE = struct.Struct("!BBBB4sH")


# Tunnel Engine

class TunnelEngine:
    """Manages local / remote listeners and bidirectional data piping."""

    def __init__(self, transport_provider: Callable[[], Optional[Transport]]):
        self._get_transport = transport_provider

    # Public dispatcher

    def start_forward(
        self, rule: ForwardRule, stop_event: threading.Event
    ) -> Optional[threading.Thread]:
        """Start port forwarding for a single *rule*.

        Returns the worker thread, or *None* if pre-flight checks fail.
        """
        if rule.forward_type == ForwardType.LOCAL:
            worker = self._local_forward_worker
        elif rule.forward_type == ForwardType.REMOTE:
            worker = self._remote_forward_worker
        elif rule.forward_type == ForwardType.DYNAMIC:
            worker = self._dynamic_forward_worker
        else:
            log.error("Unknown forward type: %s", rule.forward_type)
            return None

        thread = threading.Thread(
            target=worker,
            args=(rule, stop_event),
            daemon=True,
            name=rule.label,
        )
        thread.start()
        return thread

    # Local forwarding (-L)

    def _local_forward_worker(self, rule: ForwardRule, stop_event: threading.Event):
        """Listen locally and forward each connection via SSH direct-tcpip."""
        log.info("[START] %s", rule.label)

        server_sock = self._bind_local(rule, stop_event)
        if server_sock is None:
            return

        self._accept_loop(server_sock, rule, stop_event,
                          handler=self._handle_local_connection)
        log.info("[STOP] %s", rule.label)

    def _handle_local_connection(self, client_sock: socket.socket, rule: ForwardRule):
        """Handle a single local-forward connection: client → SSH tunnel → remote."""
        transport = self._get_transport()
        if transport is None or not transport.is_active():
            log.error("SSH transport unavailable, dropping %s", rule.label)
            _safe_close(client_sock)
            return

        try:
            chan = transport.open_channel(
                "direct-tcpip",
                (rule.remote_host, rule.remote_port),
                client_sock.getpeername(),
            )
        except Exception as e:
            log.error("Failed to create tunnel to %s:%d - %s",
                      rule.remote_host, rule.remote_port, e)
            _safe_close(client_sock)
            return

        if chan is None:
            log.error("Tunnel creation returned None for %s:%d",
                      rule.remote_host, rule.remote_port)
            _safe_close(client_sock)
            return

        # Bidirectional pipe
        threading.Thread(target=self._pipe, args=(client_sock, chan), daemon=True).start()
        threading.Thread(target=self._pipe, args=(chan, client_sock), daemon=True).start()

    # Remote forwarding (-R)

    def _remote_forward_worker(self, rule: ForwardRule, stop_event: threading.Event):
        """Request the SSH server to listen on *remote_host:remote_port*.

        Automatically re-requests on transport loss so the forwarding
        survives SSH reconnections.
        """
        log.info("[START] %s", rule.label)

        while not stop_event.is_set():
            transport = self._get_transport()
            if transport is None or not transport.is_active():
                stop_event.wait(timeout=2)
                continue

            try:
                # The handler is invoked by Paramiko's internal thread whenever
                # a remote client connects to the forwarded port.
                def _incoming_handler(chan, origin_addr, origin_port):
                    log.debug("Remote forward: connection from %s:%d", origin_addr, origin_port)
                    self._handle_remote_incoming(chan, rule)

                transport.request_port_forward(
                    rule.remote_host, rule.remote_port, _incoming_handler
                )
                log.info("[LISTEN] %s (remote)", rule.label)

                # Wait while transport is alive and not stopped
                while not stop_event.is_set() and transport.is_active():
                    stop_event.wait(timeout=1)

            except Exception as e:
                log.error("Remote forward %s failed: %s", rule.label, e)
            finally:
                try:
                    transport.cancel_port_forward(rule.remote_host, rule.remote_port)
                except Exception:
                    pass

            if not stop_event.is_set():
                log.warning("Remote forward %s lost, retrying in 3s...", rule.label)
                stop_event.wait(timeout=3)

        log.info("[STOP] %s", rule.label)

    def _handle_remote_incoming(self, chan, rule: ForwardRule):
        """A remote client connected to the SSH server's forwarded port.

        We connect to the local target and pipe data bidirectionally.
        """
        try:
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.settimeout(10)
            target.connect((rule.local_host, rule.local_port))
        except Exception as e:
            log.error("Cannot connect to local target %s:%d - %s",
                      rule.local_host, rule.local_port, e)
            _safe_close(chan)
            return

        threading.Thread(target=self._pipe, args=(chan, target), daemon=True).start()
        threading.Thread(target=self._pipe, args=(target, chan), daemon=True).start()

    # Dynamic / SOCKS5 forwarding (-D)

    def _dynamic_forward_worker(self, rule: ForwardRule, stop_event: threading.Event):
        """Start a local SOCKS5 proxy server."""
        log.info("[START] %s", rule.label)

        server_sock = self._bind_local(rule, stop_event)
        if server_sock is None:
            return

        self._accept_loop(server_sock, rule, stop_event,
                          handler=self._handle_socks5_connection)
        log.info("[STOP] %s", rule.label)

    def _handle_socks5_connection(self, client_sock: socket.socket, _rule: ForwardRule):
        """Handle a complete SOCKS5 CONNECT handshake and start piping."""
        try:
            # 1. Greeting 
            ver, nmethods = struct.unpack("!BB", _recv_exactly(client_sock, 2))
            if ver != SOCKS5_VER:
                _safe_close(client_sock)
                return

            methods = _recv_exactly(client_sock, nmethods)
            if 0x00 not in methods:  # Only "no authentication" is supported
                client_sock.sendall(b"\x05\xff")
                _safe_close(client_sock)
                return
            client_sock.sendall(b"\x05\x00")  # VER=5, METHOD=0

            # 2. Request 
            header = _recv_exactly(client_sock, 4)
            ver, cmd, _, atyp = struct.unpack("!BBBB", header)
            if cmd != SOCKS5_CMD_CONNECT:
                self._send_socks5_reply(client_sock, SOCKS5_REP_CMD_NOT_SUPPORTED)
                _safe_close(client_sock)
                return

            # Parse destination address
            if atyp == SOCKS5_ATYP_IPV4:
                dst_addr = socket.inet_ntoa(_recv_exactly(client_sock, 4))
            elif atyp == SOCKS5_ATYP_DOMAIN:
                length = _recv_exactly(client_sock, 1)[0]
                dst_addr = _recv_exactly(client_sock, length).decode("utf-8", errors="replace")
            elif atyp == SOCKS5_ATYP_IPV6:
                dst_addr = socket.inet_ntop(socket.AF_INET6, _recv_exactly(client_sock, 16))
            else:
                self._send_socks5_reply(client_sock, SOCKS5_REP_ATYP_NOT_SUPPORTED)
                _safe_close(client_sock)
                return

            dst_port = struct.unpack("!H", _recv_exactly(client_sock, 2))[0]
            log.debug("SOCKS5 CONNECT → %s:%d", dst_addr, dst_port)

            # 3. Open tunnel 
            transport = self._get_transport()
            if transport is None or not transport.is_active():
                self._send_socks5_reply(client_sock, SOCKS5_REP_GENERAL_FAILURE)
                _safe_close(client_sock)
                return

            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (dst_addr, dst_port),
                    client_sock.getpeername(),
                )
            except Exception as e:
                log.debug("SOCKS5 tunnel failed to %s:%d - %s", dst_addr, dst_port, e)
                self._send_socks5_reply(client_sock, SOCKS5_REP_GENERAL_FAILURE)
                _safe_close(client_sock)
                return

            # 4. Reply success 
            self._send_socks5_reply(client_sock, SOCKS5_REP_SUCCEEDED)

            # 5. Bidirectional pipe
            threading.Thread(target=self._pipe, args=(client_sock, chan), daemon=True).start()
            threading.Thread(target=self._pipe, args=(chan, client_sock), daemon=True).start()

        except (ConnectionError, OSError, struct.error) as e:
            log.debug("SOCKS5 connection error: %s", e)
        except Exception:
            log.debug("SOCKS5 unexpected error", exc_info=True)
        finally:
            # Only close if we didn't start piping (piping threads handle close)
            pass  # _pipe threads will close their sockets

    @staticmethod
    def _send_socks5_reply(sock: socket.socket, rep: int):
        """Send a minimal SOCKS5 reply: VER=5, REP, RSV=0, ATYP=IPv4, BND=0.0.0.0:0."""
        try:
            sock.sendall(SOCKS5_REPLY_TEMPLATE.pack(5, rep, 0, 1, b"\x00\x00\x00\x00", 0))
        except Exception:
            pass

    # Shared helpers

    def _bind_local(self, rule: ForwardRule, stop_event: threading.Event) -> Optional[socket.socket]:
        """Create, bind, and listen on a local TCP socket.

        Returns the server socket, or *None* on failure.
        """
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_sock.bind((rule.local_host, rule.local_port))
        except OSError as e:
            log.error("Failed to bind %s:%d - %s", rule.local_host, rule.local_port, e)
            _safe_close(server_sock)
            return None

        server_sock.listen(128)
        server_sock.settimeout(1.0)
        log.info("[LISTEN] %s", rule.label)
        return server_sock

    def _accept_loop(self, server_sock: socket.socket, rule: ForwardRule,
                     stop_event: threading.Event, handler):
        """Accept connections on *server_sock* and dispatch to *handler*.

        *handler* is called as ``handler(client_sock, rule)``.
        """
        while not stop_event.is_set():
            try:
                client_sock, addr = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            log.debug("Connection from %s → %s", addr, rule.label)
            threading.Thread(
                target=handler,
                args=(client_sock, rule),
                daemon=True,
            ).start()

        _safe_close(server_sock)

    # Data pipe

    @staticmethod
    def _pipe(src, dst):
        """Copy data from *src* to *dst* until EOF or error."""
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            _safe_close(src, dst)
