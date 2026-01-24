// HealthMetric.swift
// Whole Life Journey iOS App
//
// Data model for health metrics to be synced to the server.

import Foundation

/// A health metric to be sent to the WLJ API.
/// Supports multiple metric types with different fields.
struct HealthMetric: Codable {
    let type: String
    let date: String
    let source: String
    let syncId: String

    // Steps
    var value: Double?

    // Weight
    var unit: String?

    // Sleep
    var totalMinutes: Int?
    var deepMinutes: Int?
    var remMinutes: Int?
    var lightMinutes: Int?
    var awakeMinutes: Int?
    var bedtime: String?
    var wakeTime: String?

    // Heart Rate
    var restingHR: Int?
    var avgHR: Int?
    var maxHR: Int?
    var minHR: Int?

    // Blood Glucose
    var glucoseValue: Double?
    var glucoseUnit: String?

    // Blood Oxygen
    var spo2Value: Int?

    // Water Intake
    var waterAmount: Double?
    var waterUnit: String?

    // Active Calories
    var caloriesValue: Int?

    // Distance
    var distanceValue: Double?
    var distanceUnit: String?

    // Resting Calories (Basal Energy)
    var restingCaloriesValue: Int?

    // Flights Climbed
    var flightsValue: Int?

    // Exercise Minutes
    var exerciseMinutesValue: Int?

    // Stand Hours
    var standHoursValue: Int?

    // Body Fat Percentage
    var bodyFatPercentage: Double?

    // Workout
    var workoutType: String?
    var workoutDuration: Int?
    var workoutCalories: Int?
    var workoutDistance: Double?
    var workoutStartTime: String?
    var workoutEndTime: String?

    // Lean Body Mass
    var leanMassValue: Double?
    var leanMassUnit: String?

    // Respiratory Rate
    var respiratoryRate: Double?

    // Heart Rate Variability (HRV)
    var hrvValue: Double?

    // VO2 Max
    var vo2MaxValue: Double?

    // Caffeine
    var caffeineValue: Double?

    // Mindful Minutes
    var mindfulMinutesValue: Int?

    // Blood Pressure
    var systolicValue: Int?
    var diastolicValue: Int?
    var recordedAt: String?

    // Body Temperature
    var temperatureValue: Double?
    var temperatureUnit: String?

    enum CodingKeys: String, CodingKey {
        case type
        case date
        case source
        case syncId = "sync_id"
        case value
        case unit
        case totalMinutes = "total_minutes"
        case deepMinutes = "deep_minutes"
        case remMinutes = "rem_minutes"
        case lightMinutes = "light_minutes"
        case awakeMinutes = "awake_minutes"
        case bedtime
        case wakeTime = "wake_time"
        case restingHR = "resting_hr"
        case avgHR = "avg_hr"
        case maxHR = "max_hr"
        case minHR = "min_hr"
        case glucoseValue = "glucose_value"
        case glucoseUnit = "glucose_unit"
        case spo2Value = "spo2_value"
        case waterAmount = "water_amount"
        case waterUnit = "water_unit"
        case caloriesValue = "calories_value"
        case distanceValue = "distance_value"
        case distanceUnit = "distance_unit"
        case restingCaloriesValue = "resting_calories_value"
        case flightsValue = "flights_value"
        case exerciseMinutesValue = "exercise_minutes_value"
        case standHoursValue = "stand_hours_value"
        case bodyFatPercentage = "body_fat_percentage"
        case workoutType = "workout_type"
        case workoutDuration = "workout_duration"
        case workoutCalories = "workout_calories"
        case workoutDistance = "workout_distance"
        case workoutStartTime = "workout_start_time"
        case workoutEndTime = "workout_end_time"
        case leanMassValue = "lean_mass_value"
        case leanMassUnit = "lean_mass_unit"
        case respiratoryRate = "respiratory_rate"
        case hrvValue = "hrv_value"
        case vo2MaxValue = "vo2_max_value"
        case caffeineValue = "caffeine_value"
        case mindfulMinutesValue = "mindful_minutes_value"
        case systolicValue = "systolic_value"
        case diastolicValue = "diastolic_value"
        case recordedAt = "recorded_at"
        case temperatureValue = "temperature_value"
        case temperatureUnit = "temperature_unit"
    }

    // MARK: - Convenience Initializers

    /// Create a steps metric
    init(type: String, date: String, value: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.value = Double(value)
        self.source = source
        self.syncId = syncId
    }

    /// Create a weight metric
    init(type: String, date: String, value: Double, unit: String, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.value = value
        self.unit = unit
        self.source = source
        self.syncId = syncId
    }

    /// Create a sleep metric
    init(type: String, date: String, totalMinutes: Int, deepMinutes: Int?, remMinutes: Int?,
         lightMinutes: Int?, awakeMinutes: Int?, bedtime: String?, wakeTime: String?,
         source: String, syncId: String) {
        self.type = type
        self.date = date
        self.totalMinutes = totalMinutes
        self.deepMinutes = deepMinutes
        self.remMinutes = remMinutes
        self.lightMinutes = lightMinutes
        self.awakeMinutes = awakeMinutes
        self.bedtime = bedtime
        self.wakeTime = wakeTime
        self.source = source
        self.syncId = syncId
    }

    /// Create a heart rate metric
    init(type: String, date: String, restingHR: Int?, avgHR: Int? = nil, maxHR: Int? = nil,
         minHR: Int? = nil, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.restingHR = restingHR
        self.avgHR = avgHR
        self.maxHR = maxHR
        self.minHR = minHR
        self.source = source
        self.syncId = syncId
    }

    /// Create a blood glucose metric
    init(type: String, date: String, glucoseValue: Double, glucoseUnit: String,
         source: String, syncId: String) {
        self.type = type
        self.date = date
        self.glucoseValue = glucoseValue
        self.glucoseUnit = glucoseUnit
        self.source = source
        self.syncId = syncId
    }

    /// Create a blood oxygen metric
    init(type: String, date: String, spo2Value: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.spo2Value = spo2Value
        self.source = source
        self.syncId = syncId
    }

    /// Create a water intake metric
    init(type: String, date: String, waterAmount: Double, waterUnit: String,
         source: String, syncId: String) {
        self.type = type
        self.date = date
        self.waterAmount = waterAmount
        self.waterUnit = waterUnit
        self.source = source
        self.syncId = syncId
    }

    /// Create an active calories metric
    init(type: String, date: String, caloriesValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.caloriesValue = caloriesValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a distance metric
    init(type: String, date: String, distanceValue: Double, distanceUnit: String,
         source: String, syncId: String) {
        self.type = type
        self.date = date
        self.distanceValue = distanceValue
        self.distanceUnit = distanceUnit
        self.source = source
        self.syncId = syncId
    }

    /// Create a resting calories metric
    init(type: String, date: String, restingCaloriesValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.restingCaloriesValue = restingCaloriesValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a flights climbed metric
    init(type: String, date: String, flightsValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.flightsValue = flightsValue
        self.source = source
        self.syncId = syncId
    }

    /// Create an exercise minutes metric
    init(type: String, date: String, exerciseMinutesValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.exerciseMinutesValue = exerciseMinutesValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a stand hours metric
    init(type: String, date: String, standHoursValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.standHoursValue = standHoursValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a body fat percentage metric
    init(type: String, date: String, bodyFatPercentage: Double, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.bodyFatPercentage = bodyFatPercentage
        self.source = source
        self.syncId = syncId
    }

    /// Create a workout metric
    init(type: String, date: String, workoutType: String, workoutDuration: Int,
         workoutCalories: Int?, workoutDistance: Double?, workoutStartTime: String,
         workoutEndTime: String, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.workoutType = workoutType
        self.workoutDuration = workoutDuration
        self.workoutCalories = workoutCalories
        self.workoutDistance = workoutDistance
        self.workoutStartTime = workoutStartTime
        self.workoutEndTime = workoutEndTime
        self.source = source
        self.syncId = syncId
    }

    /// Create a lean body mass metric
    init(type: String, date: String, leanMassValue: Double, leanMassUnit: String,
         source: String, syncId: String) {
        self.type = type
        self.date = date
        self.leanMassValue = leanMassValue
        self.leanMassUnit = leanMassUnit
        self.source = source
        self.syncId = syncId
    }

    /// Create a respiratory rate metric
    init(type: String, date: String, respiratoryRate: Double, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.respiratoryRate = respiratoryRate
        self.source = source
        self.syncId = syncId
    }

    /// Create an HRV metric
    init(type: String, date: String, hrvValue: Double, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.hrvValue = hrvValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a VO2 Max metric
    init(type: String, date: String, vo2MaxValue: Double, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.vo2MaxValue = vo2MaxValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a caffeine metric
    init(type: String, date: String, caffeineValue: Double, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.caffeineValue = caffeineValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a mindful minutes metric
    init(type: String, date: String, mindfulMinutesValue: Int, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.mindfulMinutesValue = mindfulMinutesValue
        self.source = source
        self.syncId = syncId
    }

    /// Create a blood pressure metric
    init(type: String, date: String, systolicValue: Int, diastolicValue: Int,
         recordedAt: String, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.systolicValue = systolicValue
        self.diastolicValue = diastolicValue
        self.recordedAt = recordedAt
        self.source = source
        self.syncId = syncId
    }

    /// Create a body temperature metric
    init(type: String, date: String, temperatureValue: Double, temperatureUnit: String,
         recordedAt: String, source: String, syncId: String) {
        self.type = type
        self.date = date
        self.temperatureValue = temperatureValue
        self.temperatureUnit = temperatureUnit
        self.recordedAt = recordedAt
        self.source = source
        self.syncId = syncId
    }
}
