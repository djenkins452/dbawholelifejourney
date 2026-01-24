// WLJWrapperApp.swift
// Whole Life Journey iOS App
//
// Main app entry point using SwiftUI App lifecycle.
// Configures the app and sets up the initial view hierarchy.

import SwiftUI

@main
struct WLJWrapperApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .onChange(of: scenePhase) { oldPhase, newPhase in
            switch newPhase {
            case .active:
                BackgroundSyncManager.shared.applicationDidBecomeActive()
            case .background:
                BackgroundSyncManager.shared.applicationDidEnterBackground()
            default:
                break
            }
        }
    }
}

// MARK: - App Delegate
/// UIKit App Delegate for background task registration
class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Set up background sync
        BackgroundSyncManager.shared.setupBackgroundSync()
        return true
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

        // Disable background sync when logged out
        BackgroundSyncManager.shared.disableBackgroundDelivery()
    }

    func onHealthKitAuthorized() {
        healthKitAuthorized = true
        // Enable background delivery after HealthKit is authorized
        BackgroundSyncManager.shared.enableBackgroundDelivery()
    }
}
