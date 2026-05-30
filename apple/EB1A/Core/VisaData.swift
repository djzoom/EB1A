import Foundation

/// Static visa-bulletin data ported from index.html. Currently compiled in;
/// M3 will sync these from the repo to match the web app's auto-updates.
enum VisaData {
    /// EB-1A China current Final Action Date (Table A) — CUTOFF_DATA in index.html.
    static let currentCutoffA = EBDate.make(2023, 4, 1)
    /// EB-1A China current Dates for Filing (Table B).
    static let currentCutoffB = EBDate.make(2023, 12, 1)

    /// Latest published bulletin context (VB_* in index.html).
    static let bulletinMonthLabel = "2026年6月"
    static let bulletinReleased = "2026-05-13"
    static let filingChart = "A" // 本月 AOS 递交用表A

    /// Monthly visa allocation weights (FY month 0 = October). MONTHLY_WEIGHTS.
    static let monthlyWeights: [Double] =
        [0.338, 0.183, 0.139, 0.110, 0.057, 0.037, 0.047, 0.017, 0.022, 0.026, 0.020, 0.004]

    /// Historical Table A (Final Action Dates): (bulletin date, cutoff date).
    static let historyA: [SimPoint] = pairs([
        ("2017-10-15", "2017-10-01"), ("2018-10-15", "2016-06-01"), ("2019-10-15", "2016-11-01"),
        ("2020-04-15", "2017-06-08"), ("2020-10-15", "2018-06-01"), ("2021-04-15", "2021-04-01"),
        ("2021-10-15", "2021-10-01"), ("2022-04-15", "2022-04-01"), ("2022-10-15", "2022-10-01"),
        ("2023-01-15", "2022-02-01"), ("2023-04-15", "2022-02-01"), ("2023-10-15", "2022-02-15"),
        ("2024-01-15", "2022-07-01"), ("2024-04-15", "2022-09-01"), ("2024-07-15", "2022-11-01"),
        ("2024-10-15", "2022-11-08"), ("2025-04-15", "2022-11-08"), ("2025-07-15", "2022-11-15"),
        ("2025-10-15", "2022-12-22"), ("2025-12-15", "2023-01-22"), ("2026-01-15", "2023-02-01"),
        ("2026-03-15", "2023-03-15"), ("2026-04-15", "2023-04-01"), ("2026-06-15", "2023-04-01"),
    ])

    /// Historical Table B (Dates for Filing): (bulletin date, cutoff date).
    static let historyB: [SimPoint] = pairs([
        ("2024-10-15", "2022-12-01"), ("2025-04-15", "2023-01-01"), ("2025-07-15", "2023-04-15"),
        ("2025-10-15", "2023-05-15"), ("2025-12-15", "2023-08-01"), ("2026-01-15", "2023-09-15"),
        ("2026-03-15", "2023-11-01"), ("2026-04-15", "2023-12-01"), ("2026-06-15", "2023-12-01"),
    ])

    private static func pairs(_ raw: [(String, String)]) -> [SimPoint] {
        raw.compactMap { (b, c) in
            guard let bx = EBDate.parse(b), let cy = EBDate.parse(c) else { return nil }
            return SimPoint(x: bx.timeIntervalSince1970, y: cy.timeIntervalSince1970)
        }
    }
}
