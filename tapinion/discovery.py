# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announce Tapinion in the local network (mDNS / DNS-SD, "_tapinion._tcp"), so the Android
app finds the computer by itself – no address to type, no QR code needed."""
import logging
import socket

SERVICE_TYPE = "_tapinion._tcp.local."
log = logging.getLogger("tapinion.discovery")


def announce(port: int, ip: str | None, version: str):
    """Register the service; returns a function that withdraws it. Never raises."""
    if not ip:
        return lambda: None
    try:
        from zeroconf import ServiceInfo, Zeroconf

        host = socket.gethostname().split(".")[0] or "computer"
        info = ServiceInfo(
            SERVICE_TYPE,
            f"Tapinion {host}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"path": "/", "version": version, "host": host},
            server=f"{host}.local.",
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
