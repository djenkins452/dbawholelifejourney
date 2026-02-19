// APIClient.swift
// Whole Life Journey iOS App
//
// HTTP client for communicating with WLJ Django backend.
// Handles authentication, health data submission, and error handling.

import Foundation
import UIKit

class APIClient {
    static let shared = APIClient()

    private let baseURL = "https://wholelifejourney.com"
    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120  // 2 minutes for large health data syncs
        config.timeoutIntervalForResource = 300  // 5 minutes total
        session = URLSession(configuration: config)
    }

    // MARK: - Token Exchange

    /// Exchange a one-time code for an API token.
    func exchangeToken(code: String) async throws -> TokenExchangeResponse {
        let url = URL(string: "\(baseURL)/api/mobile/token/exchange/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let deviceId = KeychainManager.shared.getOrCreateDeviceId()
        let deviceName = await UIDevice.current.name
        let deviceModel = await UIDevice.current.model
        let osVersion = await UIDevice.current.systemVersion
        let body = TokenExchangeRequest(
            code: code,
            deviceId: deviceId,
            deviceName: deviceName,
            deviceModel: deviceModel,
            osVersion: "iOS \(osVersion)",
            appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
        )

        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        if httpResponse.statusCode == 200 {
            let result = try JSONDecoder().decode(TokenExchangeResponse.self, from: data)

            // Save token and user info to Keychain
            KeychainManager.shared.saveAPIToken(result.token)
            KeychainManager.shared.saveUserInfo(userId: result.user.id, email: result.user.email)

            return result
        } else {
            let error = try? JSONDecoder().decode(APIErrorResponse.self, from: data)
            throw APIError.serverError(error?.message ?? "Token exchange failed")
        }
    }

    // MARK: - Health Data Ingestion

    /// Submit health metrics to the server.
    func submitHealthMetrics(_ metrics: [HealthMetric]) async throws -> IngestionResponse {
        guard let token = KeychainManager.shared.getAPIToken() else {
            throw APIError.notAuthenticated
        }

        let url = URL(string: "\(baseURL)/api/mobile/health/ingest/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let body = HealthIngestionRequest(
            clientTimestamp: ISO8601DateFormatter().string(from: Date()),
            metrics: metrics
        )

        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200:
            return try JSONDecoder().decode(IngestionResponse.self, from: data)
        case 401:
            // Token expired or revoked
            KeychainManager.shared.deleteAPIToken()
            throw APIError.notAuthenticated
        case 413:
            throw APIError.payloadTooLarge
        default:
            let error = try? JSONDecoder().decode(APIErrorResponse.self, from: data)
            let body = String(data: data, encoding: .utf8) ?? "(no body)"
            let detail = error?.message ?? "HTTP \(httpResponse.statusCode): \(body.prefix(500))"
            throw APIError.serverError(detail)
        }
    }

    // MARK: - Sync Status

    /// Get the current sync status.
    func getSyncStatus() async throws -> SyncStatusResponse {
        guard let token = KeychainManager.shared.getAPIToken() else {
            throw APIError.notAuthenticated
        }

        let url = URL(string: "\(baseURL)/api/mobile/health/sync-status/")!
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        if httpResponse.statusCode == 200 {
            return try JSONDecoder().decode(SyncStatusResponse.self, from: data)
        } else if httpResponse.statusCode == 401 {
            KeychainManager.shared.deleteAPIToken()
            throw APIError.notAuthenticated
        } else {
            let body = String(data: data, encoding: .utf8) ?? "(no body)"
            throw APIError.serverError("Sync status failed (\(httpResponse.statusCode)): \(body)")
        }
    }

    // MARK: - Push Notifications

    /// Register APNs push token with the backend.
    func registerPushToken(_ token: String) async throws {
        guard let apiToken = KeychainManager.shared.getAPIToken() else {
            throw APIError.notAuthenticated
        }

        let url = URL(string: "\(baseURL)/api/mobile/push/register/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")

        let body = ["push_token": token]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        if httpResponse.statusCode == 401 {
            KeychainManager.shared.deleteAPIToken()
            throw APIError.notAuthenticated
        }

        guard httpResponse.statusCode == 200 else {
            throw APIError.serverError("Push registration failed (\(httpResponse.statusCode))")
        }
    }

    /// Unregister push token from the backend (on logout/disable).
    func unregisterPushToken() async throws {
        guard let apiToken = KeychainManager.shared.getAPIToken() else {
            return // Already logged out, nothing to unregister
        }

        let url = URL(string: "\(baseURL)/api/mobile/push/unregister/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")

        // Best-effort — don't throw on failure
        let (_, _) = try await session.data(for: request)
    }

    // MARK: - Token Revocation

    /// Revoke the current API token (logout).
    func revokeToken() async throws {
        guard let token = KeychainManager.shared.getAPIToken() else {
            return // Already logged out
        }

        let url = URL(string: "\(baseURL)/api/mobile/token/revoke/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (_, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            // Still delete local token even if server request fails
            KeychainManager.shared.deleteAPIToken()
            return
        }

        KeychainManager.shared.deleteAPIToken()
    }
}

// MARK: - Request/Response Types

struct TokenExchangeRequest: Codable {
    let code: String
    let deviceId: String
    let deviceName: String
    let deviceModel: String
    let osVersion: String
    let appVersion: String

    enum CodingKeys: String, CodingKey {
        case code
        case deviceId = "device_id"
        case deviceName = "device_name"
        case deviceModel = "device_model"
        case osVersion = "os_version"
        case appVersion = "app_version"
    }
}

struct TokenExchangeResponse: Codable {
    let token: String
    let expiresAt: String
    let user: UserInfo

    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
        case user
    }
}

struct UserInfo: Codable {
    let id: Int
    let email: String
    let firstName: String?
    let lastName: String?

    enum CodingKeys: String, CodingKey {
        case id
        case email
        case firstName = "first_name"
        case lastName = "last_name"
    }
}

struct HealthIngestionRequest: Codable {
    let clientTimestamp: String
    let metrics: [HealthMetric]

    enum CodingKeys: String, CodingKey {
        case clientTimestamp = "client_timestamp"
        case metrics
    }
}

struct IngestionResponse: Codable {
    let success: Bool
    let ingestionId: Int
    let created: Int
    let updated: Int
    let skipped: Int
    let errors: [IngestionError]

    enum CodingKeys: String, CodingKey {
        case success
        case ingestionId = "ingestion_id"
        case created
        case updated
        case skipped
        case errors
    }
}

struct IngestionError: Codable {
    let index: Int
    let type: String
    let error: String
}

struct SyncStatusResponse: Codable {
    let lastSync: String?
    let lastSyncStatus: String?
    let metricsSynced: MetricsSynced
    let device: DeviceInfo

    enum CodingKeys: String, CodingKey {
        case lastSync = "last_sync"
        case lastSyncStatus = "last_sync_status"
        case metricsSynced = "metrics_synced"
        case device
    }
}

struct MetricsSynced: Codable {
    let steps: String?
    let weight: String?
    let sleep: String?
}

struct DeviceInfo: Codable {
    let name: String
    let lastSeen: String?

    enum CodingKeys: String, CodingKey {
        case name
        case lastSeen = "last_seen"
    }
}

struct APIErrorResponse: Codable {
    let error: String
    let message: String
}

// MARK: - API Errors

enum APIError: LocalizedError {
    case notAuthenticated
    case invalidResponse
    case payloadTooLarge
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "Please log in to sync health data."
        case .invalidResponse:
            return "Invalid response from server."
        case .payloadTooLarge:
            return "Too much data to sync at once. Try syncing less data."
        case .serverError(let message):
            return message
        }
    }
}
