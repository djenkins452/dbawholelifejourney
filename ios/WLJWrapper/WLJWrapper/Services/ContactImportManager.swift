// ContactImportManager.swift
// Whole Life Journey iOS App
//
// Wraps CNContactPickerViewController for multi-contact import.
// Uses the native iOS contact picker — no bulk access, no background sync.
// The user explicitly picks contacts from the native UI.

import ContactsUI
import SwiftUI

// PickedContact is defined in APIClient.swift so both files compile independently.

/// Bridges CNContactPickerViewController into SwiftUI.
/// Presents the native iOS contact picker and extracts name/phone/email
/// from one or more contacts the user selects.
struct ContactPickerView: UIViewControllerRepresentable {
    @Binding var pickedContacts: [PickedContact]
    var onCancel: () -> Void

    func makeUIViewController(context: Context) -> CNContactPickerViewController {
        let picker = CNContactPickerViewController()
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: CNContactPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, CNContactPickerDelegate {
        let parent: ContactPickerView

        init(_ parent: ContactPickerView) {
            self.parent = parent
        }

        /// Multi-select: user taps Done after selecting one or more contacts
        func contactPicker(_ picker: CNContactPickerViewController, didSelect contacts: [CNContact]) {
            parent.pickedContacts = contacts.map { contact in
                let phone = contact.phoneNumbers.first?.value.stringValue
                let email = contact.emailAddresses.first?.value as String?
                return PickedContact(
                    firstName: contact.givenName,
                    lastName: contact.familyName,
                    phone: phone,
                    email: email
                )
            }
        }

        func contactPickerDidCancel(_ picker: CNContactPickerViewController) {
            parent.onCancel()
        }
    }
}
