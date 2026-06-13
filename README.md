# NiceTunnel

A nice and elegant SSH port forwarding tool — **Local**, **Remote**, and **Dynamic/SOCKS5** mode,
all through a single SSH bastion host. Built on [Paramiko](https://www.paramiko.org/).

## Features

- **All forwarding types** — Local (`-L`), Remote (`-R`), and Dynamic/SOCKS5 (`-D`)
- **Unlimited tunnels** — Run as many forwarding rules as you need simultaneously
- **Auto-reconnect** — SSH connection drops are detected and recovered automatically
- **Multiple auth methods** — Private key, password, or SSH agent
- **Keepalive** — Prevents idle timeouts with a configurable heartbeat interval
- **Graceful shutdown** — `Ctrl+C` safely closes all tunnels and the SSH connection
- **Modular design** — Cleanly separated into `models / cli / ssh_client / tunnel_engine / manager`

## Installation

```bash
pip install paramiko
```

## Quick Start

```bash
# Clone & run
python NiceTunnel.py -H your-bastion.example.com -u youruser -L 8080:internal-host:80
```

Now visit `http://localhost:8080` — you're accessing `internal-host:80` inside the cluster.

---

## Usage

### CLI Mode

All examples use `NiceTunnel.py` as the entry point. Replace with your actual SSH bastion
host and username.

#### Local Forwarding (`-L`)

Forward a local port to a remote host *through* the SSH bastion.

```
-L [bind_host:]port:remote_host:remote_port
```

```bash
# Basic: local 8080 → internal.example.com:80
python NiceTunnel.py -H bastion.example.com -u root -L 8080:internal.example.com:80

# Bind to localhost only (other machines on your LAN cannot connect)
python NiceTunnel.py -H gw -u ops -L 127.0.0.1:5432:db.internal:5432

# Multiple local forwards at once
python NiceTunnel.py -H 10.0.0.1 -u admin --key ~/.ssh/id_rsa \
    -L 3306:db-node01:3306 \
    -L 6379:redis-node02:6379 \
    -L 8888:app-node03:8080
```

#### Remote Forwarding (`-R`)

Let the SSH server listen on a port and forward connections back to your local machine.
Useful for exposing a local service to the remote network.

```
-R [bind_host:]port:local_host:local_port
```

```bash
# Expose local MySQL to the SSH server's port 13306
python NiceTunnel.py -H jumper -u root -R 13306:localhost:3306

# Expose local SSH to a specific interface on the SSH server
python NiceTunnel.py -H jumper -u root -R 0.0.0.0:2222:localhost:22
```

#### Dynamic / SOCKS5 Forwarding (`-D`)

Start a SOCKS5 proxy on your local machine. All traffic goes through the SSH tunnel
— perfect for browsing internal web apps or accessing multiple services at once.

```
-D [bind_host:]port
```

```bash
# SOCKS5 proxy on port 1080 (all interfaces)
python NiceTunnel.py -H jumper -u root -D 1080

# SOCKS5 proxy on localhost only
python NiceTunnel.py -H jumper -u root -D 127.0.0.1:1080
```

Then configure your browser or tool to use `socks5://127.0.0.1:1080`:

```bash
# Example: curl through the SOCKS5 proxy
curl --socks5 127.0.0.1:1080 http://internal-app.example.com

# Example: SSH through the SOCKS5 proxy
ssh -o ProxyCommand='nc -x 127.0.0.1:1080 %h %p' user@internal-host
```

#### Legacy Format (`-f`)

The original `-f` flag is still supported for backward compatibility (equivalent to `-L`):

```bash
python NiceTunnel.py -H 10.0.0.1 -u root -f "192.168.1.100:80->8080"
python NiceTunnel.py -H 10.0.0.1 -u root -f "node01:3306>127.0.0.1:3306"
```

#### Mix All Modes

You can combine `-L`, `-R`, `-D`, and `-f` in a single command:

```bash
python NiceTunnel.py -H jumper -u root \
    -L 8080:web.internal:80 \
    -R 13306:localhost:3306 \
    -D 1080
```

---

## Options

### SSH Connection

| Argument           | Description                        | Default              |
|--------------------|------------------------------------|----------------------|
| `-H`, `--ssh-host` | SSH bastion/jump host address      | **Required**         |
| `-p`, `--ssh-port` | SSH port                           | `22`                 |
| `-u`, `--ssh-user` | SSH username                       | **Required**         |
| `--key`            | Path to SSH private key            | auto-detect \*       |
| `--password`       | SSH password (not recommended)     | —                    |

\* Auto-detection order: `--key` argument → `~/.ssh/id_rsa` → `~/.ssh/id_ed25519` → `~/.ssh/id_ecdsa` → SSH agent.

### Forwarding Rules

| Argument           | Mode     | Format                                              |
|--------------------|----------|-----------------------------------------------------|
| `-L`, `--local-forward`   | Local    | `[bind_host:]port:remote_host:remote_port`          |
| `-R`, `--remote-forward`  | Remote   | `[bind_host:]port:local_host:local_port`            |
| `-D`, `--dynamic-forward` | Dynamic  | `[bind_host:]port`                                  |
| `-f`, `--forward`         | Local    | `remote_host:remote_port>[local_host:]local_port`   |

All flags can be repeated multiple times for multiple rules.

### Miscellaneous

| Argument           | Description                        | Default              |
|--------------------|------------------------------------|----------------------|
| `-k`, `--keepalive`| Keepalive interval (seconds)       | `30`                 |
| `-v`, `--verbose`  | Enable debug-level logging         | —                    |

---

## How It Works

### Local Forwarding (`-L`)

```
┌──────────────┐        SSH Tunnel         ┌──────────────┐       TCP        ┌──────────────┐
│  Your Machine │ ◄─── direct-tcpip ──────► │ Bastion Host  │ ◄──────────────► │ Remote Target │
│  localhost:   │                           │               │                  │               │
│    8080       │                           │               │                  │  internal:80  │
└──────────────┘                           └──────────────┘                  └──────────────┘
```

1. A local TCP socket listens on `bind_host:port`.
2. On each connection, Paramiko opens a `direct-tcpip` channel through the SSH tunnel.
3. The bastion host forwards the channel to `remote_host:remote_port`.
4. Bidirectional data piping makes the tunnel transparent.

### Remote Forwarding (`-R`)

```
┌──────────────┐        SSH Tunnel         ┌──────────────┐       TCP        ┌──────────────┐
│  Your Machine │ ◄── forwarded-tcpip ────► │ Bastion Host  │ ◄──────────────► │ Remote Client │
│  localhost:   │                           │  listens on   │                  │  connects to  │
│    3306       │                           │   :13306      │                  │  :13306       │
└──────────────┘                           └──────────────┘                  └──────────────┘
```

1. The SSH client requests the server to listen on `remote_host:remote_port`.
2. When a remote client connects, the server sends a `forwarded-tcpip` channel back.
3. NiceTunnel connects to `local_host:local_port` and pipes data bidirectionally.
4. Automatically re-requests the port forward after SSH reconnection.

### Dynamic Forwarding (`-D`) — SOCKS5

```
┌──────────────┐        SSH Tunnel         ┌──────────────┐
│  Your Machine │ ◄─── direct-tcpip ──────► │ Bastion Host  │ ───► Any internal host
│  SOCKS5       │   (dynamic destination)   │               │
│  :1080        │                           │               │
└──────────────┘                           └──────────────┘
```

1. A local SOCKS5 proxy listens on `bind_host:port`.
2. The client (browser, curl, etc.) sends a SOCKS5 `CONNECT` request with the desired destination.
3. NiceTunnel opens a `direct-tcpip` channel to that destination through SSH.
4. Once connected, a SOCKS5 success reply is sent, and data flows transparently.

---

## Project Structure

```
NiceTunnel/
├── NiceTunnel.py                 # CLI entry point
├── nice_tunnel/                  # Core package
│   ├── __init__.py               # Public API exports
│   ├── models.py                 # ForwardRule dataclass, ForwardType enum, spec parsers
│   ├── cli.py                    # argparse setup (-L / -R / -D / -f)
│   ├── ssh_client.py             # SSH connection & authentication
│   ├── tunnel_engine.py          # Local / Remote / SOCKS5 forwarding engine
│   └── manager.py                # Lifecycle orchestration & auto-reconnect
└── README.md
```

## Practical Examples

```bash
# Access a Kubernetes dashboard inside a cluster
python NiceTunnel.py -H jump.example.com -u ops -L 8443:k8s-dashboard:443

# Forward a Jupyter notebook server
python NiceTunnel.py -H jump -u dev -L 8888:gpu-node-07:8888

# SOCKS5 proxy to browse all internal services
python NiceTunnel.py -H jump -u dev -D 1080
# Then set your browser to SOCKS5 proxy at 127.0.0.1:1080

# Remote forward to let a colleague access your local dev server
python NiceTunnel.py -H shared-bastion -u dev -R 9000:localhost:3000

# Combine: access DB directly + SOCKS5 for everything else
python NiceTunnel.py -H jump -u ops \
    -L 5432:pg-primary:5432 \
    -D 1080
```

## License

MIT
