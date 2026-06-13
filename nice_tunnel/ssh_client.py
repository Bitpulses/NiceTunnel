"""SSH connection and authentication logic."""

import logging
import os

import paramiko

log = logging.getLogger(__name__)


class SSHConnector:
    """Handles SSH connection establishment and authentication."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        key_file: str | None = None,
        password: str | None = None,
        keepalive: int = 30,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.key_file = key_file
        self.password = password
        self.keepalive = keepalive

    def connect(self) -> paramiko.SSHClient:
        """Establish an SSH connection to the bastion host."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        pkey, password = self._resolve_auth()

        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 15,
            "banner_timeout": 15,
        }
        if pkey:
            connect_kwargs["pkey"] = pkey
        if password:
            connect_kwargs["password"] = password

        log.info(
            "Connecting to SSH: %s@%s:%d ...",
            self.username, self.host, self.port,
        )
        client.connect(**connect_kwargs)

        # Enable keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(self.keepalive)
            log.info("SSH connected (keepalive=%ds)", self.keepalive)

        return client

    # Authentication resolution (private)

    def _resolve_auth(self):
        """Resolve SSH authentication method.

        Priority: explicit key_file > default keys > SSH agent > password.
        Returns a (pkey, password) tuple.
        """
        pkey = self._load_explicit_key()
        if pkey is not None:
            return pkey, self.password

        if self.password is None:
            pkey = self._try_default_keys()
            if pkey is not None:
                return pkey, None

            pkey = self._try_ssh_agent()
            if pkey is not None:
                return pkey, None

        return None, self.password

    def _load_explicit_key(self):
        """Load a user-specified SSH private key file."""
        if not self.key_file:
            return None
        pkey_path = os.path.expanduser(self.key_file)
        if not os.path.isfile(pkey_path):
            raise FileNotFoundError(f"SSH key file not found: {pkey_path}")
        return paramiko.RSAKey.from_private_key_file(pkey_path)

    @staticmethod
    def _try_default_keys():
        """Try loading keys from common default paths."""
        for default_key in ["~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/id_ecdsa"]:
            pkey_path = os.path.expanduser(default_key)
            if os.path.isfile(pkey_path):
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
                    log.info("Using default key: %s", pkey_path)
                    return pkey
                except Exception:
                    continue
        return None

    @staticmethod
    def _try_ssh_agent():
        """Try loading a key from the SSH agent."""
        try:
            agent = paramiko.Agent()
            agent_keys = agent.get_keys()
            if agent_keys:
                log.info("Using SSH agent key")
                return agent_keys[0]
        except Exception:
            pass
        return None
