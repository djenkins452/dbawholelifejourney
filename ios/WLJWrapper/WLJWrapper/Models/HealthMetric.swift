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
}
