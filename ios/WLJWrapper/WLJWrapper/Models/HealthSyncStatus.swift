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
    let overallHealth: OverallHealth?
    let lastSync: LastSyncInfo?
    let activeTypesCount: Int
    let totalTypesCount: Int
    let newestData: TypeRef?
    let oldestActiveSource: TypeRef?
    let issues: [SyncIssue]
    let dataTypes: [DataTypeHealth]
    let categories: [SyncCategory]?
    let lastSyncSummary: SyncSummary?
    /// The technical truth about synchronization itself — the ONLY authority for
    /// "is sync working?". Never infer that from how old a metric's records are.
    let syncPath: SyncPath?
    /// What the SOURCES produced. Activity, never health — displayed separately.
    let sourceActivitySummary: SourceActivitySummary?

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at"
        case overallHealth = "overall_health"
        case lastSync = "last_sync"
        case activeTypesCount = "active_types_count"
        case totalTypesCount = "total_types_count"
        case newestData = "newest_data"
        case oldestActiveSource = "oldest_active_source"
        case issues
        case dataTypes = "data_types"
        case categories
        case lastSyncSummary = "last_sync_summary"
        case syncPath = "sync_path"
        case sourceActivitySummary = "source_activity_summary"
    }
}

/// Account-level TECHNICAL health of the sync path (from HealthIngestionRun).
/// `status` ∈ ok | never_synced | not_checking_in | failed
struct SyncPath: Codable {
    let status: String
    let lastRunAt: String?
    let lastRunStatus: String?
    let errorMessage: String?

    enum CodingKeys: String, CodingKey {
        case status
        case lastRunAt = "last_run_at"
        case lastRunStatus = "last_run_status"
        case errorMessage = "error_message"
    }

    var isWorking: Bool { status == "ok" }
}

/// How many sources produced records lately. ACTIVITY — not health. Never label this
/// "healthy"/"unhealthy": a source with no new records is not sick, the user just
/// didn't do that thing.
struct SourceActivitySummary: Codable {
    let producedRecently: Int
    let noRecentRecords: Int
    let neverRecorded: Int

    enum CodingKeys: String, CodingKey {
        case producedRecently = "produced_recently"
        case noRecentRecords = "no_recent_records"
        case neverRecorded = "never_recorded"
    }
}

/// Account-level rollup for the hero card. Deterministic status (not a verdict):
/// `status` ∈ healthy | attention | setup; counts give the honest fraction.
struct OverallHealth: Codable {
    let status: String
    let healthyCount: Int
    let activeCount: Int
    let totalCount: Int
    let issueCount: Int
    /// Sources with a VERIFIED technical problem. This — not inactivity — is what
    /// "needs attention" means.
    let attentionCount: Int?

    enum CodingKeys: String, CodingKey {
        case status
        case healthyCount = "healthy_count"
        case activeCount = "active_count"
        case totalCount = "total_count"
        case issueCount = "issue_count"
        case attentionCount = "attention_count"
    }
}

/// One category group (Activity, Heart & Vitals, …) as grouped by the backend.
struct SyncCategory: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let types: [DataTypeHealth]
    let activeCount: Int
    let totalCount: Int
    /// Legacy alias of `attentionCount` (kept for wire compatibility). It counts
    /// VERIFIED technical problems — never inactivity.
    let staleCount: Int
    let attentionCount: Int?

    enum CodingKeys: String, CodingKey {
        case key, label, types
        case activeCount = "active_count"
        case totalCount = "total_count"
        case staleCount = "stale_count"
        case attentionCount = "attention_count"
    }

    /// Sources in this category with no verified technical problem.
    var healthyCount: Int { types.filter { !$0.needsAttention }.count }
    /// Category needs attention only when a source has a VERIFIED import problem.
    var needsAttention: Bool { (attentionCount ?? staleCount) > 0 }
    /// No source in this category has ever produced data.
    var isDormant: Bool { activeCount == 0 }
    /// Sources that produced records recently (activity, not health).
    var producedRecentlyCount: Int { types.filter { $0.sourceActivity == "recent" }.count }
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
    /// The corrective affordance this issue justifies. "open_health_settings" ONLY when
    /// Apple Health sharing is the PROVEN cause — never for ordinary inactivity.
    let action: String?

    var opensHealthSettings: Bool { action == "open_health_settings" }
}

struct DataTypeHealth: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    /// Derived display status ∈ healthy | idle | no_data | attention.
    /// "attention" is ONLY ever set from verified import truth — never from record age.
    let status: String
    let lastRecordAt: String?
    let recentCount: Int
    let totalCount: Int
    let staleDays: Int?           // legacy alias of daysSinceLastRecord (a fact, not a verdict)
    let message: String

    // ── The three separated truths (see health_sync_status.py) ──
    /// Technical: ok | failed | blocked | never_attempted
    let importHealth: String?
    let importReason: String?
    /// Activity: recent | none_recently | never
    let sourceActivity: String?
    /// Registry policy: continuous | event_driven | user_entered | device_generated | rare
    let activityClass: String?
    let daysSinceLastRecord: Int?

    enum CodingKeys: String, CodingKey {
        case key, label, unit, status, message
        case lastRecordAt = "last_record_at"
        case recentCount = "recent_count"
        case totalCount = "total_count"
        case staleDays = "stale_days"
        case importHealth = "import_health"
        case importReason = "import_reason"
        case sourceActivity = "source_activity"
        case activityClass = "activity_class"
        case daysSinceLastRecord = "days_since_last_record"
    }

    /// Healthy = importing without a technical problem. A source with no recent records
    /// (a rest day, no stairs, the scale untouched) is NOT unhealthy.
    var isHealthy: Bool { status != "attention" }
    /// ONLY a verified technical problem needs attention. "No data" is not a fault —
    /// the user may simply never produce that metric.
    var needsAttention: Bool { status == "attention" }
    /// Records only appear when the activity happens, so silence is expected.
    var isEventDriven: Bool { activityClass == "event_driven" }
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
