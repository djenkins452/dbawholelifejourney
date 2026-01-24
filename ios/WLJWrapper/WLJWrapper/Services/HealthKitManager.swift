// HealthKitManager.swift
// Whole Life Journey iOS App
//
// Manages HealthKit authorization and data queries.
// Reads steps, weight, sleep, and heart rate for syncing to WLJ.

import Foundation
import HealthKit

class HealthKitManager {
    static let shared = HealthKitManager()

    private let healthStore = HKHealthStore()

    /// Types we want to read from HealthKit
    private let readTypes: Set<HKObjectType> = {
        var types: Set<HKObjectType> = []

        // Steps
        if let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            types.insert(stepType)
        }

        // Weight
        if let weightType = HKQuantityType.quantityType(forIdentifier: .bodyMass) {
            types.insert(weightType)
        }

        // Heart Rate
        if let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate) {
            types.insert(hrType)
        }
        if let restingHRType = HKQuantityType.quantityType(forIdentifier: .restingHeartRate) {
            types.insert(restingHRType)
        }

        // Sleep
        if let sleepType = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) {
            types.insert(sleepType)
        }

        // Blood Glucose (from Dexcom CGM via Apple Health)
        if let glucoseType = HKQuantityType.quantityType(forIdentifier: .bloodGlucose) {
            types.insert(glucoseType)
        }

        // Blood Oxygen (SpO2 from Apple Watch)
        if let oxygenType = HKQuantityType.quantityType(forIdentifier: .oxygenSaturation) {
            types.insert(oxygenType)
        }

        // Dietary Water
        if let waterType = HKQuantityType.quantityType(forIdentifier: .dietaryWater) {
            types.insert(waterType)
        }

        return types
    }()

    var isAuthorized: Bool {
        // Check if HealthKit is available
        guard HKHealthStore.isHealthDataAvailable() else {
            return false
        }

        // Check authorization status for at least one type
        if let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            let status = healthStore.authorizationStatus(for: stepType)
            return status == .sharingAuthorized
        }

        return false
    }

    private init() {}

    // MARK: - Authorization

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw HealthKitError.notAvailable
        }

        try await healthStore.requestAuthorization(toShare: [], read: readTypes)
    }

    // MARK: - Sync Health Data

    func syncHealthData() async throws -> SyncResult {
        guard KeychainManager.shared.getAPIToken() != nil else {
            throw HealthKitError.notAuthenticated
        }

        var metrics: [HealthMetric] = []

        // Get date range: last 7 days
        let calendar = Calendar.current
        let endDate = Date()
        let startDate = calendar.date(byAdding: .day, value: -7, to: endDate)!

        // Fetch all data types
        let steps = try await fetchSteps(from: startDate, to: endDate)
        let weights = try await fetchWeight(from: startDate, to: endDate)
        let sleepData = try await fetchSleep(from: startDate, to: endDate)
        let heartRates = try await fetchHeartRate(from: startDate, to: endDate)
        let glucoseReadings = try await fetchBloodGlucose(from: startDate, to: endDate)
        let oxygenReadings = try await fetchBloodOxygen(from: startDate, to: endDate)
        let waterIntake = try await fetchWaterIntake(from: startDate, to: endDate)

        metrics.append(contentsOf: steps)
        metrics.append(contentsOf: weights)
        metrics.append(contentsOf: sleepData)
        metrics.append(contentsOf: heartRates)
        metrics.append(contentsOf: glucoseReadings)
        metrics.append(contentsOf: oxygenReadings)
        metrics.append(contentsOf: waterIntake)

        if metrics.isEmpty {
            return SyncResult(created: 0, updated: 0, skipped: 0, errors: 0)
        }

        // Submit to API
        let response = try await APIClient.shared.submitHealthMetrics(metrics)

        return SyncResult(
            created: response.created,
            updated: response.updated,
            skipped: response.skipped,
            errors: response.errors.count
        )
    }

    // MARK: - Fetch Steps

    private func fetchSteps(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: stepType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum,
            anchorDate: Calendar.current.startOfDay(for: startDate),
            intervalComponents: interval
        )

        return try await withCheckedThrowingContinuation { continuation in
            query.initialResultsHandler = { _, results, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"

                results?.enumerateStatistics(from: startDate, to: endDate) { statistics, _ in
                    if let sum = statistics.sumQuantity() {
                        let steps = Int(sum.doubleValue(for: .count()))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        metrics.append(HealthMetric(
                            type: "steps",
                            date: dateStr,
                            value: steps,
                            source: "apple_health",
                            syncId: "steps-\(dateStr)"
                        ))
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Weight

    private func fetchWeight(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let weightType = HKQuantityType.quantityType(forIdentifier: .bodyMass) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: weightType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"

                // Group by date, take most recent per day
                var seenDates: Set<String> = []

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    if seenDates.contains(dateStr) { continue }
                    seenDates.insert(dateStr)

                    // Convert to pounds
                    let weightLbs = sample.quantity.doubleValue(for: .pound())

                    metrics.append(HealthMetric(
                        type: "weight",
                        date: dateStr,
                        value: weightLbs,
                        unit: "lb",
                        source: "apple_health",
                        syncId: "weight-\(sample.uuid.uuidString)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Sleep

    private func fetchSleep(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let sleepType = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: sleepType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"
                let isoFormatter = ISO8601DateFormatter()

                // Group samples by sleep session (consecutive samples)
                var sleepSessions: [String: SleepSession] = [:]

                for sample in (samples as? [HKCategorySample]) ?? [] {
                    // Use wake date as the "sleep date"
                    let sleepDate = dateFormatter.string(from: sample.endDate)

                    if sleepSessions[sleepDate] == nil {
                        sleepSessions[sleepDate] = SleepSession(date: sleepDate)
                    }

                    let duration = sample.endDate.timeIntervalSince(sample.startDate) / 60 // minutes

                    // Track earliest bedtime and latest wake time
                    if sleepSessions[sleepDate]!.bedtime == nil ||
                       sample.startDate < sleepSessions[sleepDate]!.bedtime! {
                        sleepSessions[sleepDate]!.bedtime = sample.startDate
                    }
                    if sleepSessions[sleepDate]!.wakeTime == nil ||
                       sample.endDate > sleepSessions[sleepDate]!.wakeTime! {
                        sleepSessions[sleepDate]!.wakeTime = sample.endDate
                    }

                    // Categorize by sleep stage
                    switch sample.value {
                    case HKCategoryValueSleepAnalysis.awake.rawValue:
                        sleepSessions[sleepDate]!.awakeMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepREM.rawValue:
                        sleepSessions[sleepDate]!.remMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue:
                        sleepSessions[sleepDate]!.lightMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepDeep.rawValue:
                        sleepSessions[sleepDate]!.deepMinutes += Int(duration)
                    default:
                        // Generic asleep or in bed
                        sleepSessions[sleepDate]!.totalMinutes += Int(duration)
                    }
                }

                // Convert sessions to metrics
                for (date, session) in sleepSessions {
                    let totalMinutes = session.totalMinutes + session.deepMinutes +
                                      session.remMinutes + session.lightMinutes + session.awakeMinutes

                    if totalMinutes > 0 {
                        metrics.append(HealthMetric(
                            type: "sleep",
                            date: date,
                            totalMinutes: totalMinutes,
                            deepMinutes: session.deepMinutes > 0 ? session.deepMinutes : nil,
                            remMinutes: session.remMinutes > 0 ? session.remMinutes : nil,
                            lightMinutes: session.lightMinutes > 0 ? session.lightMinutes : nil,
                            awakeMinutes: session.awakeMinutes > 0 ? session.awakeMinutes : nil,
                            bedtime: session.bedtime != nil ? isoFormatter.string(from: session.bedtime!) : nil,
                            wakeTime: session.wakeTime != nil ? isoFormatter.string(from: session.wakeTime!) : nil,
                            source: "apple_health",
                            syncId: "sleep-\(date)"
                        ))
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Heart Rate

    private func fetchHeartRate(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let restingHRType = HKQuantityType.quantityType(forIdentifier: .restingHeartRate) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: restingHRType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"

                // Group by date, take most recent per day
                var seenDates: Set<String> = []

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    if seenDates.contains(dateStr) { continue }
                    seenDates.insert(dateStr)

                    let hr = Int(sample.quantity.doubleValue(for: HKUnit(from: "count/min")))

                    metrics.append(HealthMetric(
                        type: "heart_rate",
                        date: dateStr,
                        restingHR: hr,
                        source: "apple_health",
                        syncId: "hr-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Blood Glucose

    private func fetchBloodGlucose(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let glucoseType = HKQuantityType.quantityType(forIdentifier: .bloodGlucose) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: glucoseType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let isoFormatter = ISO8601DateFormatter()

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    // Blood glucose in mg/dL (standard US unit)
                    let glucoseValue = sample.quantity.doubleValue(for: HKUnit(from: "mg/dL"))
                    let timestamp = isoFormatter.string(from: sample.startDate)

                    metrics.append(HealthMetric(
                        type: "blood_glucose",
                        date: timestamp,
                        glucoseValue: glucoseValue,
                        glucoseUnit: "mg/dL",
                        source: "apple_health",
                        syncId: "glucose-\(sample.uuid.uuidString)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Blood Oxygen

    private func fetchBloodOxygen(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let oxygenType = HKQuantityType.quantityType(forIdentifier: .oxygenSaturation) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: oxygenType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let isoFormatter = ISO8601DateFormatter()

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    // Blood oxygen is stored as a percentage (0.0-1.0), convert to %
                    let spo2 = Int(sample.quantity.doubleValue(for: .percent()) * 100)
                    let timestamp = isoFormatter.string(from: sample.startDate)

                    metrics.append(HealthMetric(
                        type: "blood_oxygen",
                        date: timestamp,
                        spo2Value: spo2,
                        source: "apple_health",
                        syncId: "oxygen-\(sample.uuid.uuidString)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Water Intake

    private func fetchWaterIntake(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let waterType = HKQuantityType.quantityType(forIdentifier: .dietaryWater) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: waterType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum,
            anchorDate: Calendar.current.startOfDay(for: startDate),
            intervalComponents: interval
        )

        return try await withCheckedThrowingContinuation { continuation in
            query.initialResultsHandler = { _, results, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                var metrics: [HealthMetric] = []
                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"

                results?.enumerateStatistics(from: startDate, to: endDate) { statistics, _ in
                    if let sum = statistics.sumQuantity() {
                        // Water in fluid ounces
                        let waterOz = sum.doubleValue(for: .fluidOunceUS())
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if waterOz > 0 {
                            metrics.append(HealthMetric(
                                type: "water",
                                date: dateStr,
                                waterAmount: waterOz,
                                waterUnit: "oz",
                                source: "apple_health",
                                syncId: "water-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }
}

// MARK: - Supporting Types

private struct SleepSession {
    let date: String
    var totalMinutes: Int = 0
    var deepMinutes: Int = 0
    var remMinutes: Int = 0
    var lightMinutes: Int = 0
    var awakeMinutes: Int = 0
    var bedtime: Date?
    var wakeTime: Date?
}

enum HealthKitError: LocalizedError {
    case notAvailable
    case notAuthenticated
    case queryFailed(String)

    var errorDescription: String? {
        switch self {
        case .notAvailable:
            return "HealthKit is not available on this device."
        case .notAuthenticated:
            return "Please log in to sync health data."
        case .queryFailed(let message):
            return message
        }
    }
}
