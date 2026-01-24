// KeychainManager.swift
// Whole Life Journey iOS App
//
// Secure storage for API tokens and device ID using iOS Keychain.
// Never stores sensitive data in UserDefaults.

import Foundation
import Security

class KeychainManager {
    static let shared = KeychainManager()

    private let service = "com.wholelifejourney.app"

    private enum Key: String {
        case apiToken = "api_token"
        case deviceId = "device_id"
        case userEmail = "user_email"
        case userId = "user_id"
    }

    private init() {}

    // MARK: - API Token

    func saveAPIToken(_ token: String) {
        save(key: .apiToken, value: token)
    }

    func getAPIToken() -> String? {
        return get(key: .apiToken)
    }

    func deleteAPIToken() {
        delete(key: .apiToken)
    }

    // MARK: - Device ID

    /// Get or create a unique device ID stored in Keychain.
    /// This persists across app reinstalls (as long as Keychain is preserved).
    func getOrCreateDeviceId() -> String {
        if let existing = get(key: .deviceId) {
            return existing
        }

        // Generate new UUID
        let newId = UUID().uuidString
        save(key: .deviceId, value: newId)
        return newId
    }

    // MARK: - User Info

    func saveUserInfo(userId: Int, email: String) {
        save(key: .userId, value: String(userId))
        save(key: .userEmail, value: email)
    }

    func getUserEmail() -> String? {
        return get(key: .userEmail)
    }

    func getUserId() -> Int? {
        guard let str = get(key: .userId) else { return nil }
        return Int(str)
    }

    func deleteUserInfo() {
        delete(key: .userId)
        delete(key: .userEmail)
    }

    // MARK: - Generic Keychain Operations

    private func save(key: Key, value: String) {
        guard let data = value.data(using: .utf8) else { return }

        // Delete any existing item first
        delete(key: key)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            print("Keychain save error for \(key.rawValue): \(status)")
        }
    }

    private func get(key: Key) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else {
            return nil
        }

        return value
    }

    private func delete(key: Key) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue
        ]

        SecItemDelete(query as CFDictionary)
    }
}
