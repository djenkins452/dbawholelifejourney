// MainWebView.swift
// Whole Life Journey iOS App
//
// Secure WKWebView wrapper that:
// - Only allows WLJ domains
// - Persists login sessions
// - Handles JS bridge messages
// - Supports deep links

import SwiftUI
import WebKit

struct MainWebView: UIViewRepresentable {
    @EnvironmentObject var appState: AppState

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> WKWebView {
        // Configure content controller for JS bridge
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "wljBridge")

        // Configure web view
        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.websiteDataStore = .default() // Persist cookies/session
        config.allowsInlineMediaPlayback = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true

        // Enable inspection in debug builds
        #if DEBUG
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }
        #endif

        // Load WLJ
        if let url = URL(string: "https://wholelifejourney.com") {
            webView.load(URLRequest(url: url))
        }

        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        // Handle updates if needed
    }

    // MARK: - Coordinator
    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        var parent: MainWebView

        // Allowed domains for navigation
        private let allowedDomains = [
            "wholelifejourney.com",
            "www.wholelifejourney.com"
        ]

        init(_ parent: MainWebView) {
            self.parent = parent
        }

        // MARK: - WKNavigationDelegate

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }

            // Handle custom URL schemes
            if url.scheme == "wlj" {
                handleCustomURL(url)
                decisionHandler(.cancel)
                return
            }

            // Only allow HTTPS
            guard url.scheme == "https" else {
                decisionHandler(.cancel)
                return
            }

            // Check domain allowlist
            if let host = url.host, allowedDomains.contains(where: { host == $0 || host.hasSuffix(".\($0)") }) {
                decisionHandler(.allow)
            } else {
                // Open external links in Safari
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // Inject JS bridge helper after page loads
            let js = """
            window.wljNative = {
                requestHealthSync: function() {
                    window.webkit.messageHandlers.wljBridge.postMessage({action: 'healthSync'});
                },
                requestExchangeCode: function() {
                    window.webkit.messageHandlers.wljBridge.postMessage({action: 'requestExchangeCode'});
                },
                openSettings: function() {
                    window.webkit.messageHandlers.wljBridge.postMessage({action: 'openSettings'});
                },
                logout: function() {
                    window.webkit.messageHandlers.wljBridge.postMessage({action: 'logout'});
                },
                isNativeApp: true
            };
            console.log('WLJ Native bridge initialized');
            """
            webView.evaluateJavaScript(js, completionHandler: nil)
        }

        // MARK: - WKScriptMessageHandler

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any],
                  let action = body["action"] as? String else {
                return
            }

            switch action {
            case "healthSync":
                triggerHealthSync()
            case "requestExchangeCode":
                requestExchangeCode()
            case "openSettings":
                DispatchQueue.main.async {
                    self.parent.appState.showSettings = true
                }
            case "logout":
                DispatchQueue.main.async {
                    self.parent.appState.logout()
                }
            default:
                print("Unknown bridge action: \(action)")
            }
        }

        // MARK: - Custom URL Handling

        private func handleCustomURL(_ url: URL) {
            guard let host = url.host else { return }

            switch host {
            case "health":
                if url.path == "/sync" {
                    triggerHealthSync()
                }
            case "settings":
                DispatchQueue.main.async {
                    self.parent.appState.showSettings = true
                }
            default:
                print("Unknown custom URL: \(url)")
            }
        }

        // MARK: - Health Sync

        private func triggerHealthSync() {
            Task {
                do {
                    _ = try await HealthKitManager.shared.syncHealthData()
                    DispatchQueue.main.async {
                        self.parent.appState.lastSyncDate = Date()
                    }
                } catch {
                    print("Health sync error: \(error)")
                }
            }
        }

        // MARK: - Token Exchange

        private func requestExchangeCode() {
            // This would be called when user logs in via web
            // The web sends us a code, we exchange it for a token
            print("Exchange code requested - implement web-side JS to pass code")
        }
    }
}

#Preview {
    MainWebView()
        .environmentObject(AppState())
}
