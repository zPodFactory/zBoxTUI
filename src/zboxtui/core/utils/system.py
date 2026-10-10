"""System information utilities."""

import math
import glob
import os
import platform
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass


DNSMASQ_RESOLV_PATH = "/var/run/dnsmasq/resolv.conf"

_NAMESERVER_RE = re.compile(
    r"^\s*nameserver\s+(\d+\.\d+\.\d+\.\d+)\s*(?:#.*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteEntry:
    """An IPv4 route for the dashboard Routes section."""

    destination: str  # e.g. 10.20.0.0/24
    via: str
    iface: str


@dataclass
class NetworkInterface:
    """Container for network interface information."""

    name: str
    ipv4: str
    gateway: str | None = None  # Gateway IP if this is the default route interface
    netmask: str | None = None  # Netmask in dotted notation
    cidr: int | None = None  # CIDR prefix length (e.g., 24)
    is_dhcp: bool = False  # From /etc/network/interfaces (dashboard [DHCP] tag)


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
    cpu_count: int
    cpu_load_percent: float       # 1-min loadavg / cpu_count * 100
    memory_total: str             # Human-readable total ("16.0 GB")
    memory_used_bytes: int
    memory_total_bytes: int
    interfaces: list[NetworkInterface]
    filesystems: list[FilesystemInfo]

    @property
    def memory_percent(self) -> float:
        if self.memory_total_bytes <= 0:
            return 0.0
        return 100.0 * self.memory_used_bytes / self.memory_total_bytes


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


def _provisioned_memory_bytes() -> int | None:
    """Return the raw RAM the hypervisor/BIOS reports to the kernel.

    /proc/meminfo's MemTotal excludes 0.5-3% reserved by the kernel
    and firmware, so a 48 GiB VM reports ~47.05 GiB there — fine for
    "what's usable" but misleading for "what's provisioned".

    /sys/devices/system/memory/ exposes the kernel's memory-block
    map, which is readable without root (unlike /proc/iomem) and
    counts the *full* provisioned RAM. Returns None on kernels that
    don't expose memory blocks (typical for some ARM builds).
    """
    root = "/sys/devices/system/memory"
    try:
        with open(f"{root}/block_size_bytes") as f:
            block_size = int(f.read().strip(), 16)
        block_count = sum(
            1
            for name in os.listdir(root)
            if name.startswith("memory") and name[6:].isdigit()
        )
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    if block_size <= 0 or block_count <= 0:
        return None
    return block_size * block_count


def get_memory_info() -> str:
    """Total memory, formatted for the dashboard header.

    Prefer the sysfs memory-block total (matches the nominal VM/host
    allocation). Fall back to /proc/meminfo's MemTotal — rounded up
    to the nearest whole GiB when the gap looks like normal kernel
    reserve overhead — if sysfs isn't available.
    """
    provisioned = _provisioned_memory_bytes()
    if provisioned is not None:
        return _format_gib_bytes(provisioned, suffix=" Memory")

    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    break
            else:
                return "Unknown Memory"
    except (FileNotFoundError, PermissionError, ValueError):
        return "Unknown Memory"

    gb_exact = kb / (1024 * 1024)
    gb_ceil = math.ceil(gb_exact)
    if gb_ceil > 0 and (gb_ceil - gb_exact) / gb_ceil <= 0.05:
        return f"{gb_ceil} GiB Memory"
    return f"{gb_exact:.1f} GiB Memory"



@dataclass(frozen=True)
class MemoryStats:
    """Memory figures shared by the dashboard and System Metrics dialog."""

    used_bytes: int
    total_bytes: int  # /proc/meminfo MemTotal — usage % denominator (dashboard bar)
    percent: float
    total_label: str  # provisioned/nominal total, e.g. "48 GiB"
    header_label: str  # dashboard header line, e.g. "48 GiB Memory"
    used_label: str  # e.g. "12.3 GiB"


def _format_gib_bytes(num_bytes: int, *, suffix: str = "") -> str:
    """Format a byte count in GiB using the same rounding as :func:`get_memory_info`."""
    gb = num_bytes / (1024**3)
    if abs(gb - round(gb)) < 0.01:
        base = f"{round(gb)} GiB"
    else:
        base = f"{gb:.1f} GiB"
    return f"{base}{suffix}" if suffix else base


def get_memory_stats() -> MemoryStats:
    """Return memory used/total aligned with the dashboard MEM Usage bar and header."""
    used, total = get_memory_usage()
    percent = 100.0 * used / total if total else 0.0
    provisioned = _provisioned_memory_bytes()
    display_total = provisioned if provisioned is not None else total
    return MemoryStats(
        used_bytes=used,
        total_bytes=total,
        percent=percent,
        total_label=_format_gib_bytes(display_total),
        header_label=get_memory_info(),
        used_label=f"{used / (1024**3):.1f} GiB",
    )


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


_NATURAL_SORT_RE = re.compile(r"(\d+)")


def interface_sort_key(name: str) -> tuple:
    """Natural sort key for interface names.

    Splits the name into text and integer runs so that numeric parts,
    such as VLAN IDs or interface indexes, compare numerically instead of
    lexically: ``eth1.64 < eth1.128`` and ``eth2 < eth10``.
    """
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in _NATURAL_SORT_RE.split(name)
        if part
    )


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
                                is_dhcp=is_dhcp_interface(current_iface),
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

    # Sort to put gateway interface first, then natural order by name so
    # VLAN IDs sort numerically (eth1.64 before eth1.128).
    interfaces.sort(key=lambda x: (x.gateway is None, interface_sort_key(x.name)))

    return interfaces


def get_system_info() -> SystemInfo:
    """Gather all system information."""
    os_name, os_version = get_os_info()
    mem = get_memory_stats()
    return SystemInfo(
        hostname=get_hostname(),
        os_name=os_name,
        os_version=os_version,
        debian_version=get_debian_version(),
        cpu_info=get_cpu_info(),
        cpu_count=get_cpu_count(),
        cpu_load_percent=get_load_percent(),
        memory_total=mem.header_label,
        memory_used_bytes=mem.used_bytes,
        memory_total_bytes=mem.total_bytes,
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




def _is_nested_mount_path(mount_point: str, parent_mount: str) -> bool:
    """True when ``mount_point`` is strictly under ``parent_mount``."""
    if mount_point == parent_mount:
        return False
    if parent_mount == "/":
        return mount_point.startswith("/") and mount_point != "/"
    return mount_point.startswith(parent_mount.rstrip("/") + "/")


def get_filesystems() -> list[FilesystemInfo]:
    """Read /proc/mounts and return real-disk filesystems with usage.

    Pseudo-filesystems (proc, sysfs, tmpfs, etc.) are filtered out via
    an allow-list of disk-fstype names. Mounts whose statvfs fails are
    silently skipped. Mount points are de-duplicated (bind mounts can
    appear twice with the same mount_point) — first one wins.
    """
    candidates: list[FilesystemInfo] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            mount_lines = f.readlines()
    except (FileNotFoundError, PermissionError, OSError):
        return []

    for line in mount_lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device = _unescape_mount_field(parts[0])
        mount_point = _unescape_mount_field(parts[1])
        fstype = parts[2]
        if fstype not in _DISK_FSTYPES:
            continue
        if not os.path.isdir(mount_point):
            continue
        try:
            stat = os.statvfs(mount_point)
        except OSError:
            continue
        total = stat.f_blocks * stat.f_frsize
        # Use f_bfree (all free blocks), not f_bavail (free blocks minus
        # the ext4 root reservation, typically 5%). Deriving "used" from
        # f_bavail silently counts the reserved blocks as used and
        # overstates usage versus df/duf/shutil.disk_usage.
        free = stat.f_bfree * stat.f_frsize
        used = max(0, total - free)
        if total == 0:
            continue
        candidates.append(
            FilesystemInfo(
                device=device,
                mount_point=mount_point,
                fstype=fstype,
                used_bytes=used,
                total_bytes=total,
            )
        )

    # Drop same-device bind mounts under an ancestor (e.g. sandboxed file
    # binds under ``/``). Keep separate partitions such as ``/boot``.
    candidates.sort(key=lambda fs: (len(fs.mount_point), fs.mount_point))
    result: list[FilesystemInfo] = []
    for fs in candidates:
        if any(
            other.device == fs.device
            and _is_nested_mount_path(fs.mount_point, other.mount_point)
            for other in result
        ):
            continue
        result.append(fs)
    return result


# Prefixes for physical NICs shown in network configuration UI
INCLUDED_INTERFACE_PREFIXES = (
    "eth",
    "ens",
)


def get_physical_interfaces() -> list[NetworkInterface]:
    """Get physical network interfaces (eth* and ens* only)."""
    all_interfaces = get_network_interfaces()
    return [
        iface
        for iface in all_interfaces
        if iface.name.startswith(INCLUDED_INTERFACE_PREFIXES)
    ]


def parse_nameserver_file(path: str) -> list[str]:
    """Parse ``nameserver x.x.x.x`` lines from a resolver file."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, PermissionError, OSError):
        return []

    servers: list[str] = []
    for line in content.splitlines():
        match = _NAMESERVER_RE.match(line)
        if match:
            servers.append(match.group(1))
    return servers


def get_dnsmasq_dns_servers(
    *,
    resolv_path: str = DNSMASQ_RESOLV_PATH,
) -> list[str]:
    """Upstream DNS from dnsmasq's resolver file (zBox DHCP)."""
    return parse_nameserver_file(resolv_path)[:2]


_IFACE_SOURCE_RE = re.compile(r"^[ \t]*source(-directory)?[ \t]+(\S+)", re.M)
_IFACE_SOURCE_DIR_NAME_RE = re.compile(r"[a-zA-Z0-9_-]+")


def read_interfaces_config(interfaces_path: str = "/etc/network/interfaces") -> str:
    """``interfaces_path`` plus every file its ``source`` and ``source-directory`` lines
    pull in, concatenated in the order ifupdown reads them.

    Debian's stock file starts with ``source /etc/network/interfaces.d/*``, and zbox-init
    drops per-interface stanzas there, so a reader that opens only the main file calls a
    configured VLAN interface unmanaged. Relative patterns resolve against the directory of
    the file that names them, as in interfaces(5); ``source-directory`` takes only names
    made of letters, digits, ``_`` and ``-``. Missing or unreadable files are skipped.
    """
    seen: set[str] = set()
    parts: list[str] = []

    def _read(path: str) -> None:
        if path in seen:
            return
        seen.add(path)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return
        parts.append(content)
        base = os.path.dirname(path) or "."
        for match in _IFACE_SOURCE_RE.finditer(content):
            is_directory, target = match.group(1), match.group(2)
            if not os.path.isabs(target):
                target = os.path.join(base, target)
            if is_directory:
                try:
                    names = sorted(os.listdir(target))
                except OSError:
                    continue
                for name in names:
                    if _IFACE_SOURCE_DIR_NAME_RE.fullmatch(name):
                        _read(os.path.join(target, name))
            else:
                for found in sorted(glob.glob(target)):
                    if os.path.isfile(found):
                        _read(found)

    _read(interfaces_path)
    return "\n".join(parts)


def get_interface_dns_servers(iface_name: str, *, interfaces_path: str = "/etc/network/interfaces") -> list[str]:
    """Parse ``dns-nameservers`` for ``iface_name`` from Debian interfaces file."""
    content = read_interfaces_config(interfaces_path)
    if not content:
        return []

    stanza = re.search(
        rf"iface\s+{re.escape(iface_name)}\s+inet\s+\w+",
        content,
    )
    if not stanza:
        return []

    dns_servers: list[str] = []
    for line in content[stanza.end() :].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^(iface|auto|allow-|mapping)\b", stripped):
            break
        if stripped.startswith("dns-nameservers"):
            dns_servers.extend(stripped.split()[1:])
            break

    return dns_servers[:2]


def resolve_interface_dns_servers(
    iface_name: str,
    *,
    interfaces_path: str = "/etc/network/interfaces",
    resolv_path: str = DNSMASQ_RESOLV_PATH,
) -> list[str]:
    """DNS for an interface: dnsmasq resolv when DHCP, else ``interfaces`` stanza."""
    if is_dhcp_interface(iface_name):
        servers = get_dnsmasq_dns_servers(resolv_path=resolv_path)
        if servers:
            return servers
    return get_interface_dns_servers(iface_name, interfaces_path=interfaces_path)


def format_dashboard_interface_addr(iface: NetworkInterface) -> str:
    """Format ``192.168.1.10/24`` for the dashboard interface row."""
    cidr = iface.cidr if iface.cidr is not None else 24
    return f"{iface.ipv4}/{cidr}" if iface.ipv4 else "-"


def get_interface_config_mode(
    iface_name: str,
    *,
    interfaces_path: str = "/etc/network/interfaces",
) -> str:
    """``[STATIC]``, ``[DHCP]``, or ``[UNMANAGED]`` for dashboard tags."""
    match = re.search(
        rf"iface\s+{re.escape(iface_name)}\s+inet\s+(\w+)",
        read_interfaces_config(interfaces_path),
    )
    if not match:
        return "[UNMANAGED]"
    return "[DHCP]" if match.group(1).lower() == "dhcp" else "[STATIC]"


def format_dashboard_network_iface_lines(
    interfaces: list[NetworkInterface],
    *,
    interfaces_path: str = "/etc/network/interfaces",
) -> list[str]:
    """Aligned per-interface rows for the dashboard network block."""
    if not interfaces:
        return []
    name_width = max(len(f"{iface.name}:") for iface in interfaces)
    addr_width = max(
        len(format_dashboard_interface_addr(iface)) for iface in interfaces
    )
    lines: list[str] = []
    for iface in interfaces:
        name_col = f"{iface.name}:".ljust(name_width)
        addr = format_dashboard_interface_addr(iface)
        mode = get_interface_config_mode(iface.name, interfaces_path=interfaces_path)
        lines.append(f"  → {name_col}  {addr.ljust(addr_width)}  {mode}")
    return lines




_ROUTE_VIA_RE = re.compile(
    r"^(\S+)\s+via\s+(\d+\.\d+\.\d+\.\d+)\s+dev\s+(\S+)"
)


def get_additional_ipv4_routes() -> list[RouteEntry]:
    """Non-default IPv4 routes with an explicit gateway (``ip -4 route``)."""
    routes: list[RouteEntry] = []
    try:
        result = subprocess.run(
            ["ip", "-4", "route", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return routes
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("default "):
                continue
            match = _ROUTE_VIA_RE.match(stripped)
            if match:
                dest, via, iface = match.group(1), match.group(2), match.group(3)
                if "@" in iface:
                    iface = iface.split("@", 1)[0]
                routes.append(RouteEntry(destination=dest, via=via, iface=iface))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return routes


def _format_route_row(
    destination: str,
    via: str,
    iface: str | None,
    *,
    dest_width: int,
    via_width: int,
) -> str:
    dest_col = destination.ljust(dest_width)
    via_col = via.ljust(via_width)
    if iface:
        return f"  → {dest_col}  via {via_col}  ({iface})"
    return f"  → {dest_col}  via {via_col}"


def format_dashboard_network_routing_lines(
    default_gw_ip: str | None,
    default_gw_iface: str | None,
    extra_routes: list[RouteEntry] | None = None,
    *,
    visible_iface_names: frozenset[str] | None = None,
) -> list[str]:
    """Routes and DNS sections for the dashboard network block."""
    if extra_routes is None:
        extra_routes = get_additional_ipv4_routes()

    def _route_iface(iface: str | None) -> str | None:
        if iface is None:
            return None
        if visible_iface_names is not None and iface not in visible_iface_names:
            return None
        return iface

    route_rows: list[tuple[str, str, str | None]] = []
    if default_gw_ip or default_gw_iface:
        route_rows.append(
            ("default", default_gw_ip or "(none)", _route_iface(default_gw_iface))
        )
    else:
        route_rows.append(("default", "(none)", None))
    for route in extra_routes:
        iface = _route_iface(route.iface)
        if visible_iface_names is not None and route.iface is not None and iface is None:
            continue
        route_rows.append((route.destination, route.via, iface))
    dest_width = max(len(dest) for dest, _, _ in route_rows)
    via_width = max(len(via) for _, via, _ in route_rows)
    lines: list[str] = ["Routes:"]
    for dest, via, iface in route_rows:
        lines.append(
            _format_route_row(dest, via, iface, dest_width=dest_width, via_width=via_width)
        )
    lines.append("")
    lines.append("DNS:")
    if default_gw_iface:
        servers = resolve_interface_dns_servers(default_gw_iface)
    else:
        servers = []
    if servers:
        lines.extend(f"  → {server}" for server in servers)
    else:
        lines.append("  → (none)")
    return lines

def format_dashboard_interface_mode(iface: NetworkInterface) -> str:
    """``[STATIC]`` or ``[DHCP]`` when configured; else ``None``."""
    return get_interface_config_mode(iface.name)


def format_dashboard_interface_line(iface: NetworkInterface) -> str:
    """Address plus mode tag (legacy helper)."""
    addr = format_dashboard_interface_addr(iface)
    mode = format_dashboard_interface_mode(iface)
    return f"{addr}  {mode}"


def format_dashboard_dns_servers(iface_name: str | None) -> str:
    """Comma-separated DNS list for the dashboard (DHCP → dnsmasq resolv)."""
    if not iface_name:
        return "-"
    servers = resolve_interface_dns_servers(iface_name)
    return ", ".join(servers) if servers else "-"


def is_dhcp_interface(
    iface_name: str,
    *,
    interfaces_path: str = "/etc/network/interfaces",
) -> bool:
    """Check if an interface is configured for DHCP in /etc/network/interfaces
    (``source``d files included).

    Args:
        iface_name: The interface name to check (e.g., 'eth0').

    Returns:
        True if configured for DHCP, False if static or unknown.
    """
    # Look for "iface eth0 inet dhcp" pattern
    pattern = rf"iface\s+{re.escape(iface_name)}\s+inet\s+(\w+)"
    match = re.search(pattern, read_interfaces_config(interfaces_path))
    return bool(match) and match.group(1).lower() == "dhcp"


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

    is_dhcp = is_dhcp_interface(iface_name)
    dns_servers = resolve_interface_dns_servers(iface_name)
    dns1 = dns_servers[0] if dns_servers else ""
    dns2 = dns_servers[1] if len(dns_servers) > 1 else ""

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


def get_load_average() -> tuple[float, float, float]:
    """Return the system load averages (1, 5, 15 minute) from /proc/loadavg.

    Falls back to (0, 0, 0) if /proc/loadavg can't be read or parsed.
    On a real Linux box this is a single ~zero-cost read; perfect for
    a snapshot dashboard that wants a stable "is this box busy?"
    indicator without sampling /proc/stat twice.
    """
    try:
        with open("/proc/loadavg", encoding="utf-8") as f:
            parts = f.read().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        return 0.0, 0.0, 0.0


def get_load_percent() -> float:
    """1-minute load average expressed as a percentage of total CPU capacity.

    100% means the runqueue length matches the number of logical CPUs
    over the last minute. Values above 100 are possible (oversubscribed
    box) — callers that drive a ProgressBar should clamp visually.
    """
    load_1, _, _ = get_load_average()
    cpu_count = get_cpu_count()
    if cpu_count <= 0:
        return 0.0
    return 100.0 * load_1 / cpu_count


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
