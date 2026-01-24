// SettingsView.swift
// Whole Life Journey iOS App
//
// Native settings screen - REQUIRED for App Store approval.
// This provides native functionality beyond the WebView.

import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    @State private var isSyncing = false
    @State private var showSyncError = false
    @State private var syncError: String = ""

    var body: some View {
        NavigationStack {
            List {
                // MARK: - Health Sync Section
                Section {
                    NavigationLink(destination: HealthSyncView()) {
                        HStack {
                            Image(systemName: "heart.fill")
                                .foregroundColor(.red)
                            Text("Health Data Sync")
                        }
                    }

                    HStack {
                        Text("HealthKit Status")
                        Spacer()
                        Text(appState.healthKitAuthorized ? "Authorized" : "Not Authorized")
                            .foregroundColor(appState.healthKitAuthorized ? .green : .secondary)
                    }

                    if let lastSync = appState.lastSyncDate {
                        HStack {
                            Text("Last Sync")
                            Spacer()
                            Text(lastSync, style: .relative)
                                .foregroundColor(.secondary)
                        }
                    }

                    Button(action: syncNow) {
                        HStack {
                            if isSyncing {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.triangle.2.circlepath")
                            }
                            Text(isSyncing ? "Syncing..." : "Sync Now")
                        }
                    }
                    .disabled(isSyncing || !appState.healthKitAuthorized)
                } header: {
                    Text("Health")
                } footer: {
                    Text("Sync your Apple Health data to Whole Life Journey for tracking steps, weight, sleep, and heart rate.")
                }

                // MARK: - Account Section
                Section {
                    if appState.isAuthenticated {
                        HStack {
                            Text("Status")
                            Spacer()
                            Text("Logged In")
                                .foregroundColor(.green)
                        }

                        Button(role: .destructive) {
                            appState.logout()
                            dismiss()
                        } label: {
                            HStack {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                                Text("Log Out")
                            }
                        }
                    } else {
                        HStack {
                            Text("Status")
                            Spacer()
                            Text("Not Logged In")
                                .foregroundColor(.secondary)
                        }

                        Text("Log in via the web to enable health sync.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } header: {
                    Text("Account")
                }

                // MARK: - About Section
                Section {
                    HStack {
                        Text("App Version")
                        Spacer()
                        Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Build")
                        Spacer()
                        Text(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1")
                            .foregroundColor(.secondary)
                    }

                    Link(destination: URL(string: "https://wholelifejourney.com/terms/")!) {
                        HStack {
                            Text("Terms of Service")
                            Spacer()
                            Image(systemName: "arrow.up.right.square")
                                .foregroundColor(.secondary)
                        }
                    }

                    Link(destination: URL(string: "https://wholelifejourney.com/privacy/")!) {
                        HStack {
                            Text("Privacy Policy")
                            Spacer()
                            Image(systemName: "arrow.up.right.square")
                                .foregroundColor(.secondary)
                        }
                    }
                } header: {
                    Text("About")
                }

                // MARK: - Support Section
                Section {
                    Link(destination: URL(string: "mailto:support@wholelifejourney.com")!) {
                        HStack {
                            Image(systemName: "envelope")
                            Text("Contact Support")
                        }
                    }
                } header: {
                    Text("Support")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .alert("Sync Error", isPresented: $showSyncError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(syncError)
            }
        }
    }

    private func syncNow() {
        isSyncing = true

        Task {
            do {
                try await HealthKitManager.shared.syncHealthData()
                await MainActor.run {
                    appState.lastSyncDate = Date()
                    isSyncing = false
                }
            } catch {
                await MainActor.run {
                    syncError = error.localizedDescription
                    showSyncError = true
                    isSyncing = false
                }
            }
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(AppState())
}
