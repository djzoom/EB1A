import Foundation

/// Chinese-language formatters mirroring formatDate/formatDateFull/formatWait
/// in index.html.
enum Fmt {
    /// "YYYY年M月", or "超过12年" when the crossing never happened.
    static func dateFull(_ ts: TimeInterval?) -> String {
        guard let ts else { return "超过12年" }
        let d = Date(timeIntervalSince1970: ts)
        let c = EBDate.utc.dateComponents([.year, .month], from: d)
        return "\(c.year!)年\(c.month!)月"
    }

    /// "YYYY-MM".
    static func dateShort(_ ts: TimeInterval?) -> String {
        guard let ts else { return "12年+" }
        let d = Date(timeIntervalSince1970: ts)
        let c = EBDate.utc.dateComponents([.year, .month], from: d)
        return "\(c.year!)-" + String(format: "%02d", c.month!)
    }

    /// Human wait time from `from` to the crossing, e.g. "约1年8个月".
    static func wait(_ ts: TimeInterval?, from: Date = Date()) -> String {
        guard let ts else { return "12年+" }
        let diff = (ts - from.timeIntervalSince1970) / (86_400 * 30.44) // months
        if diff < 0 { return "已到" }
        if diff < 1 { return "不到1个月" }
        if diff < 12 { return "约\(Int(diff.rounded()))个月" }
        var y = Int(diff / 12)
        var m = Int((diff - Double(y) * 12).rounded())
        if m >= 12 { y += 1; m = 0 }
        return "约\(y)年" + (m > 0 ? "\(m)个月" : "")
    }
}
