// ContactImportView.swift
// Whole Life Journey iOS App
//
// "Import from Phone" flow. Opens the native iOS contact picker with
// multi-select support. Imports each selected contact to the WLJ backend
// sequentially, showing progress and a summary when done.

import SwiftUI

struct ContactImportView: View {
    @State private var showPicker = false
    @State private var pickedContacts: [PickedContact] = []
    @State private var importResults: [ImportResultItem] = []
    @State private var errorMessage: String?
    @State private var isImporting = false
    @State private var importProgress: (current: Int, total: Int) = (0, 0)
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                if !importResults.isEmpty && !isImporting {
                    importSummaryView
                } else if isImporting {
                    importProgressView
                } else if let error = errorMessage {
                    errorView(error)
                } else {
                    promptView
                }
            }
            .padding()
            .navigationTitle("Import Contacts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .sheet(isPresented: $showPicker) {
                ContactPickerView(pickedContacts: $pickedContacts, onCancel: { showPicker = false })
            }
            .onChange(of: pickedContacts) { _, contacts in
                if !contacts.isEmpty {
                    Task { await importContacts(contacts) }
                }
            }
        }
    }

    // MARK: - Subviews

    private var promptView: some View {
        VStack(spacing: 16) {
            Image(systemName: "person.crop.circle.badge.plus")
                .font(.system(size: 64))
                .foregroundColor(.accentColor)

            Text("Import from Phone")
                .font(.title2.bold())

            Text("Select one or more contacts from your phone to add them to Whole Life Journey. You can set their relationship type and add notes after import.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button(action: { showPicker = true }) {
                Label("Choose Contacts", systemImage: "person.2.crop.square.stack")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.accentColor)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .padding(.top, 8)
        }
    }

    private var importProgressView: some View {
        VStack(spacing: 16) {
            ProgressView(value: Double(importProgress.current), total: Double(importProgress.total))
                .progressViewStyle(.linear)
                .padding(.horizontal)

            Text("Importing \(importProgress.current) of \(importProgress.total)...")
                .font(.headline)
                .foregroundColor(.secondary)

            if let latest = importResults.last {
                Text(latest.name)
                    .font(.body)
                    .foregroundColor(.secondary)
            }
        }
    }

    private var importSummaryView: some View {
        VStack(spacing: 16) {
            let created = importResults.filter { $0.status == .created }.count
            let existing = importResults.filter { $0.status == .existing }.count
            let failed = importResults.filter { $0.status == .failed }.count

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 64))
                .foregroundColor(.green)

            Text("Import Complete")
                .font(.title2.bold())

            // Summary counts
            VStack(spacing: 8) {
                if created > 0 {
                    Label("\(created) added", systemImage: "plus.circle.fill")
                        .foregroundColor(.green)
                }
                if existing > 0 {
                    Label("\(existing) already in WLJ", systemImage: "person.fill.checkmark")
                        .foregroundColor(.blue)
                }
                if failed > 0 {
                    Label("\(failed) failed", systemImage: "exclamationmark.circle.fill")
                        .foregroundColor(.red)
                }
            }
            .font(.body)

            // Contact list
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(importResults) { item in
                        HStack {
                            Image(systemName: item.status.icon)
                                .foregroundColor(item.status.color)
                            Text(item.name)
                                .font(.body)
                            Spacer()
                            Text(item.status.label)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(8)
                    }
                }
            }
            .frame(maxHeight: 200)

            // Action buttons
            VStack(spacing: 12) {
                Button(action: {
                    // Reset for another round
                    importResults = []
                    pickedContacts = []
                    showPicker = true
                }) {
                    Label("Import More", systemImage: "plus")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color(.secondarySystemBackground))
                        .foregroundColor(.accentColor)
                        .cornerRadius(12)
                }

                Button(action: {
                    NotificationCenter.default.post(name: .contactImported, object: nil)
                    dismiss()
                }) {
                    Text("Done")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.accentColor)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
            }
            .padding(.top, 8)
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundColor(.orange)

            Text("Import Failed")
                .font(.title2.bold())

            Text(message)
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button("Try Again") {
                errorMessage = nil
                showPicker = true
            }
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.accentColor)
            .foregroundColor(.white)
            .cornerRadius(12)
        }
    }

    // MARK: - Import Logic

    private func importContacts(_ contacts: [PickedContact]) async {
        isImporting = true
        errorMessage = nil
        importResults = []
        importProgress = (0, contacts.count)

        for (index, contact) in contacts.enumerated() {
            importProgress = (index + 1, contacts.count)
            let name = [contact.firstName, contact.lastName].filter { !$0.isEmpty }.joined(separator: " ")

            do {
                let result = try await APIClient.shared.importContact(contact)
                let status: ImportStatus = result.status == "created" ? .created : .existing
                importResults.append(ImportResultItem(name: result.person.displayName, status: status))
            } catch {
                importResults.append(ImportResultItem(name: name.isEmpty ? "Unknown" : name, status: .failed))
            }
        }

        isImporting = false
    }
}

// MARK: - Supporting Types

struct ImportResultItem: Identifiable {
    let id = UUID()
    let name: String
    let status: ImportStatus
}

enum ImportStatus {
    case created
    case existing
    case failed

    var icon: String {
        switch self {
        case .created: return "plus.circle.fill"
        case .existing: return "person.fill.checkmark"
        case .failed: return "xmark.circle.fill"
        }
    }

    var color: Color {
        switch self {
        case .created: return .green
        case .existing: return .blue
        case .failed: return .red
        }
    }

    var label: String {
        switch self {
        case .created: return "Added"
        case .existing: return "Exists"
        case .failed: return "Failed"
        }
    }
}
