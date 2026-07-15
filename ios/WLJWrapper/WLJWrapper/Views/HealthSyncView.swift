// HealthSyncView.swift
// Whole Life Journey iOS App
//
// Health Sync — a first-class, Apple-quality status screen built entirely on the
// DETERMINISTIC backend truth from GET /api/mobile/health/sync-status/ (key
// "sync_health"). It answers, at a glance:
//   Is everything healthy?  What synced?  What changed?  What needs attention?
//   What should I do next?
//
// We never claim a source is "authorized" — HealthKit hides read-authorization, so
// *received data* is the only trustworthy signal. A source showing "No data" is the
// real, actionable truth. Grouping, per-source status, counts, and the sync summary
// are all computed server-side (apps.health.services.health_sync_status) — the UI
// only renders that truth. No implementation details are exposed to the user.

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
    @State private var expandedCategories: Set<String> = []

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                if isLoadingStatus && status == nil {
                    loadingCard
                } else if let s = status {
                    HeroCard(status: s,
                             isSyncing: isSyncing,
                             canSync: appState.healthKitAuthorized,
                             onSync: syncNow)

                    if !s.issues.isEmpty {
                        AttentionCard(issues: s.issues, onFix: openHealthSettings)
                    }

                    if let summary = s.lastSyncSummary, hasSummaryContent(summary) {
                        TodaysSyncCard(summary: summary)
                    }

                    if let cats = s.categories, !cats.isEmpty {
                        categoriesView(cats)
                    }

                    connectionCard
                } else if loadError != nil {
                    errorCard
                } else {
                    setupCard
                }

                disclaimer
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 28)
            .animation(.spring(response: 0.35, dampingFraction: 0.85), value: expandedCategories)
        }
        .background(Color(uiColor: .systemGroupedBackground).ignoresSafeArea())
        .navigationTitle("Health Sync")
        .refreshable { await loadStatus() }
        .task { await loadStatus() }
        .onReceive(NotificationCenter.default.publisher(
            for: BackgroundSyncManager.syncCompletedNotification)) { _ in
            Task { await loadStatus() }
        }
        .sheet(item: $selectedType) { type in
            DataSourceDetailView(type: type, onFix: openHealthSettings)
        }
        .alert("Permission Required", isPresented: $showPermissionAlert) {
            Button("Open Settings") { openHealthSettings() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Open Settings → Health → Data Access & Devices → Whole Life Journey and enable the sources you want to sync.")
        }
    }

    // MARK: - Categories

    @ViewBuilder
    private func categoriesView(_ cats: [SyncCategory]) -> some View {
        // Active categories first, dormant (nothing has ever synced) last — so what
        // matters is on top and unused sources don't clutter the lead. Registry order
        // is preserved within each partition (filter keeps a stable order).
        let ordered = cats.filter { !$0.isDormant } + cats.filter { $0.isDormant }
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Categories")
            ForEach(ordered) { cat in
                CategoryCard(
                    category: cat,
                    isExpanded: expandedCategories.contains(cat.key),
                    onToggle: { toggle(cat.key) },
                    onSelect: { selectedType = $0 }
                )
            }
        }
    }

    private func toggle(_ key: String) {
        if expandedCategories.contains(key) { expandedCategories.remove(key) }
        else { expandedCategories.insert(key) }
    }

    // MARK: - Connection

    private var connectionCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            if appState.healthKitAuthorized {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    Text("Apple Health connected").font(.subheadline.weight(.medium))
                    Spacer()
                    Button("Manage") { openHealthSettings() }.font(.subheadline)
                }
            } else {
                Button(action: requestPermission) {
                    HStack(spacing: 8) {
                        if isRequestingPermission { ProgressView().tint(.white) }
                        else { Image(systemName: "heart.text.square.fill") }
                        Text("Connect Apple Health").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .foregroundStyle(.white)
                }
                .disabled(isRequestingPermission)
            }
            Text("Apple doesn't tell apps which read permissions you granted, so a source can look connected while sending no data. WLJ shows what actually arrived — if a source says “No data”, enable it under Apple Health → Sharing.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .wljCard()
    }

    // MARK: - Transient states

    private var loadingCard: some View {
        HStack(spacing: 10) {
            ProgressView()
            Text("Checking sync status…").foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .wljCard()
    }

    private var errorCard: some View {
        VStack(spacing: 10) {
            Image(systemName: "wifi.exclamationmark").font(.title2).foregroundStyle(.orange)
            Text(loadError ?? "Couldn't load sync status.").font(.subheadline)
            Button("Try Again") { Task { await loadStatus() } }
                .font(.subheadline.weight(.medium))
        }
        .frame(maxWidth: .infinity)
        .wljCard()
    }

    private var setupCard: some View {
        VStack(spacing: 12) {
            Image(systemName: "heart.text.square")
                .font(.system(size: 40)).foregroundStyle(Color.accentColor)
            Text("Set Up Health Sync").font(.title3.weight(.semibold))
            Text("Connect Apple Health and run your first sync to see the health of every source.")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button(action: appState.healthKitAuthorized ? syncNow : requestPermission) {
                Text(appState.healthKitAuthorized ? "Sync Now" : "Connect Apple Health")
                    .fontWeight(.semibold).frame(maxWidth: .infinity).padding(.vertical, 12)
                    .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .foregroundStyle(.white)
            }
        }
        .frame(maxWidth: .infinity)
        .wljCard()
    }

    private var disclaimer: some View {
        Text("Whole Life Journey provides informational insights only. It does not provide medical advice, diagnosis, or treatment. Always consult a qualified healthcare professional for medical decisions.")
            .font(.caption2).foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 8).padding(.top, 4)
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.secondary)
            .padding(.leading, 4)
    }

    // MARK: - Helpers / actions (behavior unchanged)

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

    private func syncNow() { Task { await syncAndReload() } }

    private func syncAndReload() async {
        await MainActor.run { isSyncing = true }
        do {
            _ = try await HealthKitManager.shared.syncHealthData()
            await MainActor.run { appState.lastSyncDate = Date() }
        } catch {
            // Even on error, reload — the backend truth still tells the story.
        }
        await loadStatus()
        await MainActor.run { isSyncing = false }
    }
}

// MARK: - Hero card (overall health at a glance)

private struct HeroCard: View {
    let status: HealthSyncStatus
    let isSyncing: Bool
    let canSync: Bool
    let onSync: () -> Void

    private var overall: OverallHealth? { status.overallHealth }

    private var tint: Color {
        switch overall?.status {
        case "healthy": return .green
        case "attention": return .orange
        default: return .accentColor
        }
    }
    private var glyph: String {
        switch overall?.status {
        case "healthy": return "checkmark.seal.fill"
        case "attention": return "exclamationmark.triangle.fill"
        default: return "heart.text.square.fill"
        }
    }
    private var title: String {
        switch overall?.status {
        case "healthy": return "All Healthy"
        case "attention": return "Needs Attention"
        default: return "Set Up Health Sync"
        }
    }
    private var subtitle: String {
        guard let o = overall else { return "Tap Sync to check your sources" }
        if o.status == "setup" || o.activeCount == 0 { return "No data has synced yet" }
        return "\(o.healthyCount) of \(o.activeCount) active sources healthy"
    }
    private var issueCount: Int { overall?.issueCount ?? status.issues.count }

    var body: some View {
        VStack(spacing: 16) {
            HStack(spacing: 14) {
                ZStack {
                    Circle().fill(tint.opacity(0.15)).frame(width: 56, height: 56)
                    Image(systemName: glyph).font(.system(size: 26, weight: .semibold)).foregroundStyle(tint)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.title2.weight(.bold))
                    Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }

            Divider()

            VStack(spacing: 10) {
                factLine("clock", "Last synced", lastSyncText)
                if let n = status.newestData {
                    factLine("sparkles", "Newest data",
                             "\(n.label) • \(HealthSyncDate.relative(n.at))")
                }
            }

            Button(action: onSync) {
                HStack(spacing: 8) {
                    if isSyncing { ProgressView().tint(.white) }
                    else { Image(systemName: "arrow.triangle.2.circlepath") }
                    Text(isSyncing ? "Syncing…" : "Sync Now").fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 12)
                .background(canSync ? Color.accentColor : Color.gray.opacity(0.4),
                            in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .foregroundStyle(.white)
            }
            .disabled(isSyncing || !canSync)
        }
        .wljCard()
    }

    private var lastSyncText: String {
        let done = status.lastSync?.status == "completed" || status.lastSync?.status == "partial"
        return done ? HealthSyncDate.relative(status.lastSync?.at) : "Never"
    }

    private func factLine(_ icon: String, _ label: String, _ value: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.caption).foregroundStyle(.secondary).frame(width: 16)
            Text(label).font(.subheadline).foregroundStyle(.secondary)
            Spacer(minLength: 8)
            Text(value).font(.subheadline.weight(.medium)).foregroundStyle(.primary)
                .lineLimit(1).minimumScaleFactor(0.7).multilineTextAlignment(.trailing)
        }
    }
}

// MARK: - Needs-attention card (what to do next)

private struct AttentionCard: View {
    let issues: [SyncIssue]
    let onFix: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Text("Needs Attention").font(.headline)
                Spacer()
                Text("\(issues.count)").font(.subheadline.weight(.bold)).foregroundStyle(.orange)
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(Color.orange.opacity(0.15), in: Capsule())
            }
            ForEach(issues) { issue in
                HStack(alignment: .top, spacing: 8) {
                    Circle().fill(.orange).frame(width: 6, height: 6).padding(.top, 6)
                    Text(issue.message).font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Button(action: onFix) {
                Label("Fix in Apple Health", systemImage: "gearshape.fill")
                    .font(.subheadline.weight(.medium))
            }
            .padding(.top, 2)
        }
        .wljCard(tint: .orange)
    }
}

// MARK: - Today's sync summary (what changed)

private struct TodaysSyncCard: View {
    let summary: SyncSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Latest Sync").font(.headline)
                Spacer()
                Text(HealthSyncDate.relative(summary.at)).font(.caption).foregroundStyle(.secondary)
            }
            if !summary.imported.isEmpty {
                group("Imported", .green, "arrow.down.circle.fill") {
                    ForEach(summary.imported) { item in
                        row(item.label, "\(item.count) \(item.count == 1 ? "record" : "records")")
                    }
                }
            }
            if !summary.noChanges.isEmpty {
                group("No Changes", Color.secondary, "equal.circle.fill") {
                    ForEach(summary.noChanges) { item in row(item.label, nil) }
                }
            }
            if !summary.failed.isEmpty {
                group("Needs Attention", .orange, "xmark.circle.fill") {
                    ForEach(summary.failed) { item in row(item.label, item.reason) }
                }
            }
        }
        .wljCard()
    }

    @ViewBuilder
    private func group<Content: View>(_ title: String, _ tint: Color, _ icon: String,
                                      @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.caption).foregroundStyle(tint)
                Text(title.uppercased()).font(.caption.weight(.semibold)).foregroundStyle(tint)
            }
            content()
        }
    }

    private func row(_ label: String, _ detail: String?) -> some View {
        HStack {
            Text(label).font(.subheadline)
            Spacer()
            if let detail = detail {
                Text(detail).font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .padding(.leading, 22)
    }
}

// MARK: - Category card (collapsible group of sources)

private struct CategoryCard: View {
    let category: SyncCategory
    let isExpanded: Bool
    let onToggle: () -> Void
    let onSelect: (DataTypeHealth) -> Void

    var body: some View {
        VStack(spacing: 0) {
            Button(action: onToggle) {
                HStack(spacing: 12) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .fill(statusTint.opacity(0.15)).frame(width: 36, height: 36)
                        Image(systemName: HealthSyncIcons.category(category.key))
                            .font(.system(size: 16, weight: .semibold)).foregroundStyle(statusTint)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(category.label).font(.body.weight(.semibold)).foregroundStyle(.primary)
                        Text(summaryText).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    statusChip
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if isExpanded {
                Divider().padding(.leading, 48).padding(.top, 10).padding(.bottom, 2)
                ForEach(Array(category.types.enumerated()), id: \.element.id) { idx, type in
                    Button { onSelect(type) } label: { MetricRow(type: type) }
                        .buttonStyle(.plain)
                    if idx < category.types.count - 1 {
                        Divider().padding(.leading, 40)
                    }
                }
            }
        }
        .wljCard()
    }

    private var statusTint: Color {
        if category.needsAttention { return .orange }
        if category.isDormant { return .secondary }
        return .green
    }
    private var summaryText: String {
        if category.isDormant { return "No data yet" }
        if category.staleCount > 0 {
            return "\(category.staleCount) need attention • \(category.healthyCount) healthy"
        }
        return "\(category.healthyCount) of \(category.activeCount) healthy"
    }
    @ViewBuilder private var statusChip: some View {
        if category.needsAttention {
            chip("\(category.staleCount)", .orange)
        } else if category.isDormant {
            chip("—", .secondary)
        } else {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.body)
        }
    }
    private func chip(_ text: String, _ tint: Color) -> some View {
        Text(text).font(.caption.weight(.bold)).foregroundStyle(tint)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(tint.opacity(0.15), in: Capsule())
    }
}

// MARK: - Metric row + status indicator

private struct MetricRow: View {
    let type: DataTypeHealth
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: type.iconName).font(.body).foregroundStyle(.blue).frame(width: 26)
            VStack(alignment: .leading, spacing: 2) {
                Text(type.label).font(.subheadline).foregroundStyle(.primary)
                Text(type.message).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            StatusIndicator(status: type.status)
            Image(systemName: "chevron.right").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 2)
        .contentShape(Rectangle())
    }
}

private struct StatusIndicator: View {
    let status: String
    var body: some View {
        let style = HealthSyncStatusStyle.of(status)
        Image(systemName: style.icon).foregroundStyle(style.tint).font(.body)
    }
}

// MARK: - Shared status styling

enum HealthSyncStatusStyle {
    struct Style { let icon: String; let tint: Color; let label: String }
    /// The single mapping from a deterministic per-source status to its visual style.
    static func of(_ status: String) -> Style {
        switch status {
        case "healthy": return Style(icon: "checkmark.circle.fill", tint: .green, label: "Healthy")
        case "idle":    return Style(icon: "checkmark.circle.fill", tint: .green, label: "Up to date")
        case "stale":   return Style(icon: "exclamationmark.triangle.fill", tint: .orange, label: "Stale")
        case "no_data": return Style(icon: "circle.dashed", tint: .secondary, label: "No data")
        default:        return Style(icon: "questionmark.circle", tint: .gray, label: status.capitalized)
        }
    }
}

enum HealthSyncIcons {
    static func category(_ key: String) -> String {
        switch key {
        case "activity": return "figure.walk"
        case "heart_vitals": return "heart.fill"
        case "respiratory": return "lungs.fill"
        case "sleep": return "bed.double.fill"
        case "body": return "figure.arms.open"
        case "mobility": return "figure.walk.motion"
        case "nutrition": return "fork.knife"
        case "hearing": return "ear.fill"
        case "mental": return "brain.head.profile"
        case "workouts": return "figure.run"
        default: return "square.grid.2x2.fill"
        }
    }
}

// MARK: - Card styling

private struct WLJCard: ViewModifier {
    var tint: Color?
    func body(content: Content) -> some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color(uiColor: .secondarySystemGroupedBackground))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder((tint ?? .clear).opacity(0.28), lineWidth: tint == nil ? 0 : 1)
            )
    }
}

private extension View {
    func wljCard(tint: Color? = nil) -> some View { modifier(WLJCard(tint: tint)) }
}

// MARK: - Data source detail (deep-dive; replaces any dead affordance)

struct DataSourceDetailView: View {
    let type: DataTypeHealth
    var onFix: (() -> Void)? = nil
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Image(systemName: type.iconName).font(.title2)
                            .foregroundStyle(.blue).frame(width: 30)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(type.label).font(.headline)
                            let style = HealthSyncStatusStyle.of(type.status)
                            HStack(spacing: 5) {
                                Image(systemName: style.icon).foregroundStyle(style.tint).font(.caption)
                                Text(style.label).font(.caption).foregroundStyle(style.tint)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section("Details") {
                    detailRow("Last record", HealthSyncDate.relative(type.lastRecordAt))
                    detailRow("Records · last 7 days", "\(type.recentCount)")
                    detailRow("Total records", "\(type.totalCount)")
                    if let stale = type.staleDays, stale > 0 {
                        detailRow("Days since last", "\(stale)")
                    }
                    detailRow("Source", "Apple Health")
                }

                Section("Suggested action") {
                    Text(suggestion).font(.subheadline).foregroundStyle(.secondary)
                    if (type.status == "no_data" || type.status == "stale"), let onFix {
                        Button {
                            dismiss()
                            onFix()
                        } label: {
                            Label("Open Apple Health Settings", systemImage: "gearshape.fill")
                        }
                    }
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

    private var suggestion: String {
        switch type.status {
        case "no_data":
            return "No \(type.label.lowercased()) records have reached your WLJ account yet. Enable \(type.label) under Apple Health → Sharing → Whole Life Journey, then Sync."
        case "stale":
            return "This source hasn't produced new data in \(type.staleDays ?? 0) days. Open Apple Health to confirm the device is still recording."
        case "idle":
            return "Up to date. This source records occasionally, so gaps between readings are normal."
        default:
            return "Everything looks good — records are arriving on schedule."
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(.secondary); Spacer(); Text(value) }
            .font(.subheadline)
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
