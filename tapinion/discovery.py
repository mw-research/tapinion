# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announce Tapinion in the local network (mDNS / DNS-SD, "_tapinion._tcp"), so the Android
app finds the computer by itself – no address to type, no QR code needed."""
import logging
import re
import socket

SERVICE_TYPE = "_tapinion._tcp.local."
log = logging.getLogger("tapinion.discovery")


def service_label(host: str) -> str:
    """'Tapinion <host>', cut to the 63 bytes a DNS-SD instance name may have (long Mac names)."""
    label = f"Tapinion {host}"
    while len(label.encode("utf-8")) > 63:
        label = label[:-1]
    return label.rstrip()


def dns_label(host: str) -> str:
    """Host name usable as a single DNS label: letters, digits and hyphens, at most 63."""
    return re.sub(r"[^A-Za-z0-9-]", "-", host)[:63].strip("-") or "computer"


def announce(port: int, ip: str | None, version: str, instance: str = ""):
    """Register the service; returns a function that withdraws it. Never raises."""
    if not ip:
        return lambda: None
    try:
        from zeroconf import ServiceInfo, Zeroconf

        host = socket.gethostname().split(".")[0] or "computer"
        info = ServiceInfo(
            SERVICE_TYPE,
            f"{service_label(host)}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"path": "/", "version": version, "host": host, "instance": instance},
            server=f"{dns_label(host)}.local.",
        )
        zc = Zeroconf(interfaces=[ip])
        zc.register_service(info, allow_name_change=True)
    except Exception as exc:  # no network, blocked multicast, missing library: discovery is optional
        log.warning("network announcement not available: %s", exc)
        return lambda: None

    def withdraw():
        try:
            zc.unregister_service(info)
            zc.close()
        except Exception:
            pass

    return withdraw
