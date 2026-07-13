// HealthSyncStatus.swift
// Whole Life Journey iOS App
//
// Decodes the deterministic Health Sync truth returned by
// GET /api/mobile/health/sync-status/ (key "sync_health"). Built server-side by
// apps.health.services.health_sync_status.build_health_sync_status — every value
// here reflects what the backend actually received/persisted, never a guess.

import Foundation

struct HealthSyncStatus: Codable {
    let generatedAt: String?
    let lastSync: LastSyncInfo?
    let activeTypesCount: Int
    let totalTypesCount: Int
    let newestData: TypeRef?
    let oldestActiveSource: TypeRef?
    let issues: [SyncIssue]
    let dataTypes: [DataTypeHealth]
    let lastSyncSummary: SyncSummary?
    let diagnostics: SyncDiagnostics?

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at"
        case lastSync = "last_sync"
        case activeTypesCount = "active_types_count"
        case totalTypesCount = "total_types_count"
        case newestData = "newest_data"
        case oldestActiveSource = "oldest_active_source"
        case issues
        case dataTypes = "data_types"
        case lastSyncSummary = "last_sync_summary"
        case diagnostics
    }
}

// MARK: - Temporary glass-box diagnostics (locate where a metric disappears)

struct SyncDiagnostics: Codable {
    let steps: StepsDiagnostics?
}

struct StepsDiagnostics: Codable {
    let stage: String
    let verdict: String
    let clientReported: [String: Int]?   // raw_samples, built, sent
    let serverReceived: [String: Int]    // created, updated, skipped, failed
    let serverRejectionReasons: [String]
    let persistedTotal: Int
    let latestPersistedDate: String?
    let recentRunCount: Int

    enum CodingKeys: String, CodingKey {
        case stage, verdict
        case clientReported = "client_reported"
        case serverReceived = "server_received"
        case serverRejectionReasons = "server_rejection_reasons"
        case persistedTotal = "persisted_total"
        case latestPersistedDate = "latest_persisted_date"
        case recentRunCount = "recent_run_count"
    }
}

struct LastSyncInfo: Codable {
    let at: String?
    let status: String?
    let ingestionId: Int?

    enum CodingKeys: String, CodingKey {
        case at, status
        case ingestionId = "ingestion_id"
    }
}

struct TypeRef: Codable {
    let key: String
    let label: String
    let at: String?
}

struct SyncIssue: Codable, Identifiable {
    var id: String { key }
    let key: String
    let message: String
    let severity: String
}

struct DataTypeHealth: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let status: String            // healthy | stale | idle | no_data
    let lastRecordAt: String?
    let recentCount: Int
    let totalCount: Int
    let staleDays: Int?
    let message: String

    enum CodingKeys: String, CodingKey {
        case key, label, unit, status, message
        case lastRecordAt = "last_record_at"
        case recentCount = "recent_count"
        case totalCount = "total_count"
        case staleDays = "stale_days"
    }

    /// UI grouping: is this source healthy?
    var isHealthy: Bool { status == "healthy" || status == "idle" }
    var needsAttention: Bool { status == "no_data" || status == "stale" }
}

struct SyncSummary: Codable {
    let at: String?
    let status: String?
    let imported: [ImportedType]
    let noChanges: [TypeLabelRef]
    let failed: [FailedType]

    enum CodingKeys: String, CodingKey {
        case at, status, imported, failed
        case noChanges = "no_changes"
    }
}

struct ImportedType: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let count: Int
}

struct TypeLabelRef: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
}

struct FailedType: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let reason: String
}

// MARK: - Display helpers

extension DataTypeHealth {
    /// SF Symbol per source (falls back to a generic heart).
    var iconName: String {
        switch key {
        case "steps": return "figure.walk"
        case "active_calories": return "flame.fill"
        case "distance": return "figure.run"
        case "weight": return "scalemass"
        case "sleep": return "bed.double"
        case "heart_rate": return "heart"
        case "blood_glucose": return "drop.fill"
        case "blood_oxygen": return "lungs.fill"
        case "water": return "drop.triangle.fill"
        case "blood_pressure": return "heart.circle"
        case "body_temperature": return "thermometer"
        case "workout": return "figure.mixed.cardio"
        default: return "heart.text.square"
        }
    }
}

/// Parse the ISO8601 date/datetime strings the backend emits into a friendly,
/// user-local relative string ("Today • 6:54 AM", "Yesterday", "3 days ago").
enum HealthSyncDate {
    private static let isoFull: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoNoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static func parse(_ s: String?) -> Date? {
        guard let s = s, !s.isEmpty else { return nil }
        if let d = isoFull.date(from: s) { return d }
        if let d = isoNoFrac.date(from: s) { return d }
        // Plain "YYYY-MM-DD"
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.timeZone = .current
        return df.date(from: s)
    }

    static func relative(_ s: String?) -> String {
        guard let date = parse(s) else { return "—" }
        let cal = Calendar.current
        if cal.isDateInToday(date) {
            let tf = DateFormatter(); tf.timeStyle = .short; tf.dateStyle = .none
            return "Today • \(tf.string(from: date))"
        }
        if cal.isDateInYesterday(date) { return "Yesterday" }
        let days = cal.dateComponents([.day], from: cal.startOfDay(for: date),
                                      to: cal.startOfDay(for: Date())).day ?? 0
        if days <= 7 { return "\(days) days ago" }
        let df = DateFormatter(); df.dateStyle = .medium; df.timeStyle = .none
        return df.string(from: date)
    }
}
