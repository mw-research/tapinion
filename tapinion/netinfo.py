# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Addresses other devices can use (for QR codes), and QR code rendering."""
import io
import os
import socket

LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}


def lan_ip() -> str | None:
    """IP address of this machine in the local network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # TEST-NET address, only selects the outgoing interface
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def public_base(request) -> str:
    """Base URL for links shown to other devices.

    PUBLIC_URL wins; when the page was opened via localhost (e.g. the desktop app), the
    machine's LAN address is used instead, so tablets in the same network can follow it.
    """
    configured = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if configured:
        return configured
    url = request.url
    if url.hostname in LOOPBACK:
        ip = lan_ip()
        if ip:
            port = f":{url.port}" if url.port else ""
            return f"{url.scheme}://{ip}{port}"
    return str(request.base_url).rstrip("/")


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    return svg[svg.index("<svg"):]  # drop the XML declaration for inline use
