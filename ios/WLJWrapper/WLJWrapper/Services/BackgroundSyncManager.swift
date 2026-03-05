// BackgroundSyncManager.swift
// Whole Life Journey iOS App
//
// Manages background health data sync using HealthKit observer queries
// and background app refresh.

import Foundation
import HealthKit
import BackgroundTasks
import UIKit

class BackgroundSyncManager {
    static let shared = BackgroundSyncManager()

    private let healthStore = HKHealthStore()
    private var observerQueries: [HKObserverQuery] = []

    // Background task identifier
    static let healthSyncTaskId = "com.wholelifejourney.app.healthsync"

    // Notification posted when any sync completes (background or foreground)
    static let syncCompletedNotification = Notification.Name("HealthSyncCompleted")

    // Throttle: prevent excessive syncs from observer queries and app activations.
    // Without throttling, 23 observer queries + frequent app opens = 90+ syncs/day,
    // each resending 7 days of unchanged data (95%+ dedup skips on server).
    private var lastScheduleTime: Date?
    private let scheduleThrottleInterval: TimeInterval = 300  // 5 min between BG task schedules

    private var lastForegroundSyncTime: Date?
    private let foregroundSyncThrottleInterval: TimeInterval = 1800  // 30 min between foreground syncs

    private var isSyncing = false  // prevent concurrent syncs

    private init() {}

    // MARK: - Setup

    /// Call this from AppDelegate/App init to set up background sync
    func setupBackgroundSync() {
        // Register background task
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.healthSyncTaskId,
            using: nil
        ) { task in
            self.handleBackgroundTask(task as! BGProcessingTask)
        }

        // Set up HealthKit observer queries if authorized
        if HealthKitManager.shared.isAuthorized {
            enableBackgroundDelivery()
        }
    }

    // MARK: - HealthKit Background Delivery

    /// Enable background delivery for key health types.
    /// We observe a focused set of types that change frequently and matter most.
    /// Other types (mobility, audio, etc.) are picked up in each full sync.
    func enableBackgroundDelivery() {
        guard HKHealthStore.isHealthDataAvailable() else { return }

        // Core types to observe — these change frequently and are most important.
        // Reducing from 23 to 10 types to cut observer-triggered syncs.
        let typesToObserve: [HKSampleType] = [
            HKQuantityType.quantityType(forIdentifier: .stepCount),
            HKQuantityType.quantityType(forIdentifier: .bodyMass),
            HKQuantityType.quantityType(forIdentifier: .bodyFatPercentage),
            HKQuantityType.quantityType(forIdentifier: .leanBodyMass),
            HKQuantityType.quantityType(forIdentifier: .bloodGlucose),
            HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned),
            HKCategoryType.categoryType(forIdentifier: .sleepAnalysis),
            HKObjectType.workoutType(),
            HKQuantityType.quantityType(forIdentifier: .restingHeartRate),
            HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN),
        ].compactMap { $0 }

        for sampleType in typesToObserve {
            // Enable background delivery
            healthStore.enableBackgroundDelivery(
                for: sampleType,
                frequency: .hourly
            ) { success, error in
                if let error = error {
                    print("Failed to enable background delivery for \(sampleType): \(error)")
                }
            }

            // Create observer query
            let query = HKObserverQuery(
                sampleType: sampleType,
                predicate: nil
            ) { [weak self] query, completionHandler, error in
                if let error = error {
                    print("Observer query error for \(sampleType): \(error)")
                    completionHandler()
                    return
                }

                // New data available - schedule a sync (throttled)
                self?.scheduleBackgroundSync()
                completionHandler()
            }

            healthStore.execute(query)
            observerQueries.append(query)
        }
    }

    /// Disable background delivery (call when user logs out)
    func disableBackgroundDelivery() {
        // Stop all observer queries
        for query in observerQueries {
            healthStore.stop(query)
        }
        observerQueries.removeAll()

        // Disable background delivery
        healthStore.disableAllBackgroundDelivery { success, error in
            if let error = error {
                print("Failed to disable background delivery: \(error)")
            }
        }
    }

    // MARK: - Background Task Scheduling

    /// Schedule a background sync task (throttled to prevent runaway loops)
    func scheduleBackgroundSync() {
        // Throttle: only schedule if enough time has passed since last schedule
        if let lastTime = lastScheduleTime,
           Date().timeIntervalSince(lastTime) < scheduleThrottleInterval {
            return
        }

        let request = BGProcessingTaskRequest(identifier: Self.healthSyncTaskId)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false

        // Schedule for at least 15 minutes from now
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)

        do {
            try BGTaskScheduler.shared.submit(request)
            lastScheduleTime = Date()
            print("Background sync task scheduled")
        } catch {
            print("Failed to schedule background sync: \(error)")
        }
    }

    /// Handle the background task when it runs
    private func handleBackgroundTask(_ task: BGProcessingTask) {
        // Schedule next sync
        scheduleBackgroundSync()

        // Create a task to sync health data
        let syncTask = Task {
            do {
                // Check if authenticated
                guard KeychainManager.shared.getAPIToken() != nil else {
                    print("Background sync skipped: not authenticated")
                    task.setTaskCompleted(success: true)
                    return
                }

                // Perform sync (with concurrency guard)
                guard !isSyncing else {
                    print("Background sync skipped: sync already in progress")
                    task.setTaskCompleted(success: true)
                    return
                }

                isSyncing = true
                defer { isSyncing = false }

                _ = try await HealthKitManager.shared.syncHealthData()
                print("Background sync completed successfully")

                // Post notification so UI can update
                await MainActor.run {
                    NotificationCenter.default.post(name: Self.syncCompletedNotification, object: nil)
                }

                task.setTaskCompleted(success: true)
            } catch {
                print("Background sync failed: \(error)")
                isSyncing = false
                task.setTaskCompleted(success: false)
            }
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
            task.setTaskCompleted(success: false)
        }
    }

    // MARK: - App Lifecycle

    /// Call when app enters background
    func applicationDidEnterBackground() {
        scheduleBackgroundSync()
    }

    /// Call when app becomes active — sync with throttle to avoid excessive requests.
    /// Without throttle: every app open triggers a full 7-day sync (~460 metrics).
    /// With 30-min throttle: max ~48 foreground syncs/day instead of 90+.
    func applicationDidBecomeActive() {
        // Throttle foreground syncs
        if let lastTime = lastForegroundSyncTime,
           Date().timeIntervalSince(lastTime) < foregroundSyncThrottleInterval {
            return
        }

        guard KeychainManager.shared.getAPIToken() != nil else { return }
        guard !isSyncing else { return }

        lastForegroundSyncTime = Date()

        Task {
            do {
                isSyncing = true
                defer { isSyncing = false }

                _ = try await HealthKitManager.shared.syncHealthData()
                print("Foreground sync completed")

                // Post notification so UI can update
                await MainActor.run {
                    NotificationCenter.default.post(name: Self.syncCompletedNotification, object: nil)
                }
            } catch {
                print("Foreground sync failed: \(error)")
                isSyncing = false
            }
        }
    }

    /// Force an immediate sync regardless of throttle (e.g., user taps "Sync Now")
    func forceSync() {
        guard KeychainManager.shared.getAPIToken() != nil else { return }
        guard !isSyncing else { return }

        lastForegroundSyncTime = Date()

        Task {
            do {
                isSyncing = true
                defer { isSyncing = false }

                _ = try await HealthKitManager.shared.syncHealthData()
                print("Forced sync completed")

                await MainActor.run {
                    NotificationCenter.default.post(name: Self.syncCompletedNotification, object: nil)
                }
            } catch {
                print("Forced sync failed: \(error)")
                isSyncing = false
            }
        }
    }
}
