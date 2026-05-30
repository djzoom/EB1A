import Foundation

/// One entry of data/release_log.json. Unknown keys are ignored by Codable.
struct ReleaseLogEntry: Codable, Equatable {
    let bulletin: String   // "YYYY-MM"
    let fad: String?       // Final Action Date (Table A)
    let dff: String?       // Dates for Filing (Table B)
}

/// The live data set the prediction runs on: current cutoffs + merged history.
/// Built from release_log.json (live) merged with VisaData's bundled back-history,
/// and cached to disk so offline launches still have last-known-good data.
struct VisaSchedule: Codable, Equatable {
    var currentCutoffA: Date
    var currentCutoffB: Date
    var historyA: [SimPoint]
    var historyB: [SimPoint]
    var bulletinMonth: String  // latest bulletin "YYYY-MM"
    var fad: String            // latest Table A "YYYY-MM-DD"
    var dff: String            // latest Table B

    /// Bundled fallback (used on first launch with no network/cache).
    static let bundled = VisaSchedule(
        currentCutoffA: VisaData.defaultCutoffA,
        currentCutoffB: VisaData.defaultCutoffB,
        historyA: VisaData.bundledHistoryA,
        historyB: VisaData.bundledHistoryB,
        bulletinMonth: VisaData.defaultBulletin,
        fad: VisaData.defaultFAD,
        dff: VisaData.defaultDFF)

    /// Build a live schedule from release_log entries, merging bundled
    /// back-history for the period before the log begins.
    static func from(entries: [ReleaseLogEntry]) -> VisaSchedule? {
        guard let newest = entries.max(by: { $0.bulletin < $1.bulletin }),
              let cutoffA = EBDate.parse(newest.fad ?? ""),
              let cutoffB = EBDate.parse(newest.dff ?? "") else { return nil }

        // bulletin "YYYY-MM" -> 15th of that month (matches HISTORY convention).
        func bulletinDate(_ b: String) -> Date? {
            let p = b.split(separator: "-")
            guard p.count == 2, let y = Int(p[0]), let m = Int(p[1]) else { return nil }
            return EBDate.make(y, m, 15)
        }

        var liveA: [SimPoint] = []
        var liveB: [SimPoint] = []
        var earliestLive = Date.distantFuture.timeIntervalSince1970
        for e in entries {
            guard let bd = bulletinDate(e.bulletin) else { continue }
            let bx = bd.timeIntervalSince1970
            earliestLive = min(earliestLive, bx)
            if let fad = EBDate.parse(e.fad ?? "") {
                liveA.append(SimPoint(x: bx, y: fad.timeIntervalSince1970))
            }
            if let dff = EBDate.parse(e.dff ?? "") {
                liveB.append(SimPoint(x: bx, y: dff.timeIntervalSince1970))
            }
        }

        // Bundled points strictly before the live window + live points.
        var histA = VisaData.bundledHistoryA.filter { $0.x < earliestLive } + liveA
        var histB = VisaData.bundledHistoryB.filter { $0.x < earliestLive } + liveB
        histA.sort { $0.x < $1.x }
        histB.sort { $0.x < $1.x }

        return VisaSchedule(
            currentCutoffA: cutoffA,
            currentCutoffB: cutoffB,
            historyA: histA,
            historyB: histB,
            bulletinMonth: newest.bulletin,
            fad: newest.fad ?? "",
            dff: newest.dff ?? "")
    }
}
