// WLJWrapperApp.swift
// Whole Life Journey iOS App
//
// Main app entry point using SwiftUI App lifecycle.
// Configures the app and sets up the initial view hierarchy.

import SwiftUI
import Combine

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

    private var cancellables = Set<AnyCancellable>()

    init() {
        // Check if we have a stored token
        isAuthenticated = KeychainManager.shared.getAPIToken() != nil

        // Check HealthKit authorization status
        healthKitAuthorized = HealthKitManager.shared.isAuthorized

        // Load last sync date from server if authenticated
        if isAuthenticated {
            loadSyncStatus()
        }

        // Listen for background sync completions to update lastSyncDate
        NotificationCenter.default.publisher(for: BackgroundSyncManager.syncCompletedNotification)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.loadSyncStatus()
            }
            .store(in: &cancellables)
    }

    /// Fetch the last sync date from the server
    func loadSyncStatus() {
        Task {
            do {
                let syncStatus = try await APIClient.shared.getSyncStatus()
                if let lastSyncString = syncStatus.lastSync,
                   let date = parseISO8601Date(lastSyncString) {
                    await MainActor.run {
                        self.lastSyncDate = date
                    }
                }
            } catch {
                // Silently fail - sync status is not critical on startup
                print("Failed to load sync status: \(error)")
            }
        }
    }

    private func parseISO8601Date(_ dateString: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dateString) {
            return date
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: dateString)
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
