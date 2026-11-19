// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import SwiftUI

extension Color {
    static let brand = Color(red: 0x0E / 255, green: 0x74 / 255, blue: 0x90 / 255)
    static let bad = Color(red: 0xD6 / 255, green: 0x45 / 255, blue: 0x45 / 255)
}

@main
struct TapinionApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .onChange(of: phase) { p in
                    if p == .active { model.becameActive() } else { model.becameInactive() }
                }
        }
    }
}

struct RootView: View {
    @ObservedObject var model: AppModel

    private var kioskScreen: Bool {
        switch model.mode {
        case .web, .offlineKiosk: return true
        default: return false
        }
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            switch model.mode {
            case .setup:
                SetupView(model: model)
            case .connecting(let address):
                ConnectingView(model: model, address: address)
            case .web(let url):
                RemoteWebView(url: url, model: model)
                    .ignoresSafeArea()
                    .overlay(alignment: .bottomLeading) {
                        if model.canLeaveWeb {
                            Button(L("overview")) { model.leave() }
                                .font(.footnote.weight(.semibold))
                                .padding(.horizontal, 14).padding(.vertical, 8)
                                .background(.ultraThinMaterial, in: Capsule())
                                .padding(12)
                                .accessibilityIdentifier("overview")
                        }
                    }
            case .offlineKiosk(let token, let locked):
                OfflineWebView(page: "kiosk", token: token, locked: locked, model: model)
                    .ignoresSafeArea()
                    .overlay(alignment: .bottomLeading) {
                        if model.offlineCanLeave {
                            Button(L("overview")) { model.leave() }
                                .font(.footnote.weight(.semibold))
                                .padding(.horizontal, 14).padding(.vertical, 8)
                                .background(.ultraThinMaterial, in: Capsule())
                                .padding(12)
                                .accessibilityIdentifier("overview")
                        }
                    }
            case .results(let token):
                OfflineWebView(page: "results", token: token, locked: false, model: model)
            }
            if let toast = model.toast {
                Text(toast)
                    .font(.callout)
                    .foregroundColor(.white)
                    .padding(.horizontal, 18).padding(.vertical, 10)
                    .background(Color.black.opacity(0.75), in: Capsule())
                    .padding(.bottom, 40)
                    .transition(.opacity)
            }
        }
        .id(model.screen)
        .statusBarHidden(kioskScreen)
        .persistentSystemOverlays(kioskScreen ? .hidden : .automatic)
        .animation(.default, value: model.toast)
    }
}
