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
    netmask: str | None = None  # Netmask in dotted notation
    cidr: int | None = None  # CIDR prefix length (e.g., 24)


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


def cidr_to_netmask(cidr: int) -> str:
    """Convert CIDR prefix length to dotted netmask notation."""
    if cidr < 0 or cidr > 32:
        return "255.255.255.0"  # Default fallback
    mask = (0xFFFFFFFF << (32 - cidr)) & 0xFFFFFFFF
    return f"{(mask >> 24) & 0xFF}.{(mask >> 16) & 0xFF}.{(mask >> 8) & 0xFF}.{mask & 0xFF}"


def netmask_to_cidr(netmask: str) -> int:
    """Convert dotted netmask notation to CIDR prefix length."""
    try:
        parts = [int(p) for p in netmask.split(".")]
        if len(parts) != 4:
            return 24
        binary = "".join(format(p, "08b") for p in parts)
        return binary.count("1")
    except (ValueError, AttributeError):
        return 24


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
                inet_match = re.match(r"^\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                if inet_match and current_iface:
                    ipv4 = inet_match.group(1)
                    cidr = int(inet_match.group(2))
                    netmask = cidr_to_netmask(cidr)
                    # Skip loopback
                    if current_iface != "lo":
                        # Check if this is the gateway interface
                        gw = gateway_ip if current_iface == gateway_iface else None
                        interfaces.append(
                            NetworkInterface(
                                name=current_iface,
                                ipv4=ipv4,
                                gateway=gw,
                                netmask=netmask,
                                cidr=cidr,
                            )
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


# Prefixes to exclude when listing physical interfaces
EXCLUDED_INTERFACE_PREFIXES = (
    "lo",
    "docker",
    "br-",
    "veth",
    "tailscale",
    "wg",
    "virbr",
    "vnet",
)


def get_physical_interfaces() -> list[NetworkInterface]:
    """Get only physical network interfaces, excluding virtual/VPN interfaces."""
    all_interfaces = get_network_interfaces()
    return [
        iface
        for iface in all_interfaces
        if not iface.name.startswith(EXCLUDED_INTERFACE_PREFIXES)
    ]


def get_dns_servers() -> list[str]:
    """Parse /etc/resolv.conf for DNS nameservers.

    Returns:
        List of DNS server IP addresses (up to 3).
    """
    dns_servers: list[str] = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                line = line.strip()
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        dns_servers.append(parts[1])
                        if len(dns_servers) >= 3:
                            break
    except (FileNotFoundError, PermissionError):
        pass
    return dns_servers


def is_dhcp_interface(iface_name: str) -> bool:
    """Check if an interface is configured for DHCP in /etc/network/interfaces.

    Args:
        iface_name: The interface name to check (e.g., 'eth0').

    Returns:
        True if configured for DHCP, False if static or unknown.
    """
    try:
        with open("/etc/network/interfaces") as f:
            content = f.read()
            # Look for "iface eth0 inet dhcp" pattern
            pattern = rf"iface\s+{re.escape(iface_name)}\s+inet\s+(\w+)"
            match = re.search(pattern, content)
            if match:
                return match.group(1).lower() == "dhcp"
    except (FileNotFoundError, PermissionError):
        pass
    # Default to DHCP if we can't determine
    return True


@dataclass
class InterfaceConfig:
    """Complete configuration for a network interface."""

    name: str
    is_dhcp: bool
    ipv4: str
    netmask: str
    cidr: int
    gateway: str
    dns1: str
    dns2: str


def get_interface_config(iface_name: str) -> InterfaceConfig:
    """Get complete configuration for a network interface.

    Args:
        iface_name: The interface name (e.g., 'eth0').

    Returns:
        InterfaceConfig with current settings.
    """
    # Get current IP/netmask from interface
    interfaces = get_network_interfaces()
    iface = next((i for i in interfaces if i.name == iface_name), None)

    ipv4 = iface.ipv4 if iface else ""
    netmask = iface.netmask if iface and iface.netmask else "255.255.255.0"
    cidr = iface.cidr if iface and iface.cidr else 24
    gateway = iface.gateway if iface and iface.gateway else ""

    # If no gateway on this interface, try to get default gateway
    if not gateway:
        gw_ip, _ = get_default_gateway()
        gateway = gw_ip or ""

    # Get DNS servers
    dns_servers = get_dns_servers()
    dns1 = dns_servers[0] if len(dns_servers) > 0 else ""
    dns2 = dns_servers[1] if len(dns_servers) > 1 else ""

    # Check if DHCP
    is_dhcp = is_dhcp_interface(iface_name)

    return InterfaceConfig(
        name=iface_name,
        is_dhcp=is_dhcp,
        ipv4=ipv4,
        netmask=netmask,
        cidr=cidr,
        gateway=gateway,
        dns1=dns1,
        dns2=dns2,
    )


def validate_ipv4(ip: str) -> bool:
    """Validate an IPv4 address format.

    Args:
        ip: The IP address string to validate.

    Returns:
        True if valid IPv4 format, False otherwise.
    """
    if not ip:
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        for part in parts:
            num = int(part)
            if num < 0 or num > 255:
                return False
    except ValueError:
        return False
    return True
