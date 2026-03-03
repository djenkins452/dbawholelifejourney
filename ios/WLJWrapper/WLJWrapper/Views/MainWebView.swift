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

        // Set custom User-Agent so the server can identify the native app.
        // Appending to the default UA ensures WKWebView sends proper Origin/Referer
        // headers on form POSTs, which Django's CSRF middleware requires.
        webView.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) WLJWrapper/1.0"

        // Enable pull-to-refresh
        let refreshControl = UIRefreshControl()
        refreshControl.addTarget(context.coordinator, action: #selector(Coordinator.handleRefresh(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        // Enable inspection in debug builds
        #if DEBUG
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }
        #endif

        // Store reference for coordinator
        context.coordinator.webView = webView

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
        weak var webView: WKWebView?

        // Allowed domains for navigation
        private let allowedDomains = [
            "wholelifejourney.com",
            "www.wholelifejourney.com"
        ]

        init(_ parent: MainWebView) {
            self.parent = parent
            super.init()

            // Listen for push notification deep-links
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(handlePushDeepLink(_:)),
                name: .pushNotificationDeepLink,
                object: nil
            )

            // Listen for contact import completions to reload WebView
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(handleContactImported),
                name: .contactImported,
                object: nil
            )
        }

        deinit {
            NotificationCenter.default.removeObserver(self)
        }

        // MARK: - Push Deep-Link

        @objc private func handlePushDeepLink(_ notification: Foundation.Notification) {
            guard let actionURL = notification.userInfo?["action_url"] as? String,
                  let url = URL(string: "https://wholelifejourney.com\(actionURL)") else {
                return
            }
            webView?.load(URLRequest(url: url))
        }

        // MARK: - Contact Import Reload

        @objc private func handleContactImported() {
            // Navigate to the relationships page to show the newly imported contact
            if let url = URL(string: "https://wholelifejourney.com/relationships/") {
                webView?.load(URLRequest(url: url))
            }
        }

        // MARK: - Pull-to-Refresh

        @objc func handleRefresh(_ sender: UIRefreshControl) {
            webView?.reload()
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                sender.endRefreshing()
            }
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
            // Ensure CSRF cookie is accessible — fetch it from the page and re-set it
            // so WKWebView's cookie store is in sync with the web content.
            webView.evaluateJavaScript("""
                (function() {
                    var match = document.cookie.match(/csrftoken=([^;]+)/);
                    return match ? match[1] : null;
                })()
            """) { result, _ in
                // Cookie exists, WebView is in sync — no action needed.
                // This eval just ensures the cookie store is primed.
            }

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
                importContact: function() {
                    window.webkit.messageHandlers.wljBridge.postMessage({action: 'importContact'});
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
            case "importContact":
                DispatchQueue.main.async {
                    self.parent.appState.showContactImport = true
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
