import Foundation

/// Date helpers anchored to a fixed UTC Gregorian calendar so the model is
/// deterministic regardless of device timezone (matches the web app's use of
/// absolute timestamps).
enum EBDate {
    static let utc: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }()

    /// Build a UTC date from year/month/day.
    static func make(_ year: Int, _ month: Int, _ day: Int) -> Date {
        var comps = DateComponents()
        comps.year = year
        comps.month = month
        comps.day = day
        return utc.date(from: comps)!
    }

    /// Parse "YYYY-MM-DD" (or "YYYY-MM") as a UTC date.
    static func parse(_ s: String) -> Date? {
        let parts = s.split(separator: "-").map { Int($0) }
        guard parts.count >= 2, let y = parts[0], let m = parts[1] else { return nil }
        let d = parts.count >= 3 ? (parts[2] ?? 1) : 1
        return make(y, m, d)
    }
}

/// One simulated point: x = calendar month timestamp, y = cutoff timestamp
/// (both in seconds since 1970, matching JS getTime()/1000 semantics — units
/// are consistent throughout the engine so absolute scale is irrelevant).
struct SimPoint {
    var x: TimeInterval
    var y: TimeInterval
}
