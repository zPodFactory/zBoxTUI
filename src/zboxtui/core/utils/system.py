"""System information utilities."""

import os
import platform
import re
import shutil
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
class FilesystemInfo:
    """One mounted filesystem we want to show on the dashboard."""

    device: str        # e.g. "/dev/mapper/vg-root", "/dev/sda1"
    mount_point: str   # e.g. "/", "/boot"
    fstype: str        # e.g. "ext4"
    used_bytes: int
    total_bytes: int

    @property
    def percent(self) -> float:
        return 100.0 * self.used_bytes / self.total_bytes if self.total_bytes else 0.0


@dataclass
class SystemInfo:
    """Container for system information."""

    hostname: str
    os_name: str
    os_version: str
    debian_version: str  # Content of /etc/debian_version, "" if absent.
    cpu_info: str
    memory_total: str
    interfaces: list[NetworkInterface]
    filesystems: list[FilesystemInfo]


def get_hostname() -> str:
    """Get the FQDN, falling back to the short hostname.

    ``socket.getfqdn()`` consults /etc/hosts and the resolver — on a
    zbox with proper DNS or hosts setup this returns
    ``host.example.com``. If FQDN resolution fails or returns the
    short name only, fall back to ``socket.gethostname()`` so we
    always have something to show.
    """
    fqdn = socket.getfqdn()
    short = socket.gethostname()
    # getfqdn can return "localhost" or the short name on a box with no
    # FQDN configured — only prefer it when it actually adds a domain
    # part beyond the short hostname.
    if fqdn and "." in fqdn and not fqdn.startswith("localhost"):
        return fqdn
    return short


def get_os_info() -> tuple[str, str]:
    """Get the OS label and (optional) version.

    Prefers ``PRETTY_NAME`` from /etc/os-release (e.g. "Debian GNU/Linux
    13 (trixie)") returned as ``(pretty_name, "")`` — the pretty name
    already includes the version. Falls back to ``(platform.system(),
    platform.release())`` on a box without /etc/os-release.
    """
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        os_release = {}
    pretty = os_release.get("PRETTY_NAME")
    if pretty:
        return pretty, ""
    return platform.system(), platform.release()


def get_debian_version() -> str:
    """Return the full Debian point release from /etc/debian_version.

    On Debian this file holds the running point release (e.g. "13.5"),
    which is more precise than the os-release VERSION_ID. Returns the
    empty string on non-Debian boxes or read errors.
    """
    try:
        with open("/etc/debian_version", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


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
        debian_version=get_debian_version(),
        cpu_info=get_cpu_info(),
        memory_total=get_memory_info(),
        interfaces=get_network_interfaces(),
        filesystems=get_filesystems(),
    )


# Filesystem types that represent actual disk-backed storage. Anything
# not in this set (proc, sysfs, tmpfs, cgroup*, devtmpfs, overlayfs,
# fuse.*, autofs, etc.) is filtered out — the dashboard only shows
# storage the user might actually fill up.
_DISK_FSTYPES = frozenset({
    "ext2", "ext3", "ext4",
    "xfs",
    "btrfs",
    "zfs",
    "jfs",
    "reiserfs",
    "f2fs",
    "ntfs", "ntfs3",
    "vfat", "exfat",
    "nilfs2",
})


def _unescape_mount_field(field: str) -> str:
    """Decode the ``\\NNN`` octal escapes the kernel writes in /proc/mounts."""
    # Spaces in mount paths show up as \040, etc. Cheap manual decoder.
    out: list[str] = []
    i = 0
    while i < len(field):
        if field[i] == "\\" and i + 3 < len(field) and field[i + 1 : i + 4].isdigit():
            try:
                out.append(chr(int(field[i + 1 : i + 4], 8)))
                i += 4
                continue
            except ValueError:
                pass
        out.append(field[i])
        i += 1
    return "".join(out)


def get_filesystems() -> list[FilesystemInfo]:
    """Read /proc/mounts and return real-disk filesystems with usage.

    Pseudo-filesystems (proc, sysfs, tmpfs, etc.) are filtered out via
    an allow-list of disk-fstype names. Mounts whose statvfs fails are
    silently skipped. Mount points are de-duplicated (bind mounts can
    appear twice with the same mount_point) — first one wins.
    """
    seen: set[str] = set()
    result: list[FilesystemInfo] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            mount_lines = f.readlines()
    except (FileNotFoundError, PermissionError, OSError):
        return result

    for line in mount_lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device = _unescape_mount_field(parts[0])
        mount_point = _unescape_mount_field(parts[1])
        fstype = parts[2]
        if fstype not in _DISK_FSTYPES:
            continue
        if mount_point in seen:
            continue
        try:
            stat = os.statvfs(mount_point)
        except OSError:
            continue
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = max(0, total - free)
        if total == 0:
            continue
        seen.add(mount_point)
        result.append(
            FilesystemInfo(
                device=device,
                mount_point=mount_point,
                fstype=fstype,
                used_bytes=used,
                total_bytes=total,
            )
        )
    # Stable display order: shortest mount point first (/ before /boot
    # before /var/lib/something).
    result.sort(key=lambda fs: (len(fs.mount_point), fs.mount_point))
    return result


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


def get_cpu_count() -> int:
    """Return the number of logical CPUs."""
    return os.cpu_count() or 1


def read_cpu_times() -> tuple[int, int]:
    """Return (idle, total) CPU jiffies from the first line of /proc/stat."""
    try:
        with open("/proc/stat") as f:
            fields = [int(x) for x in f.readline().split()[1:]]
        # cpu: user nice system idle iowait irq softirq steal guest guest_nice
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        return idle, sum(fields)
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        return 0, 0


def cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float:
    """Compute CPU utilization percent between two read_cpu_times() samples."""
    idle_delta = cur[0] - prev[0]
    total_delta = cur[1] - prev[1]
    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))


def read_net_bytes() -> tuple[int, int]:
    """Return (rx_bytes, tx_bytes) totalled over non-loopback interfaces."""
    rx = tx = 0
    try:
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:  # skip the two header rows
                name, _, rest = line.partition(":")
                if name.strip() == "lo":
                    continue
                fields = rest.split()
                if len(fields) >= 9:
                    rx += int(fields[0])
                    tx += int(fields[8])
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return rx, tx


def get_memory_usage() -> tuple[int, int]:
    """Return (used_bytes, total_bytes) of system memory."""
    total = available = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return max(0, total - available), total


def get_disk_usage(path: str = "/") -> tuple[int, int]:
    """Return (used_bytes, total_bytes) for the filesystem containing `path`."""
    try:
        usage = shutil.disk_usage(path)
        return usage.used, usage.total
    except OSError:
        return 0, 0


def format_size(num_bytes: float, decimals: int = 1) -> str:
    """Format a byte count as a human-readable string (1024-based units)."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{value:.0f} {unit}"
            return f"{value:.{decimals}f} {unit}"
        value /= 1024.0
    return f"{value:.{decimals}f} TB"


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
