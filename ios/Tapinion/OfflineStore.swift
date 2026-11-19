// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import CryptoKit
import Foundation

/// Events stored on the device for offline use (same layout and server API as the Android app).
/// Every kiosk opened in the app is kept here (question, design, logo, PIN check). Ratings
/// collected offline wait here and are sent to the computer once it is reachable; each rating
/// has an id, so sending twice is harmless.
///
/// Layout: Application Support/offline/<token>/{bundle.json, meta.json, votes.json}
final class OfflineStore {
    struct Entry: Identifiable {
        var id: String { token }
        let token, name, date, mode, origin, device, instance, syncedAt: String
        let active, switchedOff: Bool
        let pending: Int
    }

    struct SyncResult {
        var sent = 0, events = 0
        var reachable = false
    }

    struct HTTPError: Error {
        let status: Int
    }

    private let root: URL
    private let lock = NSRecursiveLock()

    init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        root = base.appendingPathComponent("offline", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    // MARK: events

    func save(token: String, origin: String, device: String, bundleJson: String) throws {
        guard let bundle = Self.object(bundleJson) else { throw HTTPError(status: 0) }
        lock.lock(); defer { lock.unlock() }
        let d = dir(token)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        write(d.appendingPathComponent("bundle.json"), bundleJson)
        var meta = Self.object(read(d.appendingPathComponent("meta.json"))) ?? [:]
        meta["origin"] = origin
        meta["device"] = device
        meta["instance"] = (bundle["server"] as? [String: Any])?["instance"] as? String ?? ""
        meta["synced_at"] = Self.now()
        meta["switched_off"] = false
        write(d.appendingPathComponent("meta.json"), Self.json(meta))
    }

    func has(_ token: String) -> Bool {
        FileManager.default.fileExists(atPath: dir(token).appendingPathComponent("bundle.json").path)
    }

    func bundle(_ token: String) -> String {
        lock.lock(); defer { lock.unlock() }
        return read(dir(token).appendingPathComponent("bundle.json"), fallback: "{}")
    }

    func list() -> [Entry] {
        lock.lock(); defer { lock.unlock() }
        let dirs = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        var out: [Entry] = []
        for d in dirs {
            guard let b = Self.object(read(d.appendingPathComponent("bundle.json"))),
                  let ev = b["event"] as? [String: Any] else { continue }  // a broken entry is skipped
            let m = Self.object(read(d.appendingPathComponent("meta.json"))) ?? [:]
            let token = d.lastPathComponent
            out.append(Entry(token: token, name: ev["name"] as? String ?? "", date: ev["date"] as? String ?? "",
                             mode: ev["mode"] as? String ?? "", origin: m["origin"] as? String ?? "",
                             device: m["device"] as? String ?? "", instance: m["instance"] as? String ?? "",
                             syncedAt: m["synced_at"] as? String ?? "", active: ev["active"] as? Bool ?? true,
                             switchedOff: m["switched_off"] as? Bool ?? false, pending: unsent(token).count))
        }
        return out.sorted { $0.date > $1.date }
    }

    func remove(_ token: String) {
        lock.lock(); defer { lock.unlock() }
        try? FileManager.default.removeItem(at: dir(token))
    }

    /// The computer got a new address: move all its events there.
    func moveOrigin(instance: String, to newOrigin: String) {
        lock.lock(); defer { lock.unlock() }
        for e in list() where e.instance == instance && e.origin != newOrigin {
            let f = dir(e.token).appendingPathComponent("meta.json")
            var m = Self.object(read(f)) ?? [:]
            m["origin"] = newOrigin
            write(f, Self.json(m))
        }
    }

    // MARK: ratings

    func addVote(token: String, value: String, lang: String) {
        lock.lock(); defer { lock.unlock() }
        var all = votes(token)
        all.append(["id": UUID().uuidString.lowercased(), "value": value, "lang": lang, "ts": Self.now(), "sent": false])
        write(dir(token).appendingPathComponent("votes.json"), Self.json(all))
    }

    func pending(_ token: String) -> Int { unsent(token).count }

    /// All ratings collected on this device for the event (results screen, offline kiosk).
    func votesJson(_ token: String) -> String { Self.json(votes(token)) }

    private func unsent(_ token: String) -> [[String: Any]] {
        votes(token).filter { !($0["sent"] as? Bool ?? false) }.map {
            ["id": $0["id"] ?? "", "value": $0["value"] ?? "", "ts": $0["ts"] ?? "", "lang": $0["lang"] ?? ""]
        }
    }

    func checkPin(token: String, pin: String) -> Bool {
        guard let b = Self.object(bundle(token)), let ev = b["event"] as? [String: Any],
              let p = ev["pin"] as? [String: Any], let expected = p["sha256"] as? String,
              !expected.isEmpty, !pin.isEmpty else { return false }
        let digest = SHA256.hash(data: Data(((p["salt"] as? String ?? "") + pin).utf8))
        return digest.map { String(format: "%02x", $0) }.joined() == expected
    }

    private func markSent(_ token: String, accepted: Set<String>, rejected: Set<String>) {
        lock.lock(); defer { lock.unlock() }
        let all = votes(token).map { v -> [String: Any] in
            var v = v
            let id = v["id"] as? String ?? ""
            if accepted.contains(id) { v["sent"] = true }
            if rejected.contains(id) { v["sent"] = true; v["rejected"] = true }
            return v
        }
        write(dir(token).appendingPathComponent("votes.json"), Self.json(all))
    }

    private func markSwitchedOff(_ token: String) {
        lock.lock(); defer { lock.unlock() }
        let f = dir(token).appendingPathComponent("meta.json")
        var m = Self.object(read(f)) ?? [:]
        m["switched_off"] = true
        write(f, Self.json(m))
    }

    // MARK: synchronisation

    /// Instance id of the Tapinion at this address, or nil if it is not reachable.
    static func instanceAt(_ origin: String) async -> String? {
        guard let body = try? await http("GET", origin + "/healthz", timeout: 3) else { return nil }
        return object(body)?["instance"] as? String ?? ""
    }

    /// Keep an event for offline use: own device key (paired with the kiosk's key), then download.
    func pairAndDownload(origin: String, token: String, kioskKey: String) async throws {
        let body = try await Self.http("POST", "\(origin)/api/kiosk/\(token)/pair", device: kioskKey, json: "{}", timeout: 8)
        guard let device = Self.object(body)?["device"] as? String else { throw HTTPError(status: 0) }
        try await download(origin: origin, token: token, device: device)
    }

    func download(origin: String, token: String, device: String) async throws {
        let body = try await Self.http("GET", "\(origin)/api/kiosk/\(token)", device: device, timeout: 8)
        try save(token: token, origin: origin, device: device, bundleJson: body)
    }

    /// Send waiting ratings and refresh the event data of every stored event that is reachable.
    func syncAll() async -> SyncResult {
        var r = SyncResult()
        var unreachable = Set<String>()
        for e in list() {
            if e.origin.isEmpty || unreachable.contains(e.origin) { continue }
            if await Self.instanceAt(e.origin) == nil {
                unreachable.insert(e.origin)
                continue
            }
            r.reachable = true
            r.events += 1
            do {
                let votes = unsent(e.token)
                if !votes.isEmpty {
                    let body = try await Self.http("POST", "\(e.origin)/api/kiosk/\(e.token)/votes", device: e.device,
                                                   json: Self.json(["votes": votes]), timeout: 15)
                    let res = Self.object(body) ?? [:]
                    let accepted = Set(res["accepted"] as? [String] ?? [])
                    let rejected = Set(res["rejected"] as? [String] ?? [])  // never accepted
                    r.sent += accepted.count
                    markSent(e.token, accepted: accepted, rejected: rejected)
                }
                try await download(origin: e.origin, token: e.token, device: e.device)
            } catch let err as HTTPError where err.status == 403 || err.status == 404 {
                markSwitchedOff(e.token)
            } catch {
                // try again next time
            }
        }
        return r
    }

    // MARK: helpers

    static func http(_ method: String, _ url: String, device: String? = nil, json: String? = nil,
                     timeout: TimeInterval) async throws -> String {
        guard let u = URL(string: url) else { throw HTTPError(status: 0) }
        var req = URLRequest(url: u, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        req.httpMethod = method
        if let device { req.setValue(device, forHTTPHeaderField: "X-Kiosk-Device") }
        if let json {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = Data(json.utf8)
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status >= 400 { throw HTTPError(status: status) }
        return String(decoding: data, as: UTF8.self)
    }

    private func dir(_ token: String) -> URL {
        let safe = String(token.map { $0.isLetter && $0.isASCII || $0.isNumber && $0.isASCII || $0 == "_" || $0 == "-" ? $0 : "_" })
        return root.appendingPathComponent(safe, isDirectory: true)
    }

    private func votes(_ token: String) -> [[String: Any]] {
        let text = read(dir(token).appendingPathComponent("votes.json"), fallback: "[]")
        return (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [[String: Any]] ?? []
    }

    private func read(_ f: URL, fallback: String = "{}") -> String {
        (try? String(contentsOf: f, encoding: .utf8)) ?? fallback
    }

    /// Atomic write: a power cut never leaves a half-written file.
    private func write(_ f: URL, _ text: String) {
        try? Data(text.utf8).write(to: f, options: .atomic)
    }

    static func object(_ text: String) -> [String: Any]? {
        (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any]
    }

    static func json(_ value: Any) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: value) else { return "{}" }
        return String(decoding: d, as: UTF8.self)
    }

    private static func now() -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.string(from: Date())
    }
}
