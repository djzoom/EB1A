import Foundation
import UserNotifications

/// One entry of data/release_log.json. Unknown keys are ignored by Codable.
struct ReleaseLogEntry: Codable, Equatable {
    let bulletin: String   // "YYYY-MM"
    let fad: String?       // Final Action Date (Table A)
    let dff: String?       // Dates for Filing (Table B)
}

/// Polls the repo's release_log.json and fires a local notification when a
/// newer visa bulletin appears. Foreground-only in M1 (called on launch and
/// whenever the app becomes active); background polling is M2.
@MainActor
final class BulletinWatcher: ObservableObject {
    @Published var latest: ReleaseLogEntry?

    private let url = URL(string:
        "https://raw.githubusercontent.com/djzoom/EB1A/main/data/release_log.json")!
    private let lastSeenKey = "eb1a_last_seen_bulletin"

    private var lastSeen: String {
        get { UserDefaults.standard.string(forKey: lastSeenKey) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: lastSeenKey) }
    }

    /// Request notification permission (call once at launch).
    func requestAuthorization() async {
        _ = try? await UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// Fetch the log; notify on a newer bulletin.
    func check(notify: Bool) async {
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let entries = try JSONDecoder().decode([ReleaseLogEntry].self, from: data)
            guard let newest = entries.max(by: { $0.bulletin < $1.bulletin }) else { return }
            latest = newest

            if newest.bulletin != lastSeen {
                // Don't notify on first-ever run (no baseline to compare).
                if notify && !lastSeen.isEmpty {
                    await postNotification(newest)
                }
                lastSeen = newest.bulletin
            }
        } catch {
            // Network/parse errors are non-fatal; try again next foreground.
        }
    }

    private func postNotification(_ e: ReleaseLogEntry) async {
        let content = UNMutableNotificationContent()
        content.title = "📢 新签证公告已发布"
        let label = monthLabel(e.bulletin)
        var body = "\(label) 公告已更新"
        if let fad = e.fad, let dff = e.dff {
            body = "\(label) · 表A \(fad) / 表B \(dff)"
        }
        content.body = body
        content.sound = .default

        let req = UNNotificationRequest(
            identifier: "bulletin-\(e.bulletin)",
            content: content,
            trigger: nil) // deliver immediately
        try? await UNUserNotificationCenter.current().add(req)
    }

    /// "2026-07" -> "2026年7月".
    private func monthLabel(_ bulletin: String) -> String {
        let parts = bulletin.split(separator: "-")
        guard parts.count == 2, let y = Int(parts[0]), let m = Int(parts[1]) else { return bulletin }
        return "\(y)年\(m)月"
    }
}
