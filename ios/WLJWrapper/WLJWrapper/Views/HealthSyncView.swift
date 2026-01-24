// HealthSyncView.swift
// Whole Life Journey iOS App
//
// Detailed health sync settings and controls.
// Shows what data types are synced and allows manual sync.

import SwiftUI
import HealthKit

struct HealthSyncView: View {
    @EnvironmentObject var appState: AppState
    @State private var isRequestingPermission = false
    @State private var isSyncing = false
    @State private var syncResult: SyncResult?
    @State private var showPermissionAlert = false

    var body: some View {
        List {
            // MARK: - Authorization Section
            Section {
                if appState.healthKitAuthorized {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                        Text("HealthKit Authorized")
                    }
                } else {
                    Button(action: requestPermission) {
                        HStack {
                            if isRequestingPermission {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "heart.text.square")
                            }
                            Text("Authorize HealthKit")
                        }
                    }
                    .disabled(isRequestingPermission)
                }
            } header: {
                Text("Authorization")
            } footer: {
                Text("Grant permission to read your health data from Apple Health.")
            }

            // MARK: - Data Types Section
            Section {
                DataTypeRow(icon: "figure.walk", title: "Steps", description: "Daily step count")
                DataTypeRow(icon: "scalemass", title: "Weight", description: "Body weight measurements")
                DataTypeRow(icon: "bed.double", title: "Sleep", description: "Sleep analysis and stages")
                DataTypeRow(icon: "heart", title: "Heart Rate", description: "Resting and average heart rate")
                DataTypeRow(icon: "drop.fill", title: "Blood Glucose", description: "CGM readings from Dexcom")
                DataTypeRow(icon: "lungs.fill", title: "Blood Oxygen", description: "SpO2 from Apple Watch")
                DataTypeRow(icon: "drop.triangle.fill", title: "Water Intake", description: "Daily hydration")
                DataTypeRow(icon: "flame.fill", title: "Active Calories", description: "Calories burned from activity")
                DataTypeRow(icon: "figure.run", title: "Distance", description: "Walking and running distance")
                DataTypeRow(icon: "bolt.fill", title: "Resting Calories", description: "Basal metabolic rate")
                DataTypeRow(icon: "figure.stairs", title: "Flights Climbed", description: "Stairs climbed")
            } header: {
                Text("Synced Data Types")
            } footer: {
                Text("These health metrics will be synced to your Whole Life Journey account.")
            }

            // MARK: - Manual Sync Section
            Section {
                Button(action: syncNow) {
                    HStack {
                        if isSyncing {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "arrow.triangle.2.circlepath")
                        }
                        Text(isSyncing ? "Syncing..." : "Sync Health Data Now")
                    }
                }
                .disabled(isSyncing || !appState.healthKitAuthorized)

                if let result = syncResult {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Last Sync Result")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        HStack {
                            Label("\(result.created) created", systemImage: "plus.circle")
                            Spacer()
                            Label("\(result.updated) updated", systemImage: "arrow.triangle.2.circlepath.circle")
                        }
                        .font(.caption)

                        if result.errors > 0 {
                            Label("\(result.errors) errors", systemImage: "exclamationmark.triangle")
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("Manual Sync")
            }

            // MARK: - Info Section
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text("How It Works")
                        .font(.headline)

                    Text("1. Your health data stays on your device until you sync")
                    Text("2. Only the data types listed above are synced")
                    Text("3. Data is sent securely to your WLJ account")
                    Text("4. You can revoke access anytime in iOS Settings")
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
        }
        .navigationTitle("Health Sync")
        .alert("Permission Required", isPresented: $showPermissionAlert) {
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Please enable HealthKit access in Settings to sync your health data.")
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
            } catch {
                await MainActor.run {
                    isRequestingPermission = false
                    showPermissionAlert = true
                }
            }
        }
    }

    private func syncNow() {
        isSyncing = true

        Task {
            do {
                let result = try await HealthKitManager.shared.syncHealthData()
                await MainActor.run {
                    syncResult = result
                    appState.lastSyncDate = Date()
                    isSyncing = false
                }
            } catch {
                await MainActor.run {
                    syncResult = SyncResult(created: 0, updated: 0, skipped: 0, errors: 1)
                    isSyncing = false
                }
            }
        }
    }
}

// MARK: - Supporting Views

struct DataTypeRow: View {
    let icon: String
    let title: String
    let description: String

    var body: some View {
        HStack {
            Image(systemName: icon)
                .foregroundColor(.blue)
                .frame(width: 24)
            VStack(alignment: .leading) {
                Text(title)
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }
}

// MARK: - Sync Result

struct SyncResult {
    let created: Int
    let updated: Int
    let skipped: Int
    let errors: Int
}

#Preview {
    NavigationStack {
        HealthSyncView()
            .environmentObject(AppState())
    }
}
