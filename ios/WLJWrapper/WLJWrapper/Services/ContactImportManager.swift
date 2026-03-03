// ContactImportManager.swift
// Whole Life Journey iOS App
//
// Wraps CNContactPickerViewController for single-contact import.
// Uses the native iOS contact picker — no bulk access, no background sync.
// The user explicitly picks one contact at a time.

import ContactsUI
import SwiftUI

// PickedContact is defined in APIClient.swift so both files compile independently.

/// Bridges CNContactPickerViewController into SwiftUI.
/// Presents the native iOS contact picker and extracts name/phone/email
/// from the single contact the user selects.
struct ContactPickerView: UIViewControllerRepresentable {
    @Binding var pickedContact: PickedContact?
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

        func contactPicker(_ picker: CNContactPickerViewController, didSelect contact: CNContact) {
            let phone = contact.phoneNumbers.first?.value.stringValue
            let email = contact.emailAddresses.first?.value as String?

            parent.pickedContact = PickedContact(
                firstName: contact.givenName,
                lastName: contact.familyName,
                phone: phone,
                email: email
            )
        }

        func contactPickerDidCancel(_ picker: CNContactPickerViewController) {
            parent.onCancel()
        }
    }
}
