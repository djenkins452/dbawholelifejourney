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

        // Inject JS bridge at document start so it's available before page scripts run.
        // Without this, page scripts that check window.wljNative on load would find it
        // undefined because the didFinish injection hasn't fired yet.
        let bridgeScript = WKUserScript(
            source: """
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
            """,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        contentController.addUserScript(bridgeScript)

        // Configure web view
        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.websiteDataStore = .default() // Persist cookies/session
        config.allowsInlineMediaPlayback = true

        // Append app identifier to the DEFAULT User-Agent instead of replacing it.
        // Using customUserAgent replaces the entire UA string, which can disrupt
        // WKWebView's default cookie and Origin/Referer header behavior.
        // applicationNameForUserAgent appends to the default UA, preserving all
        // WebKit cookie handling while still letting the server identify the app.
        config.applicationNameForUserAgent = "WLJWrapper/1.0"

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true

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
            // Sync CSRF cookie: read from WKHTTPCookieStore and re-inject into
            // the web content's document.cookie. This fixes a known WKWebView issue
            // where cookies set via HTTP Set-Cookie headers may not be immediately
            // visible to JavaScript or sent on subsequent form POSTs.
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
                let csrfCookie = cookies.first { $0.name == "csrftoken" }
                if let cookie = csrfCookie {
                    // Re-inject the cookie into document.cookie to ensure
                    // the web content's cookie jar is in sync with WKHTTPCookieStore
                    let js = "document.cookie = '\(cookie.name)=\(cookie.value); path=\(cookie.path); domain=\(cookie.domain)';"
                    webView.evaluateJavaScript(js) { _, _ in }
                }
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

            // Auto-trigger token exchange after login.
            // If we're on a non-login page (user is authenticated) but have no
            // API token in Keychain, request an exchange code. This handles the
            // first-login flow: user logs in via WKWebView → we detect post-login
            // navigation → generate exchange code → exchange for API token.
            let currentURL = webView.url?.absoluteString ?? ""
            let isLoginPage = currentURL.contains("/accounts/login")
                || currentURL.contains("/accounts/signup")
            let hasToken = KeychainManager.shared.getAPIToken() != nil

            if !isLoginPage && !hasToken {
                // Check if user is actually logged in by looking for session cookie
                webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
                    let hasSession = cookies.contains { $0.name == "sessionid" }
                    if hasSession {
                        print("Post-login detected, no API token — requesting exchange code")
                        self.requestExchangeCode()
                    }
                }
            }
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
            case "exchangeCode":
                // Received a one-time code from the web — exchange it for an API token
                if let code = body["code"] as? String {
                    exchangeCodeForToken(code)
                }
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
            // Use the WKWebView's session (which has the login cookie) to call
            // the Django generate-code endpoint via JavaScript fetch().
            // URLSession can't call this endpoint because it doesn't share
            // WKWebView's cookie store.
            guard let webView = webView else { return }

            let js = """
            (async function() {
                try {
                    // Get CSRF token from cookie for the POST request
                    var csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
                    var csrfToken = csrfMatch ? csrfMatch[1] : '';

                    var response = await fetch('/api/mobile/generate-code/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        credentials: 'same-origin'
                    });

                    if (response.ok) {
                        var data = await response.json();
                        // Pass the code back to native via JS bridge
                        window.webkit.messageHandlers.wljBridge.postMessage({
                            action: 'exchangeCode',
                            code: data.code
                        });
                    } else {
                        console.error('Generate code failed:', response.status);
                    }
                } catch (e) {
                    console.error('Generate code error:', e);
                }
            })();
            """

            webView.evaluateJavaScript(js) { _, error in
                if let error = error {
                    print("Exchange code JS error: \(error)")
                }
            }
        }

        private func exchangeCodeForToken(_ code: String) {
            Task {
                do {
                    let result = try await APIClient.shared.exchangeToken(code: code)
                    print("Token exchange successful for \(result.user.email)")

                    // Token is now saved in Keychain by APIClient.exchangeToken()
                    // Trigger an initial health sync now that we have a token
                    triggerHealthSync()
                } catch {
                    print("Token exchange error: \(error)")
                }
            }
        }
    }
}

#Preview {
    MainWebView()
        .environmentObject(AppState())
}
