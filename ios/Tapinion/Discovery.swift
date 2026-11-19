// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import Foundation

/// Finds Tapinion installations in the Wi-Fi (mDNS / DNS-SD "_tapinion._tcp"). Every installation
/// announces a fixed id ("instance") in its TXT record, so a computer that got a new address is
/// found again. Runs on the main thread.
final class Discovery: NSObject, NetServiceBrowserDelegate, NetServiceDelegate {
    struct Found {
        let name, url, instance: String
    }

    private let browser = NetServiceBrowser()
    private var services: [NetService] = []
    private let onFound: (Found) -> Void

    init(onFound: @escaping (Found) -> Void) {
        self.onFound = onFound
        super.init()
        browser.delegate = self
    }

    func start() {
        browser.searchForServices(ofType: "_tapinion._tcp.", inDomain: "local.")
    }

    func stop() {
        browser.stop()
        services.forEach { $0.stop() }
        services.removeAll()
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        services.append(service)
        service.delegate = self
        service.resolve(withTimeout: 5)
    }

    func netServiceDidResolveAddress(_ sender: NetService) {
        guard let host = Self.ipv4(sender.addresses ?? []), sender.port > 0 else { return }
        var instance = ""
        if let txt = sender.txtRecordData(),
           let id = NetService.dictionary(fromTXTRecord: txt)["instance"] {
            instance = String(decoding: id, as: UTF8.self)
        }
        onFound(Found(name: sender.name, url: "http://\(host):\(sender.port)", instance: instance))
    }

    private static func ipv4(_ addresses: [Data]) -> String? {
        for data in addresses {
            let ip: String? = data.withUnsafeBytes { raw in
                guard raw.count >= MemoryLayout<sockaddr_in>.size else { return nil }
                let sa = raw.load(as: sockaddr_in.self)
                guard sa.sin_family == sa_family_t(AF_INET) else { return nil }
                var addr = sa.sin_addr
                var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                guard inet_ntop(AF_INET, &addr, &buf, socklen_t(INET_ADDRSTRLEN)) != nil else { return nil }
                return String(cString: buf)
            }
            if let ip { return ip }
        }
        return nil
    }

    /// "http://host:port" of the installation with this id, or nil if not found in time.
    @MainActor
    static func find(instance: String, timeout: TimeInterval) async -> String? {
        guard !instance.isEmpty else { return nil }
        return await withCheckedContinuation { cont in
            var done = false
            var discovery: Discovery?
            func finish(_ url: String?) {
                guard !done else { return }
                done = true
                discovery?.stop()
                discovery = nil
                cont.resume(returning: url)
            }
            discovery = Discovery { found in
                if found.instance == instance { finish(found.url) }
            }
            discovery?.start()
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { finish(nil) }
        }
    }
}
