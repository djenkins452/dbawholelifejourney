// SettingsView.swift
// Whole Life Journey iOS App
//
// Native settings screen - REQUIRED for App Store approval.
// This provides native functionality beyond the WebView.

import SwiftUI
import WebKit

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    @State private var isSyncing = false
    @State private var isConnecting = false
    @State private var showSyncError = false
    @State private var showConnectError = false
    @State private var showSyncSuccess = false
    @State private var syncError: String = ""
    @State private var connectError: String = ""

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
                    Text("Sync your Apple Health data to Whole Life Journey for tracking steps, weight, sleep, heart rate, blood glucose, blood oxygen, and water intake.")
                }

                // MARK: - Account Section
                Section {
                    if appState.isAuthenticated {
                        HStack {
                            Text("Status")
                            Spacer()
                            Text("Connected")
                                .foregroundColor(.green)
                        }

                        Button(role: .destructive) {
                            appState.logout()
                            dismiss()
                        } label: {
                            HStack {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                                Text("Disconnect Account")
                            }
                        }
                    } else {
                        HStack {
                            Text("Status")
                            Spacer()
                            Text("Not Connected")
                                .foregroundColor(.secondary)
                        }

                        Button(action: connectAccount) {
                            HStack {
                                if isConnecting {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "link")
                                }
                                Text(isConnecting ? "Connecting..." : "Connect Account")
                            }
                        }
                        .disabled(isConnecting)

                        Text("Connect your account to enable health data sync. Make sure you're logged in via the web first.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } header: {
                    Text("Account")
                } footer: {
                    if !appState.isAuthenticated {
                        Text("This links your web login to the native app for health sync.")
                    }
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
            .alert("Connection Error", isPresented: $showConnectError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(connectError)
            }
            .alert("Sync Complete", isPresented: $showSyncSuccess) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("Your health data has been synced successfully.")
            }
        }
    }

    private func connectAccount() {
        isConnecting = true

        Task {
            do {
                // Request exchange code from server (uses web session cookies)
                let code = try await requestExchangeCode()

                // Exchange code for API token
                let response = try await APIClient.shared.exchangeToken(code: code)

                await MainActor.run {
                    appState.isAuthenticated = true
                    isConnecting = false
                }
            } catch {
                await MainActor.run {
                    connectError = error.localizedDescription
                    showConnectError = true
                    isConnecting = false
                }
            }
        }
    }

    private func requestExchangeCode() async throws -> String {
        // Get cookies from WKWebView's data store
        let dataStore = WKWebsiteDataStore.default()
        let cookies = await dataStore.httpCookieStore.allCookies()

        // Build cookie header
        let wljCookies = cookies.filter { $0.domain.contains("wholelifejourney.com") }
        let cookieHeader = wljCookies.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")

        // Make request with cookies
        let url = URL(string: "https://wholelifejourney.com/api/mobile/generate-code/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(cookieHeader, forHTTPHeaderField: "Cookie")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw NSError(domain: "SettingsView", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
        }

        if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
            throw NSError(domain: "SettingsView", code: 401, userInfo: [NSLocalizedDescriptionKey: "Please log in via the web first, then try again."])
        }

        if httpResponse.statusCode != 200 {
            throw NSError(domain: "SettingsView", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: "Server error: \(httpResponse.statusCode)"])
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let code = json["code"] as? String else {
            throw NSError(domain: "SettingsView", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response from server"])
        }

        return code
    }

    private func syncNow() {
        isSyncing = true

        Task {
            do {
                try await HealthKitManager.shared.syncHealthData()

                // Fetch the server's sync timestamp instead of using local Date()
                // If this fails, fall back to current time (sync still succeeded)
                var serverSyncDate: Date? = nil
                do {
                    let syncStatus = try await APIClient.shared.getSyncStatus()
                    serverSyncDate = parseISO8601Date(syncStatus.lastSync)
                } catch {
                    print("Failed to fetch sync status: \(error)")
                    // Don't fail the whole sync - just use current time
                }

                await MainActor.run {
                    appState.lastSyncDate = serverSyncDate ?? Date()
                    isSyncing = false
                    showSyncSuccess = true
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

    private func parseISO8601Date(_ dateString: String?) -> Date? {
        guard let dateString = dateString else { return nil }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dateString) {
            return date
        }

        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: dateString)
    }
}

#Preview {
    SettingsView()
        .environmentObject(AppState())
}
