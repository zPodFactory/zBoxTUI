# Trademark and design-attribution notice

## Trademarks

| Mark | Owner (typical) | Use in zBoxTUI |
|------|-----------------|----------------|
| VMware, ESXi | Broadcom Inc. | Layout inspiration; `vmware-esxi` theme name |
| XenServer, Citrix | Cloud Software Group / legacy Citrix branding | Historical lineage of host-console UIs in this space |
| XCP-ng | XCP-ng project / community | Layout and ncurses-style console inspiration |

VMware, ESXi, XenServer, Citrix, XCP-ng, and related marks are trademarks or
registered trademarks of their respective owners in the United States and other
jurisdictions.

zBoxTUI is an **independent open-source project**. It is **not** affiliated with,
endorsed by, or sponsored by VMware, Broadcom, Cloud Software Group, Citrix,
XCP-ng, or any hypervisor vendor.

## Design inspiration (not copies)

zBoxTUI’s operator experience is **inspired by** familiar hypervisor host consoles,
reimplemented with [Textual](https://textual.textualize.io/) for Debian-based
zBox appliances:

1. **VMware ESXi Direct Console UI (DCUI)** — dashboard-style home, F-key
   actions, modal configuration flows, and the yellow/grey **`vmware-esxi`** colour
   theme (approximation only).
2. **XCP-ng Host Configuration Console (`xsconsole`)** — classic **ncurses** host
   menu: left-hand section list, right-hand detail, and keyboard-driven
   configuration (network, system info, local shell entry, etc.). zBoxTUI does not
   ship or embed `xsconsole`; the resemblance is intentional but the code and
   styling are original.

Theme and layout choices are **approximations for operator familiarity**, not
official branding assets from any vendor.

## Similar ncurses / text UIs (reference only)

These are common in the same problem space. zBoxTUI is **not** derived from their
codebases and is **not** claiming compatibility with them:

| Interface | Notes |
|-----------|--------|
| **Citrix XenServer host console** | Predecessor to XCP-ng `xsconsole`; same general ncurses host-menu pattern |
| **XCP-ng `xsconsole`** | Primary ncurses parallel cited above |
| **VMware ESXi DCUI** | Text/graphical DCUI on the hypervisor console (see above) |
| **Proxmox VE installer / menus** | ncurses in installer and some tools; different product model (no persistent host DCUI like ESXi/xsconsole) |
| **OVirt / RHV host TUI** | Vendor-specific; not a design target for zBoxTUI |
| **IPMI / BMC serial menus** | Firmware text menus; unrelated implementation |

If you know of another host-side text console worth citing, open an issue — we
only list interfaces we consciously considered.

## Built-in theme names

- **`catppuccin-mocha`** (default) — colours from the official [Catppuccin Mocha
  palette](https://catppuccin.com/palette/) ([catppuccin.com](https://catppuccin.com/)).
  Catppuccin is a community palette project; zBoxTUI is not affiliated with it.
- **`vmware-esxi`** — visual style only (yellow body, grey chrome); not VMware
  product branding.
- Other themes (`nord`, `gruvbox`, etc.) are independent palettes with no vendor
  affiliation.
