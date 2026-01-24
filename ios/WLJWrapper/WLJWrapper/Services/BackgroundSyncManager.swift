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

    /// Enable background delivery for all health types
    func enableBackgroundDelivery() {
        guard HKHealthStore.isHealthDataAvailable() else { return }

        // Types to observe
        let typesToObserve: [HKSampleType] = [
            HKQuantityType.quantityType(forIdentifier: .stepCount),
            HKQuantityType.quantityType(forIdentifier: .bodyMass),
            HKQuantityType.quantityType(forIdentifier: .restingHeartRate),
            HKQuantityType.quantityType(forIdentifier: .bloodGlucose),
            HKQuantityType.quantityType(forIdentifier: .oxygenSaturation),
            HKQuantityType.quantityType(forIdentifier: .dietaryWater),
            HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned),
            HKQuantityType.quantityType(forIdentifier: .distanceWalkingRunning),
            HKQuantityType.quantityType(forIdentifier: .basalEnergyBurned),
            HKQuantityType.quantityType(forIdentifier: .flightsClimbed),
            HKQuantityType.quantityType(forIdentifier: .appleExerciseTime),
            HKQuantityType.quantityType(forIdentifier: .appleStandTime),
            HKQuantityType.quantityType(forIdentifier: .bodyFatPercentage),
            HKCategoryType.categoryType(forIdentifier: .sleepAnalysis),
            HKObjectType.workoutType()
        ].compactMap { $0 }

        for sampleType in typesToObserve {
            // Enable background delivery
            healthStore.enableBackgroundDelivery(
                for: sampleType,
                frequency: .hourly
            ) { success, error in
                if let error = error {
                    print("Failed to enable background delivery for \(sampleType): \(error)")
                } else if success {
                    print("Background delivery enabled for \(sampleType)")
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

                // New data available - schedule a sync
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

    /// Schedule a background sync task
    func scheduleBackgroundSync() {
        let request = BGProcessingTaskRequest(identifier: Self.healthSyncTaskId)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false

        // Schedule for at least 15 minutes from now
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)

        do {
            try BGTaskScheduler.shared.submit(request)
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
                    return
                }

                // Perform sync
                _ = try await HealthKitManager.shared.syncHealthData()
                print("Background sync completed successfully")
                task.setTaskCompleted(success: true)
            } catch {
                print("Background sync failed: \(error)")
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

    /// Call when app becomes active (good time to sync)
    func applicationDidBecomeActive() {
        // Sync when app becomes active if authenticated
        if KeychainManager.shared.getAPIToken() != nil {
            Task {
                do {
                    _ = try await HealthKitManager.shared.syncHealthData()
                    print("Foreground sync completed")
                } catch {
                    print("Foreground sync failed: \(error)")
                }
            }
        }
    }
}
