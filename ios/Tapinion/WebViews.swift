// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import SwiftUI
import WebKit

/// Forwards page messages without the content controller keeping the model alive.
private final class MessageProxy: NSObject, WKScriptMessageHandler {
    weak var model: AppModel?

    init(_ model: AppModel) { self.model = model }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any] else { return }
        Task { @MainActor in self.model?.handle(body) }
    }
}

@MainActor
private func makeWebView(_ model: AppModel, scripts: [String]) -> WKWebView {
    let config = WKWebViewConfiguration()
    config.websiteDataStore = .default()  // vote queue and device key of the web kiosk
    config.allowsInlineMediaPlayback = true
    config.applicationNameForUserAgent = "Mobile/15E148 TapinionKiosk/1.2"
    let content = WKUserContentController()
    for s in scripts {
        content.addUserScript(WKUserScript(source: s, injectionTime: .atDocumentStart, forMainFrameOnly: true))
    }
    content.add(MessageProxy(model), name: "tapinion")
    config.userContentController = content
    let web = WKWebView(frame: .zero, configuration: config)
    web.allowsBackForwardNavigationGestures = false  // a running kiosk is left with the PIN only
    web.allowsLinkPreview = false
    web.scrollView.bounces = false
    web.scrollView.contentInsetAdjustmentBehavior = .never
    web.isOpaque = false
    web.backgroundColor = .systemBackground
    if #available(iOS 16.4, *) { web.isInspectable = true }
    model.webView = web
    return web
}

/// Tapinion on the computer: its kiosk (and, after the PIN, its other pages).
struct RemoteWebView: UIViewRepresentable {
    let url: String
    let model: AppModel

    /// The kiosk page hands over a kiosk for offline use (kiosk.js calls TapinionApp.kioskReady).
    private static let bridge = """
    window.TapinionApp = { kioskReady: function (token, key) {
      try { window.webkit.messageHandlers.tapinion.postMessage({ op: "kioskReady", token: token, key: key }); } catch (e) {}
    } };
    """

    func makeCoordinator() -> Coordinator { Coordinator(model) }

    func makeUIView(context: Context) -> WKWebView {
        let web = makeWebView(model, scripts: [Self.bridge])
        web.navigationDelegate = context.coordinator
        if let u = URL(string: url) { web.load(URLRequest(url: u)) }
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        let model: AppModel

        init(_ model: AppModel) { self.model = model }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let target = action.request.url, let scheme = target.scheme, scheme.hasPrefix("http") else {
                decisionHandler(.allow)
                return
            }
            Task { @MainActor in
                if model.isSameOrigin(target) || action.targetFrame?.isMainFrame == false {
                    decisionHandler(.allow)
                } else {
                    if !model.locked { await UIApplication.shared.open(target) }
                    decisionHandler(.cancel)
                }
            }
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            let u = webView.url?.absoluteString
            Task { @MainActor in model.pageStarted(u) }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            let u = webView.url?.absoluteString
            Task { @MainActor in model.pageDidFinish(u) }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            failed(webView, error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            failed(webView, error)
        }

        private func failed(_ webView: WKWebView, _ error: Error) {
            let e = error as NSError
            if e.domain == NSURLErrorDomain && e.code == NSURLErrorCancelled { return }  // replaced by another load
            if e.domain == "WebKitErrorDomain" && e.code == 102 { return }               // a download, not a page
            let u = (e.userInfo[NSURLErrorFailingURLStringErrorKey] as? String) ?? webView.url?.absoluteString
            Task { @MainActor in model.unreachable(u) }
        }
    }
}

/// The app's own offline pages (kiosk.html, results.html; shared with the Android app).
struct OfflineWebView: UIViewRepresentable {
    let page: String     // "kiosk" or "results"
    let token: String
    let locked: Bool
    let model: AppModel

    func makeUIView(context: Context) -> WKWebView {
        let data = OfflineStore.json(["bundle": model.store.bundle(token)])
        let votes = model.store.votesJson(token)
        let inject = "window.__tapinionData = \(data); window.__tapinionData.votes = \(votes);"
        let bridge = Bundle.main.url(forResource: "bridge", withExtension: "js")
            .flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? ""
        let web = makeWebView(model, scripts: [inject, bridge])
        web.navigationDelegate = context.coordinator
        if let dir = Bundle.main.url(forResource: "offline", withExtension: nil) {
            let file = dir.appendingPathComponent("\(page).html")
            let encoded = token.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? token
            let target = URL(string: file.absoluteString + "#" + encoded + (locked ? "&unlock=1" : "")) ?? file
            web.loadFileURL(target, allowingReadAccessTo: dir)
        }
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate {
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // the offline pages never navigate away
            decisionHandler(action.request.url?.isFileURL == true ? .allow : .cancel)
        }
    }
}
