// ContactImportView.swift
// Whole Life Journey iOS App
//
// "Import from Phone" flow. Opens the native iOS contact picker,
// sends the selected contact to the WLJ backend, then shows the result.
// One contact at a time — intentional, not sync.

import SwiftUI

struct ContactImportView: View {
    @State private var showPicker = false
    @State private var pickedContact: PickedContact?
    @State private var importResult: ContactImportResponse?
    @State private var errorMessage: String?
    @State private var isImporting = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                if let result = importResult {
                    importSuccessView(result)
                } else if isImporting {
                    ProgressView("Importing contact...")
                        .padding()
                } else if let error = errorMessage {
                    errorView(error)
                } else {
                    promptView
                }
            }
            .padding()
            .navigationTitle("Import Contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .sheet(isPresented: $showPicker) {
                ContactPickerView(pickedContact: $pickedContact)
            }
            .onChange(of: pickedContact) { _, contact in
                if let contact = contact {
                    Task { await importContact(contact) }
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

            Text("Select a contact from your phone to add them to Whole Life Journey. You can set their relationship type and add notes after import.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button(action: { showPicker = true }) {
                Label("Choose Contact", systemImage: "person.crop.circle")
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

    private func importSuccessView(_ result: ContactImportResponse) -> some View {
        VStack(spacing: 16) {
            Image(systemName: result.status == "created" ? "checkmark.circle.fill" : "person.fill.checkmark")
                .font(.system(size: 64))
                .foregroundColor(.green)

            Text(result.status == "created" ? "Contact Added" : "Already in WLJ")
                .font(.title2.bold())

            Text(result.person.displayName)
                .font(.title3)

            if !result.person.phone.isEmpty {
                Label(result.person.phone, systemImage: "phone")
                    .foregroundColor(.secondary)
            }
            if !result.person.email.isEmpty {
                Label(result.person.email, systemImage: "envelope")
                    .foregroundColor(.secondary)
            }

            if result.status == "created" {
                Text("You can now set their relationship type and add notes from the Relationships page.")
                    .font(.callout)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, 4)
            }

            Button("Done") { dismiss() }
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.accentColor)
                .foregroundColor(.white)
                .cornerRadius(12)
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

    private func importContact(_ contact: PickedContact) async {
        isImporting = true
        errorMessage = nil

        do {
            let result = try await APIClient.shared.importContact(contact)
            importResult = result
        } catch {
            errorMessage = error.localizedDescription
        }

        isImporting = false
    }
}
