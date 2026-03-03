// PushNotificationManager.swift
// Whole Life Journey iOS App
//
// Manages APNs push notification registration, permission requests,
// and deep-link handling for intelligence notifications.
//
// Push flow:
// 1. User taps "Enable Push Notifications" in SettingsView
// 2. PushNotificationManager requests UNUserNotificationCenter permission
// 3. On grant, UIApplication registers for remote notifications
// 4. AppDelegate receives device token, passes to PushNotificationManager
// 5. PushNotificationManager sends token to backend via APIClient
// 6. On notification tap, action_url is extracted and posted for deep-linking

import Foundation
import UserNotifications
import UIKit

class PushNotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = PushNotificationManager()

    /// Whether the user has been asked for push permission this session
    private var hasRequestedPermission = false

    private override init() {
        super.init()
    }

    // MARK: - Permission & Registration

    /// Request push notification permission from the user.
    /// If granted, registers for remote notifications to obtain APNs token.
    func requestPermission() {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .badge, .sound]
        ) { granted, error in
            self.hasRequestedPermission = true

            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
                print("Push permission granted")
            } else {
                print("Push permission denied")
            }

            if let error = error {
                print("Push permission error: \(error.localizedDescription)")
            }
        }
    }

    /// Called by AppDelegate when APNs device token is received.
    /// Sends the token to the WLJ backend for push delivery.
    func didRegisterForRemoteNotifications(deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("APNs token received: \(token.prefix(8))...")

        Task {
            do {
                try await APIClient.shared.registerPushToken(token)
                print("Push token registered with backend")
            } catch {
                print("Failed to register push token: \(error.localizedDescription)")
            }
        }
    }

    /// Called by AppDelegate when APNs registration fails.
    func didFailToRegisterForRemoteNotifications(error: Error) {
        print("Push registration failed: \(error.localizedDescription)")
    }

    /// Unregister push on logout — clears token on backend and unregisters locally.
    func unregisterPush() {
        UIApplication.shared.unregisterForRemoteNotifications()

        Task {
            do {
                try await APIClient.shared.unregisterPushToken()
                print("Push token unregistered from backend")
            } catch {
                // Non-critical — token will be invalid on server anyway after logout
                print("Failed to unregister push token: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Handle notification tap — extract action_url for deep linking.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        if let actionURL = userInfo["action_url"] as? String {
            // Post notification for MainWebView to navigate to the deep-link URL
            NotificationCenter.default.post(
                name: .pushNotificationDeepLink,
                object: nil,
                userInfo: ["action_url": actionURL]
            )
        }

        completionHandler()
    }

    /// Show notification banner when app is in foreground.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Show banner, play sound, and update badge even when in foreground
        completionHandler([.banner, .sound, .badge])
    }
}

// MARK: - Notification Name Extension

extension Notification.Name {
    /// Posted when user taps a push notification with an action_url.
    /// UserInfo contains ["action_url": String] for deep-link navigation.
    static let pushNotificationDeepLink = Notification.Name("pushNotificationDeepLink")

    /// Posted when a contact is successfully imported from the native contact picker.
    /// The WebView should reload the relationships page.
    static let contactImported = Notification.Name("contactImported")
}
