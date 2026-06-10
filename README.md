# NiceTunnel

A nice and elegant SSH port forwarding tool.

Forward ports from cluster compute nodes to your local machine via SSH tunnel,
built on top of [Paramiko](https://www.paramiko.org/).

## Installation

```bash
pip install paramiko
```

## Usage

```bash
# Forward port 80 of cluster node 192.168.1.100 to local port 8080
python main.py -H bastion.example.com -u root -f "192.168.1.100:80->8080"

# Forward multiple ports at once
python main.py -H 10.0.0.1 -u admin --key ~/.ssh/id_rsa \
    -f "node01:3306->3306" \
    -f "node02:6379->6379" \
    -f "node03:8080->8888"

# Bind to localhost only
python main.py -H gw -u ops -f "db.internal:5432->127.0.0.1:5432"

# Use password authentication
python main.py -H 10.0.0.1 -u admin --password mypass \
    -f "192.168.1.100:22->2222"

# Custom SSH port and keepalive interval
python main.py -H jumpserver.com -p 2222 -u deploy -k 60 \
    -f "k8s-node01:6443->6443"
```

## Options

| Argument            | Description                              | Default            |
|---------------------|------------------------------------------|--------------------|
| `-H`, `--ssh-host`  | SSH bastion/jump host address            | **Required**       |
| `-p`, `--ssh-port`  | SSH port                                 | `22`               |
| `-u`, `--ssh-user`  | SSH username                             | **Required**       |
| `--key`             | Path to SSH private key file             | `~/.ssh/id_rsa`*   |
| `--password`        | SSH password (not recommended)           | —                  |
| `-f`, `--forward`   | Forwarding rule (repeatable)             | **Required**       |
| `-k`, `--keepalive` | Keepalive interval in seconds            | `30`               |
| `-v`, `--verbose`   | Enable debug-level logging               | —                  |

\* Falls back through `~/.ssh/id_ed25519`, `~/.ssh/id_ecdsa`, and SSH agent.

### Forwarding Rule Format

```
remote_host:remote_port->local_host:local_port
remote_host:remote_port->local_port          # local_host defaults to 0.0.0.0
remote_host:remote_port>local_host:local_port
```

## How It Works

```
┌─────────────┐     SSH Tunnel      ┌──────────────┐     TCP      ┌──────────────┐
│  Your Local  │ ◄─────────────────► │  Bastion/Jump │ ◄──────────► │ Cluster Node │
│   Machine    │    direct-tcpip     │     Host      │   internal   │   (target)   │
└─────────────┘                      └──────────────┘              └──────────────┘
```

1. A local TCP socket listens on the specified `local_host:local_port`.
2. When a connection arrives, Paramiko opens a `direct-tcpip` channel through the
   SSH connection to the bastion host.
3. The bastion host forwards the channel to the target `remote_host:remote_port`
   inside the cluster.
4. Bidirectional data piping makes the tunnel transparent to the client.

## Features

- **Auto-reconnect** — SSH connection drops are detected and recovered automatically.
- **Multiple tunnels** — Forward as many ports as you need with repeated `-f` flags.
- **Multiple auth methods** — Private key, password, or SSH agent.
- **Keepalive** — Prevents idle timeouts with configurable heartbeat interval.
- **Graceful shutdown** — `Ctrl+C` safely closes all tunnels and the SSH connection.

## License

MIT
