// HealthSyncView.swift
// Whole Life Journey iOS App
//
// Health Sync — redesigned around the questions a user actually has:
//   Did my data sync?  What synced?  What didn't?  Is anything broken?
//   What should I do next?
//
// Every status shown here is DETERMINISTIC backend truth from
// GET /api/mobile/health/sync-status/ (key "sync_health"): it reflects what the
// server actually received and persisted per data type. We never claim a source
// is "authorized" — HealthKit hides read-authorization, so *received data* is the
// only trustworthy signal. A source that shows "No records received" is the real,
// actionable signal (e.g. Steps enabled in iOS but not granted for reading).

import SwiftUI
import HealthKit

struct HealthSyncView: View {
    @EnvironmentObject var appState: AppState

    @State private var isRequestingPermission = false
    @State private var isSyncing = false
    @State private var isLoadingStatus = false
    @State private var status: HealthSyncStatus?
    @State private var loadError: String?
    @State private var showPermissionAlert = false
    @State private var selectedType: DataTypeHealth?

    var body: some View {
        List {
            healthStatusSection
            if let summary = status?.lastSyncSummary, hasSummaryContent(summary) {
                syncSummarySection(summary)
            }
            dataSourcesSection
            actionsSection
            if let diag = status?.diagnostics?.steps {
                stepsDiagnosticsSection(diag)
            }
            authorizationSection
            disclaimerSection
        }
        .navigationTitle("Health Sync")
        .refreshable { await loadStatus() }
        .task { await loadStatus() }
        .onReceive(NotificationCenter.default.publisher(
            for: BackgroundSyncManager.syncCompletedNotification)) { _ in
            Task { await loadStatus() }
        }
        .sheet(item: $selectedType) { type in
            DataSourceDetailView(type: type)
        }
        .alert("Permission Required", isPresented: $showPermissionAlert) {
            Button("Open Settings") { openHealthSettings() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Open Settings → Health → Data Access & Devices → Whole Life Journey and enable the sources you want to sync.")
        }
    }

    // MARK: - Health Status (the quick dashboard)

    private var healthStatusSection: some View {
        Section {
            if isLoadingStatus && status == nil {
                HStack { ProgressView().scaleEffect(0.8); Text("Checking sync status…") }
                    .foregroundColor(.secondary)
            } else if let s = status {
                StatRow(label: "Last Successful Sync",
                        value: s.lastSync?.status == "completed" || s.lastSync?.status == "partial"
                            ? HealthSyncDate.relative(s.lastSync?.at) : "Never")
                StatRow(label: "Active Data Sources",
                        value: "\(s.activeTypesCount) of \(s.totalTypesCount)")
                if let newest = s.newestData {
                    StatRow(label: "Newest Data",
                            value: "\(newest.label) • \(HealthSyncDate.relative(newest.at))")
                }
                if let oldest = s.oldestActiveSource, s.activeTypesCount > 1 {
                    StatRow(label: "Oldest Active Source",
                            value: "\(oldest.label) • \(HealthSyncDate.relative(oldest.at))")
                }
                issuesRow(s.issues)
            } else if let err = loadError {
                Label(err, systemImage: "wifi.exclamationmark")
                    .font(.caption).foregroundColor(.secondary)
            } else {
                Text("No sync data yet. Tap “Sync Health Data Now”.")
                    .foregroundColor(.secondary)
            }
        } header: {
            Text("Health Sync")
        }
    }

    @ViewBuilder
    private func issuesRow(_ issues: [SyncIssue]) -> some View {
        if issues.isEmpty {
            HStack {
                Image(systemName: "checkmark.seal.fill").foregroundColor(.green)
                Text("No issues — everything is syncing.")
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text("Issues").font(.caption).foregroundColor(.secondary)
                ForEach(issues) { issue in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(issue.message).font(.callout)
                    }
                }
            }
            .padding(.vertical, 2)
        }
    }

    // MARK: - Sync Summary (human-readable, not counters)

    private func syncSummarySection(_ summary: SyncSummary) -> some View {
        Section {
            if !summary.imported.isEmpty {
                SummaryGroup(title: "Imported", tint: .green) {
                    ForEach(summary.imported) { item in
                        summaryLine(item.label, detail: "\(item.count) \(item.count == 1 ? "record" : "records")")
                    }
                }
            }
            if !summary.noChanges.isEmpty {
                SummaryGroup(title: "No Changes", tint: .secondary) {
                    ForEach(summary.noChanges) { item in summaryLine(item.label, detail: nil) }
                }
            }
            if !summary.failed.isEmpty {
                SummaryGroup(title: "Needs Attention", tint: .orange) {
                    ForEach(summary.failed) { item in summaryLine(item.label, detail: item.reason) }
                }
            }
        } header: {
            HStack {
                Text("Last Sync")
                Spacer()
                Text(HealthSyncDate.relative(summary.at)).font(.caption).foregroundColor(.secondary)
            }
        }
    }

    private func summaryLine(_ label: String, detail: String?) -> some View {
        HStack {
            Text(label)
            Spacer()
            if let detail = detail {
                Text(detail).foregroundColor(.secondary).font(.callout)
            }
        }
    }

    // MARK: - Data Sources (per-type health; tap for details)

    private var dataSourcesSection: some View {
        Section {
            if let types = status?.dataTypes, !types.isEmpty {
                ForEach(types) { type in
                    Button { selectedType = type } label: {
                        DataSourceRow(type: type)
                    }
                    .buttonStyle(.plain)
                }
            } else {
                Text("Sync once to see the health of each source.")
                    .foregroundColor(.secondary)
            }
        } header: {
            Text("Data Sources")
        } footer: {
            Text("Tap a source to view details. A source shows healthy only when records have actually reached your WLJ account.")
        }
    }

    // MARK: - Actions

    private var actionsSection: some View {
        Section {
            Button(action: syncNow) {
                HStack {
                    if isSyncing { ProgressView().scaleEffect(0.8) }
                    else { Image(systemName: "arrow.triangle.2.circlepath") }
                    Text(isSyncing ? "Syncing…" : "Sync Health Data Now")
                }
            }
            .disabled(isSyncing || !appState.healthKitAuthorized)

            if let s = status, !s.issues.isEmpty {
                Button(action: openHealthSettings) {
                    Label("Fix in Apple Health Settings", systemImage: "gearshape")
                }
            }
        } header: {
            Text("Actions")
        }
    }

    // MARK: - Authorization (compact)

    private var authorizationSection: some View {
        Section {
            if appState.healthKitAuthorized {
                HStack {
                    Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                    Text("HealthKit connected")
                    Spacer()
                    Button("Manage") { openHealthSettings() }.font(.caption)
                }
            } else {
                Button(action: requestPermission) {
                    HStack {
                        if isRequestingPermission { ProgressView().scaleEffect(0.8) }
                        else { Image(systemName: "heart.text.square") }
                        Text("Connect Apple Health")
                    }
                }
                .disabled(isRequestingPermission)
            }
        } footer: {
            Text("Apple doesn't tell apps which read permissions you granted, so a source can look connected while sending no data. That's why WLJ shows what actually arrived — if a source says “No records received”, enable it under Apple Health → Sharing.")
        }
    }

    // MARK: - Steps Diagnostics (temporary glass-box)

    private func stepsDiagnosticsSection(_ d: StepsDiagnostics) -> some View {
        Section {
            Text(d.verdict).font(.callout)
            if let c = d.clientReported {
                StatRow(label: "HealthKit raw samples", value: "\(c["raw_samples"] ?? -1)")
                StatRow(label: "Daily totals built", value: "\(c["built"] ?? -1)")
                StatRow(label: "Sent to server", value: "\(c["sent"] ?? -1)")
            } else {
                Text("No client telemetry yet — sync once with this build.")
                    .font(.caption).foregroundColor(.secondary)
            }
            StatRow(label: "Server received (new/updated)",
                    value: "\((d.serverReceived["created"] ?? 0) + (d.serverReceived["updated"] ?? 0))")
            StatRow(label: "Server skipped / failed",
                    value: "\(d.serverReceived["skipped"] ?? 0) / \(d.serverReceived["failed"] ?? 0)")
            if !d.serverRejectionReasons.isEmpty {
                StatRow(label: "Rejection reason", value: d.serverRejectionReasons.first ?? "")
            }
            StatRow(label: "Steps rows persisted", value: "\(d.persistedTotal)")
            StatRow(label: "Recent sync batches", value: "\(d.recentRunCount)")
        } header: {
            Text("Steps Diagnostics")
        } footer: {
            Text("Temporary — shows exactly where Steps flow (device → server → database) so we can prove where they disappear.")
        }
    }

    private var disclaimerSection: some View {
        Section {
            Text("Whole Life Journey provides informational insights only. It does not provide medical advice, diagnosis, or treatment. Always consult a qualified healthcare professional for medical decisions.")
                .font(.caption).foregroundColor(.secondary).italic()
        }
    }

    // MARK: - Helpers

    private func hasSummaryContent(_ s: SyncSummary) -> Bool {
        !(s.imported.isEmpty && s.noChanges.isEmpty && s.failed.isEmpty)
    }

    private func openHealthSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }

    private func loadStatus() async {
        await MainActor.run { isLoadingStatus = true; loadError = nil }
        do {
            let resp = try await APIClient.shared.getSyncStatus()
            await MainActor.run { status = resp.syncHealth; isLoadingStatus = false }
        } catch {
            await MainActor.run { loadError = "Couldn't load sync status."; isLoadingStatus = false }
        }
    }

    private func requestPermission() {
        isRequestingPermission = true
        Task {
            do {
                try await HealthKitManager.shared.requestAuthorization()
                await MainActor.run {
                    appState.onHealthKitAuthorized()
                    isRequestingPermission = false
                }
                await syncAndReload()
            } catch {
                await MainActor.run {
                    isRequestingPermission = false
                    showPermissionAlert = true
                }
            }
        }
    }

    private func syncNow() {
        Task { await syncAndReload() }
    }

    private func syncAndReload() async {
        await MainActor.run { isSyncing = true }
        do {
            _ = try await HealthKitManager.shared.syncHealthData()
            await MainActor.run { appState.lastSyncDate = Date() }
        } catch {
            // Even on error, reload status — the backend truth still tells the story.
        }
        await loadStatus()
        await MainActor.run { isSyncing = false }
    }
}

// MARK: - Supporting Views

private struct StatRow: View {
    let label: String
    let value: String
    var body: some View {
        HStack {
            Text(label).foregroundColor(.secondary)
            Spacer()
            Text(value).multilineTextAlignment(.trailing)
        }
        .font(.callout)
    }
}

private struct SummaryGroup<Content: View>: View {
    let title: String
    let tint: Color
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased()).font(.caption2).foregroundColor(tint)
            content
        }
        .padding(.vertical, 2)
    }
}

private struct DataSourceRow: View {
    let type: DataTypeHealth

    private var indicator: (String, Color) {
        switch type.status {
        case "healthy": return ("checkmark.circle.fill", .green)
        case "idle": return ("checkmark.circle", .green)
        case "stale": return ("exclamationmark.triangle.fill", .orange)
        default: return ("exclamationmark.circle", .orange) // no_data
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: type.iconName)
                .foregroundColor(.blue).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(type.label)
                Text(type.message).font(.caption).foregroundColor(.secondary)
            }
            Spacer()
            Image(systemName: indicator.0).foregroundColor(indicator.1)
            Image(systemName: "chevron.right").font(.caption2).foregroundColor(.secondary)
        }
        .contentShape(Rectangle())
    }
}

// MARK: - Data Source Detail (replaces the non-functional "+")

struct DataSourceDetailView: View {
    let type: DataTypeHealth
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    detailRow("Status", statusText)
                    detailRow("Last Record", HealthSyncDate.relative(type.lastRecordAt))
                    detailRow("Records (last 7 days)", "\(type.recentCount)")
                    detailRow("Total Records", "\(type.totalCount)")
                    if let stale = type.staleDays, stale > 0 {
                        detailRow("Days Since Last", "\(stale)")
                    }
                } header: {
                    Text(type.label)
                } footer: {
                    Text(footerText)
                }
            }
            .navigationTitle(type.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var statusText: String {
        switch type.status {
        case "healthy": return "Healthy"
        case "idle": return "Up to date"
        case "stale": return "Stale"
        default: return "No data received"
        }
    }

    private var footerText: String {
        switch type.status {
        case "no_data":
            return "No \(type.label.lowercased()) records have reached your WLJ account. Enable \(type.label) under Apple Health → Sharing → Whole Life Journey, then Sync."
        case "stale":
            return "This source hasn't produced new data recently. Open Apple Health to confirm it's still recording."
        default:
            return "Records for this source are up to date."
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundColor(.secondary); Spacer(); Text(value) }
    }
}

// MARK: - Sync Result (retained; used by HealthKitManager)

struct SyncResult {
    let created: Int
    let updated: Int
    let skipped: Int
    let errors: Int
}

#Preview {
    NavigationStack {
        HealthSyncView().environmentObject(AppState())
    }
}
