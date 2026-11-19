from tapinion.discovery import dns_label, service_label


def test_long_mac_host_names_fit_into_dns_sd():
    host = "sat12-bq159-8cac0e31-b102-4e27-8b3a-3fb395db5835-1225A582FEFB"
    assert len(service_label(host).encode()) <= 63 and service_label(host).startswith("Tapinion sat12")
    assert len(dns_label(host)) <= 63
    assert service_label("Büro-Mäc") == "Tapinion Büro-Mäc"
    assert dns_label("Büro Mäc") == "B-ro-M-c"
    assert len(service_label("ä" * 40).encode()) <= 63


def test_announce_with_a_long_name_registers():
    import socket

    from tapinion import discovery
    from tapinion.netinfo import lan_ip

    ip = lan_ip()
    if not ip:
        return
    real = socket.gethostname
    socket.gethostname = lambda: "sat12-bq159-8cac0e31-b102-4e27-8b3a-3fb395db5835-1225A582FEFB"
    try:
        withdraw = discovery.announce(8799, ip, "test", "abc")
    finally:
        socket.gethostname = real
    assert withdraw.__name__ == "withdraw"  # registered, not the no-op fallback
    withdraw()
