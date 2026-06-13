"""Data models for NiceTunnel."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ForwardType(Enum):
    """Type of SSH port forwarding."""
    LOCAL = "L"      # -L: local port → SSH tunnel → remote target
    REMOTE = "R"     # -R: remote port → SSH tunnel → local target
    DYNAMIC = "D"    # -D: local SOCKS5 proxy → SSH tunnel → anywhere


@dataclass
class ForwardRule:
    """A single port-forwarding rule.

    Field semantics by forward_type:
        LOCAL:   bind on (local_host, local_port), forward to (remote_host, remote_port)
        REMOTE:  bind on (remote_host, remote_port) at SSH server, forward to (local_host, local_port)
        DYNAMIC: SOCKS5 proxy on (local_host, local_port), remote_* fields unused
    """

    forward_type: ForwardType
    local_host: str = "0.0.0.0"
    local_port: int = 0
    remote_host: str = ""
    remote_port: int = 0

    @property
    def label(self) -> str:
        if self.forward_type == ForwardType.DYNAMIC:
            return f"[SOCKS5] {self.local_host}:{self.local_port}"
        elif self.forward_type == ForwardType.REMOTE:
            return f"[R] {self.remote_host}:{self.remote_port} → {self.local_host}:{self.local_port}"
        else:
            return f"[L] {self.local_host}:{self.local_port} → {self.remote_host}:{self.remote_port}"


# Forward-spec parsers

def parse_local_spec(spec: str) -> ForwardRule:
    """Parse a Local (-L) forwarding spec.

    Format: [bind_host:]port:remote_host:remote_port

    Examples:
        "8080:internal.example.com:80"          → bind 0.0.0.0:8080
        "127.0.0.1:8080:10.0.0.5:3306"         → bind 127.0.0.1:8080
    """
    parts = spec.strip().split(":")
    if len(parts) == 3:
        bind_host = "0.0.0.0"
        bind_port_str, remote_host, remote_port_str = parts
    elif len(parts) == 4:
        bind_host, bind_port_str, remote_host, remote_port_str = parts
    else:
        raise ValueError(
            f"Invalid -L spec '{spec}'. Expected [bind_host:]port:remote_host:remote_port"
        )
    return ForwardRule(
        forward_type=ForwardType.LOCAL,
        local_host=_validate_host(bind_host),
        local_port=_validate_port(bind_port_str, "local"),
        remote_host=_validate_host(remote_host),
        remote_port=_validate_port(remote_port_str, "remote"),
    )


def parse_remote_spec(spec: str) -> ForwardRule:
    """Parse a Remote (-R) forwarding spec.

    Format: [bind_host:]port:local_host:local_port

    Examples:
        "8080:localhost:3306"                   → SSH server binds :8080, forwards to localhost:3306
        "0.0.0.0:9090:192.168.1.5:22"          → SSH server binds 0.0.0.0:9090
    """
    parts = spec.strip().split(":")
    if len(parts) == 3:
        bind_host = "0.0.0.0"
        bind_port_str, local_host, local_port_str = parts
    elif len(parts) == 4:
        bind_host, bind_port_str, local_host, local_port_str = parts
    else:
        raise ValueError(
            f"Invalid -R spec '{spec}'. Expected [bind_host:]port:local_host:local_port"
        )
    return ForwardRule(
        forward_type=ForwardType.REMOTE,
        remote_host=_validate_host(bind_host),
        remote_port=_validate_port(bind_port_str, "remote bind"),
        local_host=_validate_host(local_host),
        local_port=_validate_port(local_port_str, "local target"),
    )


def parse_dynamic_spec(spec: str) -> ForwardRule:
    """Parse a Dynamic (-D) forwarding spec for SOCKS5 proxy.

    Format: [bind_host:]port

    Examples:
        "1080"            → SOCKS5 on 0.0.0.0:1080
        "127.0.0.1:1080"  → SOCKS5 on 127.0.0.1:1080
    """
    spec = spec.strip()
    if ":" in spec:
        bind_host, port_str = spec.rsplit(":", 1)
    else:
        bind_host = "0.0.0.0"
        port_str = spec
    return ForwardRule(
        forward_type=ForwardType.DYNAMIC,
        local_host=_validate_host(bind_host),
        local_port=_validate_port(port_str, "SOCKS5"),
    )


def parse_legacy_spec(spec: str) -> ForwardRule:
    """Parse the legacy -f format (always LOCAL mode).

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
        raise ValueError(f"Invalid remote address '{remote_part}'. Expected host:port")
    remote_host, remote_port_str = remote_part.rsplit(":", 1)

    if ":" in local_part:
        local_host, local_port_str = local_part.rsplit(":", 1)
    else:
        local_host = "0.0.0.0"
        local_port_str = local_part

    return ForwardRule(
        forward_type=ForwardType.LOCAL,
        local_host=_validate_host(local_host),
        local_port=_validate_port(local_port_str, "local"),
        remote_host=_validate_host(remote_host),
        remote_port=_validate_port(remote_port_str, "remote"),
    )


# Batch parsing

def parse_local_rules(specs: List[str]) -> List[ForwardRule]:
    return [parse_local_spec(s) for s in specs]

def parse_remote_rules(specs: List[str]) -> List[ForwardRule]:
    return [parse_remote_spec(s) for s in specs]

def parse_dynamic_rules(specs: List[str]) -> List[ForwardRule]:
    return [parse_dynamic_spec(s) for s in specs]

def parse_legacy_rules(specs: List[str]) -> List[ForwardRule]:
    return [parse_legacy_spec(s) for s in specs]


# Internal helpers

def _validate_host(host: str) -> str:
    """Basic host validation; returns host unchanged."""
    if not host or host.isspace():
        raise ValueError("Host must not be empty")
    return host


def _validate_port(port_str: str, context: str) -> int:
    """Parse and validate a port number (1-65535)."""
    try:
        port = int(port_str.strip())
    except ValueError:
        raise ValueError(f"Invalid {context} port '{port_str}'")
    if not (1 <= port <= 65535):
        raise ValueError(f"{context.capitalize()} port {port} out of range (1-65535)")
    return port
