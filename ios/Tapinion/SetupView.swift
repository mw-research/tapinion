// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import SwiftUI

/// Start screen: Tapinion in the Wi-Fi, QR code, address by hand, offline events, locking.
struct SetupView: View {
    @ObservedObject var model: AppModel
    @State private var address = ""
    @State private var manual = false
    @State private var scanning = false
    @State private var lockHelp = false
    @State private var toDelete: OfflineStore.Entry?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    if let logo = UIImage(named: "logo_mark") {
                        Image(uiImage: logo).resizable().scaledToFit().frame(width: 44, height: 44)
                    }
                    Text("Tapinion").font(.largeTitle.bold())
                }
                Text(L("setup_intro")).foregroundColor(.secondary)

                if let error = model.error {
                    Text(error).foregroundColor(.bad).accessibilityIdentifier("error")
                }

                Button {
                    scanning = true
                } label: {
                    Label(L("setup_scan"), systemImage: "qrcode.viewfinder").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(.brand).controlSize(.large)

                section(L("found_title"))
                if model.found.isEmpty {
                    HStack(spacing: 10) {
                        ProgressView()
                        Text(L("searching")).foregroundColor(.secondary)
                    }
                } else {
                    ForEach(model.found, id: \.url) { f in
                        Button { model.connect(f.url) } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(L("found_on", f.name.hasPrefix("Tapinion ") ? String(f.name.dropFirst(9)) : f.name))
                                        .font(.headline)
                                    Text(f.url.replacingOccurrences(of: "http://", with: ""))
                                        .font(.subheadline).foregroundColor(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").foregroundColor(.secondary)
                            }
                            .padding(14)
                            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                    }
                }

                Button(L("setup_manual")) { manual.toggle() }.tint(.brand).accessibilityIdentifier("manual")
                if manual {
                    HStack {
                        TextField(L("setup_address_hint"), text: $address)
                            .textFieldStyle(.roundedBorder)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .submitLabel(.go)
                            .onSubmit { model.connect(address) }
                            .accessibilityIdentifier("address")
                        Button(L("setup_connect")) { model.connect(address) }
                            .buttonStyle(.borderedProminent).tint(.brand)
                            .accessibilityIdentifier("connect")
                    }
                }

                if !model.entries.isEmpty {
                    HStack {
                        section(L("offline_title"))
                        Spacer()
                        Button(L("offline_sync")) { model.runSync(showStatus: true) }.tint(.brand)
                            .accessibilityIdentifier("sync")
                    }
                    if let s = model.syncStatus {
                        Text(s).font(.subheadline).foregroundColor(.secondary).accessibilityIdentifier("syncStatus")
                    }
                    ForEach(model.entries) { e in offlineCard(e) }
                }

                section(L("lock_how_title").uppercased())
                Text(model.guidedAccess ? L("lock_on") : L("lock_off"))
                    .font(.subheadline).foregroundColor(.secondary)
                Button(L("lock_how")) { lockHelp = true }.tint(.brand)

                Text(L("setup_about")).font(.footnote).foregroundColor(.secondary).padding(.top, 12)
            }
            .padding(20)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
        .onAppear { address = model.currentAddress }
        .sheet(isPresented: $scanning) {
            QRScanner { code in
                scanning = false
                model.connect(code)
            }
            .ignoresSafeArea()
        }
        .alert(L("lock_how_title"), isPresented: $lockHelp) {
            Button(L("ok"), role: .cancel) {}
        } message: {
            Text(L("lock_how_text"))
        }
        .alert(toDelete.map { L("offline_delete_question", $0.name) } ?? "",
               isPresented: Binding(get: { toDelete != nil }, set: { if !$0 { toDelete = nil } })) {
            Button(L("offline_delete"), role: .destructive) {
                if let e = toDelete { model.delete(e) }
            }
            Button(L("cancel"), role: .cancel) {}
        } message: {
            if let e = toDelete, e.pending > 0 { Text(L("offline_delete_pending", e.pending)) }
        }
    }

    private func section(_ title: String) -> some View {
        Text(title).font(.caption.weight(.semibold)).foregroundColor(.secondary).padding(.top, 6)
    }

    private func status(_ e: OfflineStore.Entry) -> String {
        if e.switchedOff { return L("offline_status_off", e.date) }
        if e.pending > 0 { return L("offline_status_pending", e.date, e.pending) }
        if !e.active { return L("offline_status_closed", e.date) }
        return L("offline_status_synced", e.date)
    }

    private func offlineCard(_ e: OfflineStore.Entry) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(e.name).font(.headline)
            Text(status(e)).font(.subheadline).foregroundColor(.secondary).accessibilityIdentifier("status-\(e.token)")
            HStack(spacing: 16) {
                Button(L("offline_start")) { model.showOfflineKiosk(e.token, locked: true) }
                    .buttonStyle(.borderedProminent).tint(.brand).disabled(e.switchedOff)
                Button(L("offline_results")) { model.showResults(e.token) }.tint(.brand)
                Spacer()
                Button(L("offline_delete")) { toDelete = e }.tint(.bad)
            }
        }
        .padding(14)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
    }
}

/// Short check whether the computer answers; can be cancelled at any time.
struct ConnectingView: View {
    @ObservedObject var model: AppModel
    let address: String

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            ProgressView().controlSize(.large)
            Text(L("connecting_title")).font(.title3.weight(.semibold))
            Text(address).foregroundColor(.secondary)
            Button(model.guardedToken != nil ? L("connecting_continue_offline") : L("connecting_cancel")) {
                model.cancelConnecting()
            }
            .tint(.brand)
            .padding(.top, 12)
            .accessibilityIdentifier("cancelConnecting")
            Spacer()
        }
        .padding(24)
        .frame(maxWidth: .infinity)
    }
}
