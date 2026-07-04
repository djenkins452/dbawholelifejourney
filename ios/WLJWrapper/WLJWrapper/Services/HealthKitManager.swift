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

        // BMI (Body Mass Index)
        if let bmiType = HKQuantityType.quantityType(forIdentifier: .bodyMassIndex) {
            types.insert(bmiType)
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

        // Blood Pressure (authorize constituent quantity types — NOT the correlation
        // type, which causes requestAuthorization to hang on some iOS versions)
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

        // -- Extended HealthKit Types (Mobility, HR Events, Audio, Nutrition) --

        // Mobility / Gait metrics
        if let asymmetryType = HKQuantityType.quantityType(forIdentifier: .walkingAsymmetryPercentage) {
            types.insert(asymmetryType)
        }
        if let speedType = HKQuantityType.quantityType(forIdentifier: .walkingSpeed) {
            types.insert(speedType)
        }
        if let stepLengthType = HKQuantityType.quantityType(forIdentifier: .walkingStepLength) {
            types.insert(stepLengthType)
        }
        if let doubleSupportType = HKQuantityType.quantityType(forIdentifier: .walkingDoubleSupportPercentage) {
            types.insert(doubleSupportType)
        }
        if let stairAscentType = HKQuantityType.quantityType(forIdentifier: .stairAscentSpeed) {
            types.insert(stairAscentType)
        }
        if let stairDescentType = HKQuantityType.quantityType(forIdentifier: .stairDescentSpeed) {
            types.insert(stairDescentType)
        }
        if let sixMinWalkType = HKQuantityType.quantityType(forIdentifier: .sixMinuteWalkTestDistance) {
            types.insert(sixMinWalkType)
        }

        // Heart rate events (category types)
        if let highHRType = HKCategoryType.categoryType(forIdentifier: .highHeartRateEvent) {
            types.insert(highHRType)
        }
        if let lowHRType = HKCategoryType.categoryType(forIdentifier: .lowHeartRateEvent) {
            types.insert(lowHRType)
        }
        if let irregularType = HKCategoryType.categoryType(forIdentifier: .irregularHeartRhythmEvent) {
            types.insert(irregularType)
        }

        // Audio exposure
        if let headphoneType = HKQuantityType.quantityType(forIdentifier: .headphoneAudioExposure) {
            types.insert(headphoneType)
        }
        if let environmentalType = HKQuantityType.quantityType(forIdentifier: .environmentalAudioExposure) {
            types.insert(environmentalType)
        }

        // Dietary nutrients (macros + key micros)
        if let energyType = HKQuantityType.quantityType(forIdentifier: .dietaryEnergyConsumed) {
            types.insert(energyType)
        }
        if let proteinType = HKQuantityType.quantityType(forIdentifier: .dietaryProtein) {
            types.insert(proteinType)
        }
        if let carbsType = HKQuantityType.quantityType(forIdentifier: .dietaryCarbohydrates) {
            types.insert(carbsType)
        }
        if let fatType = HKQuantityType.quantityType(forIdentifier: .dietaryFatTotal) {
            types.insert(fatType)
        }
        if let fiberType = HKQuantityType.quantityType(forIdentifier: .dietaryFiber) {
            types.insert(fiberType)
        }
        if let sugarType = HKQuantityType.quantityType(forIdentifier: .dietarySugar) {
            types.insert(sugarType)
        }
        if let sodiumType = HKQuantityType.quantityType(forIdentifier: .dietarySodium) {
            types.insert(sodiumType)
        }
        if let cholesterolType = HKQuantityType.quantityType(forIdentifier: .dietaryCholesterol) {
            types.insert(cholesterolType)
        }
        if let satFatType = HKQuantityType.quantityType(forIdentifier: .dietaryFatSaturated) {
            types.insert(satFatType)
        }
        if let potassiumType = HKQuantityType.quantityType(forIdentifier: .dietaryPotassium) {
            types.insert(potassiumType)
        }
        if let calciumType = HKQuantityType.quantityType(forIdentifier: .dietaryCalcium) {
            types.insert(calciumType)
        }
        if let ironType = HKQuantityType.quantityType(forIdentifier: .dietaryIron) {
            types.insert(ironType)
        }
        if let vitDType = HKQuantityType.quantityType(forIdentifier: .dietaryVitaminD) {
            types.insert(vitDType)
        }

        // Walking steadiness (requires iOS 15+, Apple Watch Series 4+)
        if #available(iOS 15.0, *) {
            if let steadinessType = HKQuantityType.quantityType(forIdentifier: .appleWalkingSteadiness) {
                types.insert(steadinessType)
            }
            if let steadinessEventType = HKCategoryType.categoryType(forIdentifier: .appleWalkingSteadinessEvent) {
                types.insert(steadinessEventType)
            }
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

        // Timeout guard: authorization must complete within 60 seconds.
        // Prevents indefinite hang if HealthKit callback never fires.
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                try await self.healthStore.requestAuthorization(toShare: [], read: self.readTypes)
            }
            group.addTask {
                try await Task.sleep(nanoseconds: 60_000_000_000) // 60 seconds
                throw HealthKitError.authorizationTimeout
            }
            // First to complete wins; cancel the other
            try await group.next()
            group.cancelAll()
        }
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
        let bmi = try await fetchBMI(from: startDate, to: endDate)
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
        metrics.append(contentsOf: bmi)
        metrics.append(contentsOf: respiratoryRate)
        metrics.append(contentsOf: hrv)
        metrics.append(contentsOf: vo2Max)
        metrics.append(contentsOf: caffeine)
        metrics.append(contentsOf: mindfulMinutes)
        metrics.append(contentsOf: bloodPressure)
        metrics.append(contentsOf: bodyTemperature)

        // Extended HealthKit types
        let walkingAsymmetry = try await fetchWalkingAsymmetry(from: startDate, to: endDate)
        let walkingSteadiness = try await fetchWalkingSteadiness(from: startDate, to: endDate)
        let walkingSpeed = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .walkingSpeed, unit: HKUnit.mile().unitDivided(by: .hour()), metricType: "walking_speed", fieldName: "walking_speed", syncPrefix: "walkspeed")
        let stepLength = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .walkingStepLength, unit: .inch(), metricType: "step_length", fieldName: "step_length", syncPrefix: "steplength")
        let doubleSupport = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .walkingDoubleSupportPercentage, unit: .percent(), metricType: "double_support_time", fieldName: "double_support_time", syncPrefix: "doublesupport", multiplyBy100: true)
        let stairAscent = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .stairAscentSpeed, unit: HKUnit.meter().unitDivided(by: .second()), metricType: "stair_ascent_speed", fieldName: "stair_ascent_speed", syncPrefix: "stairascent")
        let stairDescent = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .stairDescentSpeed, unit: HKUnit.meter().unitDivided(by: .second()), metricType: "stair_descent_speed", fieldName: "stair_descent_speed", syncPrefix: "stairdescent")
        let sixMinWalk = try await fetchMobilityQuantity(from: startDate, to: endDate, identifier: .sixMinuteWalkTestDistance, unit: .meter(), metricType: "six_min_walk", fieldName: "six_min_walk", syncPrefix: "6minwalk")
        let hrEvents = try await fetchHeartRateEvents(from: startDate, to: endDate)
        let headphoneAudio = try await fetchHeadphoneAudio(from: startDate, to: endDate)
        let environmentalAudio = try await fetchEnvironmentalAudio(from: startDate, to: endDate)
        let dietaryNutrients = try await fetchDietaryNutrients(from: startDate, to: endDate)

        metrics.append(contentsOf: walkingAsymmetry)
        metrics.append(contentsOf: walkingSteadiness)
        metrics.append(contentsOf: walkingSpeed)
        metrics.append(contentsOf: stepLength)
        metrics.append(contentsOf: doubleSupport)
        metrics.append(contentsOf: stairAscent)
        metrics.append(contentsOf: stairDescent)
        metrics.append(contentsOf: sixMinWalk)
        metrics.append(contentsOf: hrEvents)
        metrics.append(contentsOf: headphoneAudio)
        metrics.append(contentsOf: environmentalAudio)
        metrics.append(contentsOf: dietaryNutrients)

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

    // MARK: - Historical Sleep Replay

    /// One-time HISTORICAL SLEEP REPLAY. Normal sync only fetches a rolling 7-day
    /// window, so nights older than a week still reflect whatever importer wrote them.
    /// This re-imports every sleep session in [from, to] through the EXACT SAME pipeline
    /// normal sync uses — `fetchSleep` (session-grouped, wake-dated) →
    /// `APIClient.submitHealthMetrics` → the production server importer. It does NOT
    /// create a separate importer or bypass any production code.
    ///
    /// Idempotent: the server keys each night on sync_id `sleep-<wakeDate>` and
    /// update-or-skips, so an existing night is corrected IN PLACE, nights are never
    /// duplicated, and the replay is safe to re-run if interrupted. A single continuous
    /// `fetchSleep` over the whole range is used deliberately (not per-month chunks) so
    /// that a night straddling any boundary is never re-fragmented.
    func syncSleepHistory(from: Date, to: Date) async throws -> SyncResult {
        let sessions = try await fetchSleep(from: from, to: to)
        guard !sessions.isEmpty else {
            return SyncResult(created: 0, updated: 0, skipped: 0, errors: 0)
        }
        let response = try await APIClient.shared.submitHealthMetrics(sessions)
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

                // Group samples into SLEEP SESSIONS by time-contiguity — NOT by each
                // sample's own end-date. A night crosses midnight (bedtime ~10 PM, wake
                // ~5 AM), so dating each sample by its own local end-date fragments one
                // night across two days: last night's sleep splits into a small pre-
                // midnight record and a post-midnight record, each mis-dated. Instead we
                // walk the (start-sorted) samples and only start a NEW session when there
                // is a real gap (> 60 min) between one sample's end and the next's start
                // (a nap vs the night). Each session is then dated once, by its WAKE
                // (latest end) instant — matching how Apple Health attributes a night.
                let sessionGapSeconds: TimeInterval = 60 * 60
                var sessions: [SleepSession] = []
                var current: SleepSession? = nil
                var currentEnd: Date? = nil

                for sample in (samples as? [HKCategorySample]) ?? [] {
                    if let end = currentEnd,
                       sample.startDate.timeIntervalSince(end) > sessionGapSeconds {
                        if let finished = current { sessions.append(finished) }
                        current = nil
                        currentEnd = nil
                    }
                    if current == nil {
                        current = SleepSession(date: "")
                        current!.bedtime = sample.startDate
                        current!.wakeTime = sample.endDate
                    }

                    // Track the session span (earliest bedtime, latest wake).
                    if current!.bedtime == nil || sample.startDate < current!.bedtime! {
                        current!.bedtime = sample.startDate
                    }
                    if current!.wakeTime == nil || sample.endDate > current!.wakeTime! {
                        current!.wakeTime = sample.endDate
                    }
                    currentEnd = max(currentEnd ?? sample.endDate, sample.endDate)

                    let duration = sample.endDate.timeIntervalSince(sample.startDate) / 60 // minutes

                    // Categorize by sleep stage.
                    switch sample.value {
                    case HKCategoryValueSleepAnalysis.inBed.rawValue:
                        // The "in bed" container overlaps the whole night AND the stage
                        // samples. Counting it would double-count the entire duration
                        // (in bed + core + deep + rem ≈ 2×). Use it only to hold the
                        // session together / define the span — never as sleep minutes.
                        break
                    case HKCategoryValueSleepAnalysis.awake.rawValue:
                        current!.awakeMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepREM.rawValue:
                        current!.remMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue:
                        current!.lightMinutes += Int(duration)
                    case HKCategoryValueSleepAnalysis.asleepDeep.rawValue:
                        current!.deepMinutes += Int(duration)
                    default:
                        // .asleepUnspecified — older / third-party data without stages.
                        current!.totalMinutes += Int(duration)
                    }
                }
                if let finished = current { sessions.append(finished) }

                // Convert sessions to metrics, each dated ONCE by its wake (end) day.
                for session in sessions {
                    guard let wake = session.wakeTime ?? session.bedtime else { continue }
                    let date = dateFormatter.string(from: wake)
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

    // MARK: - Fetch BMI (Body Mass Index)

    private func fetchBMI(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let bmiType = HKQuantityType.quantityType(forIdentifier: .bodyMassIndex) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: bmiType,
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
                var latestPerDay: [String: (date: Date, bmi: Double)] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let bmi = sample.quantity.doubleValue(for: .count())
                    let dateStr = dateFormatter.string(from: sample.startDate)

                    if let existing = latestPerDay[dateStr] {
                        if sample.startDate > existing.date {
                            latestPerDay[dateStr] = (sample.startDate, bmi)
                        }
                    } else {
                        latestPerDay[dateStr] = (sample.startDate, bmi)
                    }
                }

                for (dateStr, data) in latestPerDay {
                    metrics.append(HealthMetric(
                        type: "bmi",
                        date: dateStr,
                        bmiValue: data.bmi,
                        source: "apple_health",
                        syncId: "bmi-\(dateStr)"
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

                    // Average heart rate from workout statistics (iOS 16+)
                    var avgHeartRate: Int? = nil
                    if #available(iOS 16.0, *) {
                        let hrType = HKQuantityType(.heartRate)
                        if let hrStats = workout.statistics(for: hrType),
                           let avgHR = hrStats.averageQuantity() {
                            avgHeartRate = Int(avgHR.doubleValue(for: HKUnit.count().unitDivided(by: .minute())))
                        }
                    }

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
                        workoutAvgHeartRate: avgHeartRate,
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
        guard let bpCorrelationType = HKCorrelationType.correlationType(forIdentifier: .bloodPressure),
              let systolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureSystolic),
              let diastolicType = HKQuantityType.quantityType(forIdentifier: .bloodPressureDiastolic) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)

        // Blood pressure is stored as HKCorrelation — query the correlation type
        let correlations = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<[HKCorrelation], Error>) in
            let query = HKCorrelationQuery(
                type: bpCorrelationType,
                predicate: predicate,
                samplePredicates: nil
            ) { _, results, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: results ?? [])
            }
            healthStore.execute(query)
        }

        // Extract systolic and diastolic from each correlation
        var metrics: [HealthMetric] = []
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let timeFormatter = ISO8601DateFormatter()

        for correlation in correlations {
            guard let systolicSample = correlation.objects(for: systolicType).first as? HKQuantitySample,
                  let diastolicSample = correlation.objects(for: diastolicType).first as? HKQuantitySample else {
                continue
            }

            let systolicValue = Int(systolicSample.quantity.doubleValue(for: .millimeterOfMercury()))
            let diastolicValue = Int(diastolicSample.quantity.doubleValue(for: .millimeterOfMercury()))
            let dateStr = dateFormatter.string(from: correlation.startDate)
            let timeStr = timeFormatter.string(from: correlation.startDate)

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
    // MARK: - Fetch Walking Asymmetry

    private func fetchWalkingAsymmetry(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let asymmetryType = HKQuantityType.quantityType(forIdentifier: .walkingAsymmetryPercentage) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: asymmetryType,
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

                // Average per day
                var dailyReadings: [String: [Double]] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let pct = sample.quantity.doubleValue(for: .percent()) * 100
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    dailyReadings[dateStr, default: []].append(pct)
                }

                for (dateStr, readings) in dailyReadings {
                    let avg = readings.reduce(0, +) / Double(readings.count)
                    metrics.append(HealthMetric(
                        type: "walking_asymmetry",
                        date: dateStr,
                        walkingAsymmetryValue: avg,
                        source: "apple_health",
                        syncId: "walkasym-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Walking Steadiness

    private func fetchWalkingSteadiness(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard #available(iOS 15.0, *),
              let steadinessType = HKQuantityType.quantityType(forIdentifier: .appleWalkingSteadiness) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: steadinessType,
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

                // Most recent per day
                var seenDates: Set<String> = []

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    if seenDates.contains(dateStr) { continue }
                    seenDates.insert(dateStr)

                    let score = sample.quantity.doubleValue(for: .percent()) * 100

                    // Classify: OK (>= 50%), Low (>= 20%), Very Low (< 20%)
                    let classification: String
                    if score >= 50 {
                        classification = "ok"
                    } else if score >= 20 {
                        classification = "low"
                    } else {
                        classification = "very_low"
                    }

                    metrics.append(HealthMetric(
                        type: "walking_steadiness",
                        date: dateStr,
                        walkingSteadinessValue: classification,
                        walkingSteadinessScore: score,
                        source: "apple_health",
                        syncId: "steadiness-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Generic Mobility Quantity

    private func fetchMobilityQuantity(
        from startDate: Date,
        to endDate: Date,
        identifier: HKQuantityTypeIdentifier,
        unit: HKUnit,
        metricType: String,
        fieldName: String,
        syncPrefix: String,
        multiplyBy100: Bool = false,
        convertToFlightsPerMin: Bool = false
    ) async throws -> [HealthMetric] {
        guard let quantityType = HKQuantityType.quantityType(forIdentifier: identifier) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: quantityType,
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

                // Average per day
                var dailyReadings: [String: [Double]] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    var value = sample.quantity.doubleValue(for: unit)
                    if multiplyBy100 { value *= 100 }
                    if convertToFlightsPerMin { value *= 60 } // flights/sec -> flights/min
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    dailyReadings[dateStr, default: []].append(value)
                }

                for (dateStr, readings) in dailyReadings {
                    let avg = readings.reduce(0, +) / Double(readings.count)
                    metrics.append(HealthMetric(
                        type: metricType,
                        date: dateStr,
                        mobilityValue: avg,
                        source: "apple_health",
                        syncId: "\(syncPrefix)-\(dateStr)",
                        fieldName: fieldName
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Heart Rate Events

    private func fetchHeartRateEvents(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        var allMetrics: [HealthMetric] = []

        // Fetch all three event types
        let eventTypes: [(HKCategoryTypeIdentifier, String)] = [
            (.highHeartRateEvent, "high_heart_rate_event"),
            (.lowHeartRateEvent, "low_heart_rate_event"),
            (.irregularHeartRhythmEvent, "irregular_rhythm_event"),
        ]

        for (identifier, metricType) in eventTypes {
            guard let categoryType = HKCategoryType.categoryType(forIdentifier: identifier) else {
                continue
            }

            let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
            let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

            let events: [HealthMetric] = try await withCheckedThrowingContinuation { continuation in
                let query = HKSampleQuery(
                    sampleType: categoryType,
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

                    for sample in (samples as? [HKCategorySample]) ?? [] {
                        let dateStr = dateFormatter.string(from: sample.startDate)
                        let timeStr = isoFormatter.string(from: sample.startDate)
                        let syncId = "\(metricType)-\(Int(sample.startDate.timeIntervalSince1970))"

                        // Duration of event
                        let durationSec = Int(sample.endDate.timeIntervalSince(sample.startDate))

                        // Heart rate threshold from category value (if available)
                        let hrValue = sample.value > 0 ? sample.value : nil

                        metrics.append(HealthMetric(
                            type: metricType,
                            date: dateStr,
                            heartRateValue: hrValue,
                            thresholdValue: nil,
                            durationSeconds: durationSec > 0 ? durationSec : nil,
                            recordedAt: timeStr,
                            source: "apple_health",
                            syncId: syncId
                        ))
                    }

                    continuation.resume(returning: metrics)
                }

                healthStore.execute(query)
            }

            allMetrics.append(contentsOf: events)
        }

        return allMetrics
    }

    // MARK: - Fetch Headphone Audio Exposure

    private func fetchHeadphoneAudio(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let headphoneType = HKQuantityType.quantityType(forIdentifier: .headphoneAudioExposure) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: headphoneType,
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

                // Aggregate per day: average level, total duration
                var dailyLevels: [String: [Double]] = [:]
                var dailyDurations: [String: Double] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let level = sample.quantity.doubleValue(for: .decibelAWeightedSoundPressureLevel())
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    let durationMin = sample.endDate.timeIntervalSince(sample.startDate) / 60

                    dailyLevels[dateStr, default: []].append(level)
                    dailyDurations[dateStr, default: 0] += durationMin
                }

                for (dateStr, levels) in dailyLevels {
                    let avgLevel = levels.reduce(0, +) / Double(levels.count)
                    let totalDuration = Int(dailyDurations[dateStr] ?? 0)

                    metrics.append(HealthMetric(
                        type: "headphone_audio",
                        date: dateStr,
                        headphoneLevelDb: avgLevel,
                        headphoneDurationMinutes: totalDuration > 0 ? totalDuration : nil,
                        source: "apple_health",
                        syncId: "headphone-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Environmental Audio Exposure

    private func fetchEnvironmentalAudio(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        guard let envType = HKQuantityType.quantityType(forIdentifier: .environmentalAudioExposure) else {
            return []
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictEndDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: envType,
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

                // Average per day
                var dailyLevels: [String: [Double]] = [:]

                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    let level = sample.quantity.doubleValue(for: .decibelAWeightedSoundPressureLevel())
                    let dateStr = dateFormatter.string(from: sample.startDate)
                    dailyLevels[dateStr, default: []].append(level)
                }

                for (dateStr, levels) in dailyLevels {
                    let avgLevel = levels.reduce(0, +) / Double(levels.count)
                    metrics.append(HealthMetric(
                        type: "environmental_audio",
                        date: dateStr,
                        environmentalLevelDb: avgLevel,
                        source: "apple_health",
                        syncId: "envaud-\(dateStr)"
                    ))
                }

                continuation.resume(returning: metrics)
            }

            healthStore.execute(query)
        }
    }

    // MARK: - Fetch Dietary Nutrients

    private func fetchDietaryNutrients(from startDate: Date, to endDate: Date) async throws -> [HealthMetric] {
        let interval = DateComponents(day: 1)
        let anchorDate = Calendar.current.startOfDay(for: startDate)
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        // All nutrient types to query
        let nutrientQueries: [(HKQuantityTypeIdentifier, HKUnit, String)] = [
            (.dietaryEnergyConsumed, .kilocalorie(), "calories"),
            (.dietaryProtein, .gram(), "protein"),
            (.dietaryCarbohydrates, .gram(), "carbs"),
            (.dietaryFatTotal, .gram(), "fat"),
            (.dietaryFiber, .gram(), "fiber"),
            (.dietarySugar, .gram(), "sugar"),
            (.dietarySodium, .gramUnit(with: .milli), "sodium"),
            (.dietaryCholesterol, .gramUnit(with: .milli), "cholesterol"),
            (.dietaryFatSaturated, .gram(), "satfat"),
            (.dietaryPotassium, .gramUnit(with: .milli), "potassium"),
            (.dietaryCalcium, .gramUnit(with: .milli), "calcium"),
            (.dietaryIron, .gramUnit(with: .milli), "iron"),
            (.dietaryVitaminD, .gramUnit(with: .micro), "vitd"),
        ]

        // Collect daily totals for each nutrient
        var dailyNutrients: [String: [String: Double]] = [:]

        for (identifier, unit, key) in nutrientQueries {
            guard let quantityType = HKQuantityType.quantityType(forIdentifier: identifier) else {
                continue
            }

            let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)

            let results: [(String, Double)] = try await withCheckedThrowingContinuation { continuation in
                let query = HKStatisticsCollectionQuery(
                    quantityType: quantityType,
                    quantitySamplePredicate: predicate,
                    options: .cumulativeSum,
                    anchorDate: anchorDate,
                    intervalComponents: interval
                )

                query.initialResultsHandler = { _, results, error in
                    if error != nil {
                        // Don't fail the whole sync for missing nutrient types
                        continuation.resume(returning: [])
                        return
                    }

                    var dayValues: [(String, Double)] = []
                    results?.enumerateStatistics(from: startDate, to: endDate) { statistics, _ in
                        if let sum = statistics.sumQuantity() {
                            let value = sum.doubleValue(for: unit)
                            let dateStr = dateFormatter.string(from: statistics.startDate)
                            if value > 0 {
                                dayValues.append((dateStr, value))
                            }
                        }
                    }
                    continuation.resume(returning: dayValues)
                }

                healthStore.execute(query)
            }

            for (dateStr, value) in results {
                if dailyNutrients[dateStr] == nil {
                    dailyNutrients[dateStr] = [:]
                }
                dailyNutrients[dateStr]![key] = value
            }
        }

        // Convert to HealthMetric objects
        var metrics: [HealthMetric] = []
        for (dateStr, nutrients) in dailyNutrients {
            if nutrients.isEmpty { continue }

            metrics.append(HealthMetric(
                type: "dietary_nutrients",
                date: dateStr,
                dietaryCalories: nutrients["calories"].map { Int($0) },
                proteinG: nutrients["protein"],
                carbohydratesG: nutrients["carbs"],
                fatG: nutrients["fat"],
                fiberG: nutrients["fiber"],
                sugarG: nutrients["sugar"],
                sodiumMg: nutrients["sodium"],
                cholesterolMg: nutrients["cholesterol"],
                saturatedFatG: nutrients["satfat"],
                potassiumMg: nutrients["potassium"],
                calciumMg: nutrients["calcium"],
                ironMg: nutrients["iron"],
                vitaminDMcg: nutrients["vitd"],
                source: "apple_health",
                syncId: "nutrients-\(dateStr)"
            ))
        }

        return metrics
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
    case authorizationTimeout

    var errorDescription: String? {
        switch self {
        case .notAvailable:
            return "HealthKit is not available on this device."
        case .notAuthenticated:
            return "Please log in to sync health data."
        case .queryFailed(let message):
            return message
        case .authorizationTimeout:
            return "HealthKit authorization timed out. Please try again or check Settings > Privacy > Health."
        }
    }
}
