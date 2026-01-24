// ContentView.swift
// Whole Life Journey iOS App
//
// Main content view that displays either the WebView or Settings.

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        NavigationStack {
            ZStack {
                // Main WebView
                MainWebView()
                    .ignoresSafeArea()

                // Floating settings button
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        Button(action: {
                            appState.showSettings = true
                        }) {
                            Image(systemName: "gearshape.fill")
                                .font(.title2)
                                .foregroundColor(.white)
                                .padding()
                                .background(Color.blue.opacity(0.9))
                                .clipShape(Circle())
                                .shadow(radius: 4)
                        }
                        .padding(.trailing, 20)
                        .padding(.bottom, 100)
                    }
                }
            }
            .sheet(isPresented: $appState.showSettings) {
                SettingsView()
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppState())
}
