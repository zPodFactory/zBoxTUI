"""System information utilities."""

import platform
import re
import socket
import subprocess
from dataclasses import dataclass


@dataclass
class NetworkInterface:
    """Container for network interface information."""

    name: str
    ipv4: str
    gateway: str | None = None  # Gateway IP if this is the default route interface


@dataclass
class SystemInfo:
    """Container for system information."""

    hostname: str
    os_name: str
    os_version: str
    cpu_info: str
    memory_total: str
    interfaces: list[NetworkInterface]


def get_hostname() -> str:
    """Get the system hostname."""
    return socket.gethostname()


def get_os_info() -> tuple[str, str]:
    """Get OS name and version."""
    return platform.system(), platform.release()


def get_cpu_info() -> str:
    """Get CPU information."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":")[1].strip()
    except (FileNotFoundError, PermissionError):
        pass
    return platform.processor() or "Unknown CPU"


def get_memory_info() -> str:
    """Get total memory in human-readable format."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    gb = kb / (1024 * 1024)
                    return f"{gb:.1f} GiB Memory"
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return "Unknown Memory"


def get_default_gateway() -> tuple[str | None, str | None]:
    """Get the default gateway IP and interface name."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse "default via X.X.X.X dev ethX ..."
            match = re.search(
                r"default via (\d+\.\d+\.\d+\.\d+) dev (\S+)", result.stdout
            )
            if match:
                return match.group(1), match.group(2)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None, None


def get_network_interfaces() -> list[NetworkInterface]:
    """Get list of network interfaces with their IPv4 addresses.

    The default gateway interface is returned first.
    """
    interfaces = []
    gateway_ip, gateway_iface = get_default_gateway()

    try:
        # Use 'ip addr' command to get interface information
        result = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            current_iface = None
            for line in result.stdout.splitlines():
                # Match interface line: "2: eth0: <BROADCAST,..."
                iface_match = re.match(r"^\d+:\s+(\S+):", line)
                if iface_match:
                    current_iface = iface_match.group(1)
                    # Remove @... suffix if present (e.g., eth0@if123)
                    if "@" in current_iface:
                        current_iface = current_iface.split("@")[0]

                # Match inet line: "    inet 192.168.1.100/24 ..."
                inet_match = re.match(r"^\s+inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                if inet_match and current_iface:
                    ipv4 = inet_match.group(1)
                    # Skip loopback
                    if current_iface != "lo":
                        # Check if this is the gateway interface
                        gw = gateway_ip if current_iface == gateway_iface else None
                        interfaces.append(
                            NetworkInterface(name=current_iface, ipv4=ipv4, gateway=gw)
                        )

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback if no interfaces found
    if not interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            interfaces.append(NetworkInterface(name="unknown", ipv4=ip))
        except OSError:
            interfaces.append(NetworkInterface(name="lo", ipv4="127.0.0.1"))

    # Sort to put gateway interface first
    interfaces.sort(key=lambda x: (x.gateway is None, x.name))

    return interfaces


def get_system_info() -> SystemInfo:
    """Gather all system information."""
    os_name, os_version = get_os_info()
    return SystemInfo(
        hostname=get_hostname(),
        os_name=os_name,
        os_version=os_version,
        cpu_info=get_cpu_info(),
        memory_total=get_memory_info(),
        interfaces=get_network_interfaces(),
    )
