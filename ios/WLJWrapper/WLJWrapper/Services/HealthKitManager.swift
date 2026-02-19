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

        // Active Energy (Calories Burned)
        if let activeEnergyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) {
            types.insert(activeEnergyType)
        }

        // Distance Walking/Running
        if let distanceType = HKQuantityType.quantityType(forIdentifier: .distanceWalkingRunning) {
            types.insert(distanceType)
        }

        // Basal Energy (Resting Calories)
        if let basalEnergyType = HKQuantityType.quantityType(forIdentifier: .basalEnergyBurned) {
            types.insert(basalEnergyType)
        }

        // Flights Climbed
        if let flightsType = HKQuantityType.quantityType(forIdentifier: .flightsClimbed) {
            types.insert(flightsType)
        }

        // Apple Exercise Time (Exercise Minutes)
        if let exerciseType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime) {
            types.insert(exerciseType)
        }

        // Apple Stand Hours
        if let standType = HKQuantityType.quantityType(forIdentifier: .appleStandTime) {
            types.insert(standType)
        }

        // Body Fat Percentage
        if let bodyFatType = HKQuantityType.quantityType(forIdentifier: .bodyFatPercentage) {
            types.insert(bodyFatType)
        }

        // Lean Body Mass
        if let leanMassType = HKQuantityType.quantityType(forIdentifier: .leanBodyMass) {
            types.insert(leanMassType)
        }

        // Respiratory Rate
        if let respRateType = HKQuantityType.quantityType(forIdentifier: .respiratoryRate) {
            types.insert(respRateType)
        }

        // Heart Rate Variability (SDNN)
        if let hrvType = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) {
            types.insert(hrvType)
        }

        // VO2 Max
        if let vo2MaxType = HKQuantityType.quantityType(forIdentifier: .vo2Max) {
            types.insert(vo2MaxType)
        }

        // Caffeine (dietary)
        if let caffeineType = HKQuantityType.quantityType(forIdentifier: .dietaryCaffeine) {
            types.insert(caffeineType)
        }

        // Mindful Minutes (category type, not quantity)
        if let mindfulType = HKCategoryType.categoryType(forIdentifier: .mindfulSession) {
            types.insert(mindfulType)
        }

        // Blood Pressure (systolic and diastolic)
        if let systolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureSystolic) {
            types.insert(systolicType)
        }
        if let diastolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureDiastolic) {
            types.insert(diastolicType)
        }

        // Body Temperature
        if let tempType = HKQuantityType.quantityType(forIdentifier: .bodyTemperature) {
            types.insert(tempType)
        }

        // Workout Sessions
        types.insert(HKObjectType.workoutType())

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
        let activeCalories = try await fetchActiveCalories(from: startDate, to: endDate)
        let distance = try await fetchDistance(from: startDate, to: endDate)
        let restingCalories = try await fetchRestingCalories(from: startDate, to: endDate)
        let flightsClimbed = try await fetchFlightsClimbed(from: startDate, to: endDate)
        let exerciseMinutes = try await fetchExerciseMinutes(from: startDate, to: endDate)
        let standHours = try await fetchStandHours(from: startDate, to: endDate)
        let bodyFat = try await fetchBodyFat(from: startDate, to: endDate)
        let workouts = try await fetchWorkouts(from: startDate, to: endDate)
        let leanMass = try await fetchLeanBodyMass(from: startDate, to: endDate)
        let respiratoryRate = try await fetchRespiratoryRate(from: startDate, to: endDate)
        let hrv = try await fetchHeartRateVariability(from: startDate, to: endDate)
        let vo2Max = try await fetchVO2Max(from: startDate, to: endDate)
        let caffeine = try await fetchCaffeine(from: startDate, to: endDate)
        let mindfulMinutes = try await fetchMindfulMinutes(from: startDate, to: endDate)
        let bloodPressure = try await fetchBloodPressure(from: startDate, to: endDate)
        let bodyTemperature = try await fetchBodyTemperature(from: startDate, to: endDate)

        metrics.append(contentsOf: steps)
        metrics.append(contentsOf: weights)
        metrics.append(contentsOf: sleepData)
        metrics.append(contentsOf: heartRates)
        metrics.append(contentsOf: glucoseReadings)
        metrics.append(contentsOf: oxygenReadings)
        metrics.append(contentsOf: waterIntake)
        metrics.append(contentsOf: activeCalories)
        metrics.append(contentsOf: distance)
        metrics.append(contentsOf: restingCalories)
        metrics.append(contentsOf: flightsClimbed)
        metrics.append(contentsOf: exerciseMinutes)
        metrics.append(contentsOf: standHours)
        metrics.append(contentsOf: bodyFat)
        metrics.append(contentsOf: workouts)
        metrics.append(contentsOf: leanMass)
        metrics.append(contentsOf: respiratoryRate)
        metrics.append(contentsOf: hrv)
        metrics.append(contentsOf: vo2Max)
        metrics.append(contentsOf: caffeine)
        metrics.append(contentsOf: mindfulMinutes)
        metrics.append(contentsOf: bloodPressure)
        metrics.append(contentsOf: bodyTemperature)

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

    // MARK: - Fetch Active Calories

    private func fetchActiveCalories(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let activeEnergyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: activeEnergyType,
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
                        let calories = Int(sum.doubleValue(for: .kilocalorie()))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if calories > 0 {
                            metrics.append(HealthMetric(
                                type: "active_calories",
                                date: dateStr,
                                caloriesValue: calories,
                                source: "apple_health",
                                syncId: "calories-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Distance Walking/Running

    private func fetchDistance(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let distanceType = HKQuantityType.quantityType(forIdentifier: .distanceWalkingRunning) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: distanceType,
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
                        let miles = sum.doubleValue(for: .mile())
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if miles > 0 {
                            metrics.append(HealthMetric(
                                type: "distance",
                                date: dateStr,
                                distanceValue: miles,
                                distanceUnit: "mi",
                                source: "apple_health",
                                syncId: "distance-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Resting Calories (Basal Energy)

    private func fetchRestingCalories(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let basalEnergyType = HKQuantityType.quantityType(forIdentifier: .basalEnergyBurned) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: basalEnergyType,
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
                        let calories = Int(sum.doubleValue(for: .kilocalorie()))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if calories > 0 {
                            metrics.append(HealthMetric(
                                type: "resting_calories",
                                date: dateStr,
                                restingCaloriesValue: calories,
                                source: "apple_health",
                                syncId: "resting-calories-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Flights Climbed

    private func fetchFlightsClimbed(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let flightsType = HKQuantityType.quantityType(forIdentifier: .flightsClimbed) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: flightsType,
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
                        let flights = Int(sum.doubleValue(for: .count()))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if flights > 0 {
                            metrics.append(HealthMetric(
                                type: "flights_climbed",
                                date: dateStr,
                                flightsValue: flights,
                                source: "apple_health",
                                syncId: "flights-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Exercise Minutes

    private func fetchExerciseMinutes(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let exerciseType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: exerciseType,
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
                        let minutes = Int(sum.doubleValue(for: .minute()))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if minutes > 0 {
                            metrics.append(HealthMetric(
                                type: "exercise_minutes",
                                date: dateStr,
                                exerciseMinutesValue: minutes,
                                source: "apple_health",
                                syncId: "exercise-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Stand Hours

    private func fetchStandHours(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let standType = HKQuantityType.quantityType(forIdentifier: .appleStandTime) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: standType,
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
                        // Stand time is in minutes, convert to hours
                        let standMinutes = sum.doubleValue(for: .minute())
                        let standHours = Int(standMinutes / 60)
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if standHours > 0 {
                            metrics.append(HealthMetric(
                                type: "stand_hours",
                                date: dateStr,
                                standHoursValue: standHours,
                                source: "apple_health",
                                syncId: "stand-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Body Fat Percentage

    private func fetchBodyFat(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let bodyFatType = HKQuantityType.quantityType(forIdentifier: .bodyFatPercentage) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: bodyFatType,
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
                let timeFormatter = DateFormatter()
                timeFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"

                // Group by date, keeping most recent per day
                var latestPerDay: [String: (date: Date, percentage: Double)] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let percentage = sample.quantity.doubleValue(for: .percent()) * 100
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if let existing = latestPerDay[dateStr] {
                        if sample.startDate > existing.date {
                            latestPerDay[dateStr] = (sample.startDate, percentage)
                        }
                    } else {
                        latestPerDay[dateStr] = (sample.startDate, percentage)
                    }
                }

                for (dateStr, data) in latestPerDay {
                    metrics.append(HealthMetric(
                        type: "body_fat",
                        date: dateStr,
                        bodyFatPercentage: data.percentage,
                        source: "apple_health",
                        syncId: "bodyfat-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Workouts

    private func fetchWorkouts(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: HKObjectType.workoutType(),
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
                let timeFormatter = ISO8601DateFormatter()

                for workout in (samples as? [HKWorkout]) ?? [] {
                    let dateStr = dateFormatter.string(from: workout.startDate)
                    let startTimeStr = timeFormatter.string(from: workout.startDate)
                    let endTimeStr = timeFormatter.string(from: workout.endDate)

                    // Duration in minutes
                    let durationMinutes = Int(workout.duration / 60)

                    // Calories burned
                    let calories = workout.totalEnergyBurned?.doubleValue(for: .kilocalorie())

                    // Distance (for cardio workouts)
                    let distance = workout.totalDistance?.doubleValue(for: .mile())

                    // Workout type name
                    let workoutType = Self.workoutTypeName(for: workout.workoutActivityType)

                    // Create unique sync ID using start time
                    let syncId = "workout-\(Int(workout.startDate.timeIntervalSince1970))"

                    metrics.append(HealthMetric(
                        type: "workout",
                        date: dateStr,
                        workoutType: workoutType,
                        workoutDuration: durationMinutes,
                        workoutCalories: calories.map { Int($0) },
                        workoutDistance: distance,
                        workoutStartTime: startTimeStr,
                        workoutEndTime: endTimeStr,
                        source: "apple_health",
                        syncId: syncId
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    /// Convert HKWorkoutActivityType to a readable string
    private static func workoutTypeName(for activityType: HKWorkoutActivityType) -> String {
        switch activityType {
        case .americanFootball: return "American Football"
        case .archery: return "Archery"
        case .australianFootball: return "Australian Football"
        case .badminton: return "Badminton"
        case .baseball: return "Baseball"
        case .basketball: return "Basketball"
        case .bowling: return "Bowling"
        case .boxing: return "Boxing"
        case .climbing: return "Climbing"
        case .cricket: return "Cricket"
        case .crossTraining: return "Cross Training"
        case .curling: return "Curling"
        case .cycling: return "Cycling"
        case .dance: return "Dance"
        case .elliptical: return "Elliptical"
        case .equestrianSports: return "Equestrian Sports"
        case .fencing: return "Fencing"
        case .fishing: return "Fishing"
        case .functionalStrengthTraining: return "Functional Strength Training"
        case .golf: return "Golf"
        case .gymnastics: return "Gymnastics"
        case .handball: return "Handball"
        case .hiking: return "Hiking"
        case .hockey: return "Hockey"
        case .hunting: return "Hunting"
        case .lacrosse: return "Lacrosse"
        case .martialArts: return "Martial Arts"
        case .mindAndBody: return "Mind and Body"
        case .paddleSports: return "Paddle Sports"
        case .play: return "Play"
        case .preparationAndRecovery: return "Preparation and Recovery"
        case .racquetball: return "Racquetball"
        case .rowing: return "Rowing"
        case .rugby: return "Rugby"
        case .running: return "Running"
        case .sailing: return "Sailing"
        case .skatingSports: return "Skating Sports"
        case .snowSports: return "Snow Sports"
        case .soccer: return "Soccer"
        case .softball: return "Softball"
        case .squash: return "Squash"
        case .stairClimbing: return "Stair Climbing"
        case .surfingSports: return "Surfing Sports"
        case .swimming: return "Swimming"
        case .tableTennis: return "Table Tennis"
        case .tennis: return "Tennis"
        case .trackAndField: return "Track and Field"
        case .traditionalStrengthTraining: return "Strength Training"
        case .volleyball: return "Volleyball"
        case .walking: return "Walking"
        case .waterFitness: return "Water Fitness"
        case .waterPolo: return "Water Polo"
        case .waterSports: return "Water Sports"
        case .wrestling: return "Wrestling"
        case .yoga: return "Yoga"
        case .barre: return "Barre"
        case .coreTraining: return "Core Training"
        case .crossCountrySkiing: return "Cross Country Skiing"
        case .downhillSkiing: return "Downhill Skiing"
        case .flexibility: return "Flexibility"
        case .highIntensityIntervalTraining: return "HIIT"
        case .jumpRope: return "Jump Rope"
        case .kickboxing: return "Kickboxing"
        case .pilates: return "Pilates"
        case .snowboarding: return "Snowboarding"
        case .stairs: return "Stairs"
        case .stepTraining: return "Step Training"
        case .wheelchairWalkPace: return "Wheelchair Walk Pace"
        case .wheelchairRunPace: return "Wheelchair Run Pace"
        case .taiChi: return "Tai Chi"
        case .mixedCardio: return "Mixed Cardio"
        case .handCycling: return "Hand Cycling"
        case .discSports: return "Disc Sports"
        case .fitnessGaming: return "Fitness Gaming"
        case .cardioDance: return "Cardio Dance"
        case .socialDance: return "Social Dance"
        case .pickleball: return "Pickleball"
        case .cooldown: return "Cooldown"
        case .swimBikeRun: return "Triathlon"
        case .transition: return "Transition"
        case .underwaterDiving: return "Underwater Diving"
        case .danceInspiredTraining: return "Dance"
        case .mixedMetabolicCardioTraining: return "Mixed Cardio"
        case .other: return "Other"
        @unknown default: return "Other"
        }
    }

    // MARK: - Fetch Lean Body Mass

    private func fetchLeanBodyMass(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let leanMassType = HKQuantityType.quantityType(forIdentifier: .leanBodyMass) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: leanMassType,
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

                // Group by date, keeping most recent per day
                var latestPerDay: [String: (date: Date, mass: Double)] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let mass = sample.quantity.doubleValue(for: .pound())
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if let existing = latestPerDay[dateStr] {
                        if sample.startDate > existing.date {
                            latestPerDay[dateStr] = (sample.startDate, mass)
                        }
                    } else {
                        latestPerDay[dateStr] = (sample.startDate, mass)
                    }
                }

                for (dateStr, data) in latestPerDay {
                    metrics.append(HealthMetric(
                        type: "lean_body_mass",
                        date: dateStr,
                        leanMassValue: data.mass,
                        leanMassUnit: "lb",
                        source: "apple_health",
                        syncId: "leanmass-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Heart Rate Variability (HRV)

    private func fetchHeartRateVariability(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let hrvType = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: hrvType,
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

                // Group by date, keeping average per day
                var dailyReadings: [String: [Double]] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    // HRV SDNN is in milliseconds
                    let hrv = sample.quantity.doubleValue(for: HKUnit.secondUnit(with: .milli))
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if dailyReadings[dateStr] == nil {
                        dailyReadings[dateStr] = []
                    }
                    dailyReadings[dateStr]?.append(hrv)
                }

                for (dateStr, readings) in dailyReadings {
                    let avgHrv = readings.reduce(0, +) / Double(readings.count)
                    metrics.append(HealthMetric(
                        type: "hrv",
                        date: dateStr,
                        hrvValue: avgHrv,
                        source: "apple_health",
                        syncId: "hrv-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch VO2 Max

    private func fetchVO2Max(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let vo2MaxType = HKQuantityType.quantityType(forIdentifier: .vo2Max) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: vo2MaxType,
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

                // Group by date, keeping most recent per day (VO2 Max updates infrequently)
                var latestPerDay: [String: (date: Date, value: Double)] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    // VO2 Max is in mL/kg/min
                    let vo2 = sample.quantity.doubleValue(for: HKUnit(from: "mL/kg*min"))
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if let existing = latestPerDay[dateStr] {
                        if sample.startDate > existing.date {
                            latestPerDay[dateStr] = (sample.startDate, vo2)
                        }
                    } else {
                        latestPerDay[dateStr] = (sample.startDate, vo2)
                    }
                }

                for (dateStr, data) in latestPerDay {
                    metrics.append(HealthMetric(
                        type: "vo2_max",
                        date: dateStr,
                        vo2MaxValue: data.value,
                        source: "apple_health",
                        syncId: "vo2max-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Caffeine

    private func fetchCaffeine(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let caffeineType = HKQuantityType.quantityType(forIdentifier: .dietaryCaffeine) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

        // Query daily totals
        let interval = DateComponents(day: 1)
        let query = HKStatisticsCollectionQuery(
            quantityType: caffeineType,
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
                        // Caffeine in milligrams
                        let caffeineMg = sum.doubleValue(for: .gramUnit(with: .milli))
                        let dateStr = dateFormatter.string(from: statistics.startDate)

                        if caffeineMg > 0 {
                            metrics.append(HealthMetric(
                                type: "caffeine",
                                date: dateStr,
                                caffeineValue: caffeineMg,
                                source: "apple_health",
                                syncId: "caffeine-\(dateStr)"
                            ))
                        }
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Mindful Minutes

    private func fetchMindfulMinutes(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let mindfulType = HKCategoryType.categoryType(forIdentifier: .mindfulSession) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: mindfulType,
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

                // Group by date, summing total minutes
                var dailyMinutes: [String: Int] = [:]

                for sample in (samples as? [HKCategorySample]) ?? [] {
                    let duration = sample.endDate.timeIntervalSince(sample.startDate) / 60 // minutes
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    dailyMinutes[dateStr, default: 0] += Int(duration)
                }

                for (dateStr, minutes) in dailyMinutes {
                    if minutes > 0 {
                        metrics.append(HealthMetric(
                            type: "mindful_minutes",
                            date: dateStr,
                            mindfulMinutesValue: minutes,
                            source: "apple_health",
                            syncId: "mindful-\(dateStr)"
                        ))
                    }
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Respiratory Rate

    private func fetchRespiratoryRate(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let respRateType = HKQuantityType.quantityType(forIdentifier: .respiratoryRate) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: respRateType,
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

                // Group by date, keeping average per day
                var dailyReadings: [String: [Double]] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let rate = sample.quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if dailyReadings[dateStr] == nil {
                        dailyReadings[dateStr] = []
                    }
                    dailyReadings[dateStr]?.append(rate)
                }

                for (dateStr, readings) in dailyReadings {
                    let avgRate = readings.reduce(0, +) / Double(readings.count)
                    metrics.append(HealthMetric(
                        type: "respiratory_rate",
                        date: dateStr,
                        respiratoryRate: avgRate,
                        source: "apple_health",
                        syncId: "resprate-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Blood Pressure

    private func fetchBloodPressure(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let systolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureSystolic),
              let diastolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureDiastolic) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        // Fetch systolic readings
        let systolicReadings = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<[HKQuantitySample], Error>) in
            let query = HKSampleQuery(
                sampleType: systolicType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: (samples as? [HKQuantitySample]) ?? [])
            }
            healthStore.execute(query)
        }

        // Fetch diastolic readings
        let diastolicReadings = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<[HKQuantitySample], Error>) in
            let query = HKSampleQuery(
                sampleType: diastolicType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: (samples as? [HKQuantitySample]) ?? [])
            }
            healthStore.execute(query)
        }

        // Match systolic and diastolic readings by timestamp (within 1 minute)
        var metrics: [HealthMetric] = []
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let timeFormatter = ISO8601DateFormatter()

        for systolic in systolicReadings {
            let systolicValue = Int(systolic.quantity.doubleValue(for: .millimeterOfMercury()))
            let systolicTime = systolic.startDate

            // Find matching diastolic reading (within 60 seconds)
            if let diastolic = diastolicReadings.first(where: { abs($0.startDate.timeIntervalSince(systolicTime)) < 60 }) {
                let diastolicValue = Int(diastolic.quantity.doubleValue(for: .millimeterOfMercury()))
                let dateStr = dateFormatter.string(from: systolicTime)
                let timeStr = timeFormatter.string(from: systolicTime)

                metrics.append(HealthMetric(
                    type: "blood_pressure",
                    date: dateStr,
                    systolicValue: systolicValue,
                    diastolicValue: diastolicValue,
                    recordedAt: timeStr,
                    source: "apple_health",
                    syncId: "bp-\(timeStr)"
                ))
            }
        }

        return metrics
    }

    // MARK: - Fetch Body Temperature

    private func fetchBodyTemperature(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let tempType = HKQuantityType.quantityType(forIdentifier: .bodyTemperature) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: tempType,
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
                let timeFormatter = ISO8601DateFormatter()

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    // Temperature in Fahrenheit
                    let tempF = sample.quantity.doubleValue(for: .degreeFahrenheit())
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    let timeStr = timeFormatter.string(from: sample.startDate)

                    metrics.append(HealthMetric(
                        type: "body_temperature",
                        date: dateStr,
                        temperatureValue: tempF,
                        temperatureUnit: "fahrenheit",
                        recordedAt: timeStr,
                        source: "apple_health",
                        syncId: "temp-\(timeStr)"
                    ))
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
