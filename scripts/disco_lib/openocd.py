"""OpenOCD communication via telnet."""

import re
import socket
import subprocess
import time

import click

from . import OPENOCD_CFG, OPENOCD_PORT


class OpenOCD:
    """Communicate with OpenOCD via telnet."""

    def __init__(self, port: int = OPENOCD_PORT):
        self.port = port

    def is_running(self) -> bool:
        """Check if OpenOCD is listening."""
        try:
            with socket.create_connection(("localhost", self.port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False

    def send(self, cmd: str, timeout: float = 2.0) -> str:
        """Send command to OpenOCD and return response.

        For long-running commands (like flash programming), use a larger timeout.
        The method waits for the connection to close (after 'exit' command completes)
        rather than relying solely on read timeouts.
        """
        try:
            with socket.create_connection(("localhost", self.port), timeout=timeout) as sock:
                # Receive initial banner
                sock.settimeout(0.5)
                try:
                    sock.recv(4096)
                except socket.timeout:
                    pass

                # Send command + exit
                # Note: OpenOCD executes commands sequentially, so 'exit' runs after cmd completes
                sock.sendall(f"{cmd}\nexit\n".encode())

                # Collect response with adaptive timeout
                # Use short timeout for individual reads, but keep reading until connection closes
                response = b""
                sock.settimeout(2.0)  # Short timeout per read
                deadline = time.time() + timeout
                consecutive_timeouts = 0

                while time.time() < deadline:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            # Connection closed - command completed
                            break
                        response += chunk
                        consecutive_timeouts = 0  # Reset on successful read
                    except socket.timeout:
                        consecutive_timeouts += 1
                        # Allow many consecutive timeouts for slow flash operations
                        # OpenOCD may pause during large reads/writes
                        # Only bail early if we've had 10+ timeouts (20s) with some response
                        if consecutive_timeouts > 10 and len(response) > 0:
                            break
                        continue

                # Clean up response
                text = response.decode("utf-8", errors="replace")
                text = text.replace("\r", "")
                # Remove control chars except newlines
                text = re.sub(r"[^\x20-\x7e\n]", "", text)
                # Filter out prompts, OpenOCD banner, and command echo
                lines = []
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith(">"):
                        continue
                    if "Open On-Chip" in line:
                        continue
                    # Filter command echo (starts with command name like "mdw", "reg", etc)
                    if line == cmd or line.startswith(cmd.split()[0] + " "):
                        continue
                    lines.append(line)
                return "\n".join(lines)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            raise click.ClickException(f"OpenOCD connection failed: {e}")

    def start(self) -> bool:
        """Start OpenOCD in background. Returns True if started successfully."""
        if self.is_running():
            click.secho("OpenOCD already running", fg="yellow")
            return True

        click.secho("Starting OpenOCD...", fg="blue")
        with open("/tmp/openocd.log", "w") as log:
            subprocess.Popen(
                ["openocd", "-f", OPENOCD_CFG],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

        # Wait for startup
        for _ in range(10):
            time.sleep(0.3)
            if self.is_running():
                click.secho("OpenOCD connected successfully", fg="green")
                # Halt and show basic info
                self.send("halt")
                pc = self.send("reg pc")
                click.echo(f"Target info:\n{pc}")
                return True

        click.secho("Failed to connect. Check /tmp/openocd.log", fg="red")
        try:
            with open("/tmp/openocd.log") as f:
                click.echo(f.read())
        except FileNotFoundError:
            pass
        return False

    def stop(self) -> None:
        """Stop OpenOCD."""
        result = subprocess.run(["pkill", "-x", "openocd"], capture_output=True)
        if result.returncode == 0:
            click.secho("OpenOCD stopped", fg="green")
        else:
            click.secho("OpenOCD not running", fg="yellow")

    def require_running(self) -> None:
        """Raise exception if OpenOCD is not running."""
        if not self.is_running():
            raise click.ClickException(
                "OpenOCD not running. Run 'disco connect' first."
            )
