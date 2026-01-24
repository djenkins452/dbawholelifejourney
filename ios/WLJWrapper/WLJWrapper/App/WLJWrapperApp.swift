// WLJWrapperApp.swift
// Whole Life Journey iOS App
//
// Main app entry point using SwiftUI App lifecycle.
// Configures the app and sets up the initial view hierarchy.

import SwiftUI

@main
struct WLJWrapperApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
    }
}

// MARK: - App State
/// Global app state shared across views
class AppState: ObservableObject {
    @Published var isAuthenticated: Bool = false
    @Published var showSettings: Bool = false
    @Published var lastSyncDate: Date?
    @Published var healthKitAuthorized: Bool = false

    init() {
        // Check if we have a stored token
        isAuthenticated = KeychainManager.shared.getAPIToken() != nil

        // Check HealthKit authorization status
        healthKitAuthorized = HealthKitManager.shared.isAuthorized
    }

    func logout() {
        KeychainManager.shared.deleteAPIToken()
        KeychainManager.shared.deleteUserInfo()
        isAuthenticated = false
    }
}
