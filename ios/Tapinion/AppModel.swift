// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import SwiftUI
import UIKit
import WebKit

func L(_ key: String, _ args: CVarArg...) -> String {
    let format = NSLocalizedString(key, comment: "")
    return args.isEmpty ? format : String(format: format, arguments: args)
}

/// Tapinion for iPad and iPhone – the slim companion of the program on the computer (same
/// behaviour as the Android app):
/// - connects to Tapinion (found in the Wi-Fi by itself, or by QR code) and shows its kiosk;
/// - keeps every event opened here for offline use and runs the kiosk without the computer;
/// - sends the ratings collected offline once the computer is reachable again (also at a new
///   address: it is found again in the Wi-Fi by its installation id);
/// - shows the results of its offline events. Events are created on the computer only.
@MainActor
final class AppModel: ObservableObject {
    enum Mode: Equatable {
        case setup
        case connecting(String)
        case web(String)
        case offlineKiosk(String, locked: Bool)
        case results(String)
    }

    private enum Key {
        static let url = "url"
        static let instance = "instance"
        static let lastKiosk = "last_kiosk"          // web kiosk that was running
        static let runningOffline = "running_offline" // offline kiosk that was running
        static let activeKiosk = "active_kiosk"      // token of a kiosk that is unlocked; left with the PIN only
    }

    static let pageTimeout: TimeInterval = 12  // a page that takes longer counts as unreachable

    @Published private(set) var mode: Mode = .setup
    @Published private(set) var screen = 0          // new web view for every screen
    @Published private(set) var error: String?
    @Published private(set) var found: [Discovery.Found] = []
    @Published private(set) var entries: [OfflineStore.Entry] = []
    @Published private(set) var syncStatus: String?
    @Published var toast: String?
    @Published private(set) var kioskRunning = false   // the web kiosk is unlocked and running (reported by the page)
    @Published private(set) var guidedAccess = UIAccessibility.isGuidedAccessEnabled

    let store = OfflineStore()
    private let prefs = UserDefaults.standard
    private var origin: String?
    private var pinned = false
    private var syncing = false
    private var attempt = 0
    private var webFailures = 0
    private var pageFinished = false
    private var offlineStarted = false   // the offline kiosk is past its PIN screen
    private var watchdog: DispatchWorkItem?
    private var discovery: Discovery?
    private var syncTimer: Timer?
    weak var webView: WKWebView?

    init() {
        UIApplication.shared.isIdleTimerDisabled = true
        NotificationCenter.default.addObserver(forName: UIAccessibility.guidedAccessStatusDidChangeNotification,
                                               object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.guidedAccess = UIAccessibility.isGuidedAccessEnabled }
        }
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-reset") {  // UI tests: start like a fresh installation
            for k in [Key.url, Key.instance, Key.lastKiosk, Key.runningOffline, Key.activeKiosk] { prefs.removeObject(forKey: k) }
            store.list().forEach { store.remove($0.token) }
        }
        if let i = args.firstIndex(of: "-connect"), i + 1 < args.count {
            connect(args[i + 1])
        } else {
            route()
        }
    }

    var activeKiosk: String? { prefs.string(forKey: Key.activeKiosk) }

    /// Where to continue after a start: a running offline kiosk, a running web kiosk, or the start screen.
    private func route() {
        let running = prefs.string(forKey: Key.runningOffline)
        let url = prefs.string(forKey: Key.url)
        if let running, store.has(running) {
            showOfflineKiosk(running, locked: false)
        } else if let url {
            showConnecting(prefs.string(forKey: Key.lastKiosk) ?? url)
        } else {
            showSetup()
        }
    }

    func becameActive() {
        syncTimer?.invalidate()
        syncTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.runSync(showStatus: false) }
        }
        if mode == .setup { startDiscovery() }
        guidedAccess = UIAccessibility.isGuidedAccessEnabled
    }

    func becameInactive() {
        syncTimer?.invalidate()
        syncTimer = nil
        stopDiscovery()
    }

    // MARK: connecting

    /// Check that the computer answers before loading anything: at most a few seconds, then the
    /// kiosk (computer reachable, also at a new address), the offline kiosk, or the start screen.
    func showConnecting(_ target: String) {
        if activeKiosk != nil { startPinning() } else { stopPinning() }
        stopDiscovery()
        cancelWatchdog()
        let o = Self.originOf(target)
        mode = .connecting(o.replacingOccurrences(of: "http://", with: ""))
        screen += 1
        attempt += 1
        let my = attempt
        let instance = prefs.string(forKey: Key.instance)
        Task {
            var result: String? = await OfflineStore.instanceAt(o) != nil ? o : nil
            if result == nil, let instance { result = await Discovery.find(instance: instance, timeout: 5) }
            guard my == attempt, case .connecting = mode else { return }  // cancelled meanwhile
            if let result {
                if result != o, let instance { movedTo(instance: instance, from: o, to: result) }
                showWeb(result + String(target.dropFirst(o.count)))
            } else {
                continueOffline(target)
            }
        }
    }

    /// The token of a running kiosk that is stored on the device, else nil.
    var guardedToken: String? {
        guard let t = activeKiosk, store.has(t) else { return nil }
        return t
    }

    /// Leave the connecting screen: a running kiosk continues offline (PIN to leave), else the overview.
    func cancelConnecting() {
        attempt += 1
        if let token = guardedToken {
            showOfflineKiosk(token, locked: false)
        } else {
            prefs.removeObject(forKey: Key.activeKiosk)  // nothing to protect on this device
            showSetup()
        }
    }

    /// Computer not reachable: continue a running kiosk from the device, else the start screen.
    private func continueOffline(_ failedUrl: String) {
        let token = Self.tokenOf(prefs.string(forKey: Key.lastKiosk)) ?? Self.tokenOf(failedUrl)
        if let token, store.has(token) {
            showOfflineKiosk(token, locked: false)
        } else {
            showSetup(error: L("unreachable", Self.originOf(failedUrl).replacingOccurrences(of: "http://", with: "")))
        }
    }

    // MARK: start screen

    func showSetup(error: String? = nil) {
        prefs.removeObject(forKey: Key.activeKiosk)  // the overview is only reached once no kiosk runs
        stopPinning()
        cancelWatchdog()
        self.error = error
        syncStatus = nil
        found = []
        mode = .setup
        screen += 1
        renderOffline()
        if !entries.isEmpty { runSync(showStatus: false) }
        startDiscovery()
    }

    func renderOffline() {
        entries = store.list()
    }

    func delete(_ e: OfflineStore.Entry) {
        store.remove(e.token)
        if e.token == prefs.string(forKey: Key.runningOffline) { prefs.removeObject(forKey: Key.runningOffline) }
        renderOffline()
    }

    var currentAddress: String { prefs.string(forKey: Key.url) ?? "" }

    func connect(_ input: String) {
        var raw = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty { return }
        if !raw.hasPrefix("http://") && !raw.hasPrefix("https://") { raw = "http://" + raw }
        guard let u = URLComponents(string: raw), let host = u.host, !host.isEmpty else {
            showSetup(error: L("setup_invalid"))
            return
        }
        stopDiscovery()
        prefs.set(raw, forKey: Key.url)
        prefs.removeObject(forKey: Key.lastKiosk)
        prefs.removeObject(forKey: Key.instance)
        let base = Self.originOf(raw)
        Task {
            if let instance = await OfflineStore.instanceAt(base), !instance.isEmpty {
                prefs.set(instance, forKey: Key.instance)
            }
        }
        showConnecting(raw)
    }

    // MARK: synchronisation

    /// Find moved computers again, send waiting ratings, refresh offline events.
    func runSync(showStatus: Bool) {
        if syncing { return }
        syncing = true
        if showStatus { syncStatus = L("sync_running") }
        Task {
            await rediscoverAll()
            let r = await store.syncAll()
            syncing = false
            if case .offlineKiosk(let token, _) = mode {  // the footer of a running offline kiosk shows what still waits
                webView?.evaluateJavaScript("window.__tapinionSetVotes && window.__tapinionSetVotes(\(store.votesJson(token)))")
            }
            guard mode == .setup else { return }
            renderOffline()
            if showStatus { syncStatus = r.reachable ? L("sync_done", r.sent) : L("sync_unreachable") }
        }
    }

    /// Computers whose address changed are looked up in the Wi-Fi by their installation id.
    private func rediscoverAll() async {
        var instances: [String: String] = [:]  // instance -> known origin
        for e in store.list() where !e.instance.isEmpty { instances[e.instance] = e.origin }
        if let url = prefs.string(forKey: Key.url), let mine = prefs.string(forKey: Key.instance) {
            instances[mine] = Self.originOf(url)
        }
        for (instance, known) in instances {
            if await OfflineStore.instanceAt(known) != nil { continue }
            if let moved = await Discovery.find(instance: instance, timeout: 6) {
                movedTo(instance: instance, from: known, to: moved)
            }
        }
    }

    private func movedTo(instance: String, from oldOrigin: String, to newOrigin: String) {
        store.moveOrigin(instance: instance, to: newOrigin)
        guard instance == prefs.string(forKey: Key.instance) else { return }
        for key in [Key.url, Key.lastKiosk] {
            if let u = prefs.string(forKey: key), u.hasPrefix(oldOrigin) {
                prefs.set(newOrigin + u.dropFirst(oldOrigin.count), forKey: key)
            }
        }
    }

    // MARK: finding Tapinion in the Wi-Fi for the start screen

    private func startDiscovery() {
        guard discovery == nil, mode == .setup else { return }
        let d = Discovery { [weak self] f in
            guard let self, self.mode == .setup, !self.found.contains(where: { $0.url == f.url }) else { return }
            self.found.append(f)
        }
        discovery = d
        d.start()
    }

    private func stopDiscovery() {
        discovery?.stop()
        discovery = nil
    }

    // MARK: Tapinion on the computer (web)

    private func showWeb(_ url: String) {
        stopDiscovery()
        pageFinished = false
        kioskRunning = false
        origin = Self.originOf(url)
        mode = .web(url)
        screen += 1
        scheduleWatchdog()
    }

    /// The kiosk page from the computer hands over a kiosk for offline use (it is unlocked and running).
    func kioskReady(token: String, kioskKey: String) {
        prefs.set(token, forKey: Key.activeKiosk)
        kioskRunning = true
        startPinning()
        guard let o = origin, !store.has(token) else { return }
        Task {
            do {
                try await store.pairAndDownload(origin: o, token: token, kioskKey: kioskKey)
                if let instance = await OfflineStore.instanceAt(o), !instance.isEmpty { prefs.set(instance, forKey: Key.instance) }
                showToast(L("offline_saved"))
            } catch {
                // next time the kiosk opens
            }
        }
    }

    func isSameOrigin(_ url: URL) -> Bool {
        Self.originOf(url.absoluteString) == origin
    }

    var locked: Bool { pinned }

    func pageStarted(_ page: String?) {
        kioskRunning = false
        pageFinished = false
        scheduleWatchdog()
        if !Self.isKioskPage(page) { stopPinning() }
    }

    func pageDidFinish(_ page: String?) {
        objectWillChange.send()  // the overview button depends on the kiosk state
        pageFinished = true
        webFailures = 0
        cancelWatchdog()
        if Self.isKioskPage(page) {
            prefs.set(page, forKey: Key.lastKiosk)
        } else {
            // A running kiosk only reaches other pages after the PIN (the server redirects to the
            // login page, or to the setup wizard on a fresh installation).
            prefs.removeObject(forKey: Key.lastKiosk)
            prefs.removeObject(forKey: Key.activeKiosk)
            stopPinning()
        }
    }

    /// The computer did not answer: check once more (new address?), else continue offline.
    func unreachable(_ failedUrl: String?) {
        guard case .web = mode else { return }  // watchdog and error can both report the same failure
        cancelWatchdog()
        stopPinning()
        webFailures += 1
        let u = failedUrl ?? prefs.string(forKey: Key.url) ?? ""
        if webFailures >= 2 { continueOffline(u) } else { showConnecting(u) }
    }

    private func scheduleWatchdog() {
        cancelWatchdog()
        let item = DispatchWorkItem { [weak self] in
            guard let self, case .web = self.mode, !self.pageFinished else { return }
            let u = self.webView?.url?.absoluteString
            self.webView?.stopLoading()
            self.unreachable(u)
        }
        watchdog = item
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.pageTimeout, execute: item)
    }

    private func cancelWatchdog() {
        watchdog?.cancel()
        watchdog = nil
    }

    /// The overview button over web pages: not while a kiosk runs (left with the PIN only).
    var canLeaveWeb: Bool { !kioskRunning && activeKiosk == nil }

    // MARK: offline kiosk and results (from the device)

    func showOfflineKiosk(_ token: String, locked: Bool) {
        stopDiscovery()
        cancelWatchdog()
        offlineStarted = !locked
        mode = .offlineKiosk(token, locked: locked)
        screen += 1
        if !locked {
            prefs.set(token, forKey: Key.runningOffline)
            prefs.set(token, forKey: Key.activeKiosk)
            startPinning()
        }
    }

    func showResults(_ token: String) {
        stopDiscovery()
        mode = .results(token)
        screen += 1
    }

    /// Messages of the pages (offline bridge and the kiosk page from the computer).
    func handle(_ message: [String: Any]) {
        let token = message["token"] as? String ?? ""
        switch message["op"] as? String {
        case "kioskReady":
            if let key = message["key"] as? String, !token.isEmpty { kioskReady(token: token, kioskKey: key) }
        case "vote":
            store.addVote(token: token, value: message["value"] as? String ?? "", lang: message["lang"] as? String ?? "")
        case "kioskStarted":
            prefs.set(token, forKey: Key.runningOffline)
            prefs.set(token, forKey: Key.activeKiosk)
            offlineStarted = true
            startPinning()
        case "exitKiosk":
            for k in [Key.runningOffline, Key.activeKiosk, Key.lastKiosk] { prefs.removeObject(forKey: k) }
            showSetup()
        case "close":
            showSetup()
        default:
            break
        }
    }

    /// Back to the overview from a screen that is not a running kiosk.
    func leave() {
        switch mode {
        case .offlineKiosk:
            if !offlineStarted { showSetup() }
        case .web:
            if canLeaveWeb { showSetup() }
        case .connecting:
            cancelConnecting()
        default:
            showSetup()
        }
    }

    var offlineCanLeave: Bool {
        if case .offlineKiosk(_, let locked) = mode { return locked && !offlineStarted }
        return false
    }

    // MARK: locking (Guided Access)

    /// Supervised devices that allow Tapinion single app mode lock themselves; elsewhere the
    /// request is refused and Guided Access is started by hand (side button three times).
    private func startPinning() {
        if pinned { return }
        pinned = true
        UIAccessibility.requestGuidedAccessSession(enabled: true) { _ in }
    }

    private func stopPinning() {
        if !pinned || activeKiosk != nil { return }  // a running kiosk stays locked
        pinned = false
        if UIAccessibility.isGuidedAccessEnabled {
            UIAccessibility.requestGuidedAccessSession(enabled: false) { _ in }
        }
    }

    private func showToast(_ text: String) {
        toast = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
            if self?.toast == text { self?.toast = nil }
        }
    }

    // MARK: helpers

    static func originOf(_ url: String) -> String {
        guard let u = URLComponents(string: url), let scheme = u.scheme, let host = u.host else { return url }
        return "\(scheme)://\(host)" + (u.port.map { ":\($0)" } ?? "")
    }

    static func tokenOf(_ kioskUrl: String?) -> String? {
        guard let kioskUrl, let path = URLComponents(string: kioskUrl)?.path else { return nil }
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        return parts.count == 3 && parts[1] == "k" && !parts[2].isEmpty ? String(parts[2]) : nil
    }

    static func isKioskPage(_ page: String?) -> Bool { tokenOf(page) != nil }
}
