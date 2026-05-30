import Foundation
import UserNotifications

/// Owns the live VisaSchedule: fetches release_log.json from the repo, builds
/// the schedule (current cutoff + merged history), caches it for offline use,
/// and fires a local notification when a newer bulletin appears.
///
/// The app never scrapes USCIS/DOS directly — the repo's GitHub Action
/// detector does that and commits release_log.json; this store just consumes it.
@MainActor
final class ScheduleStore: ObservableObject {
    @Published var schedule: VisaSchedule

    private let url = URL(string:
        "https://raw.githubusercontent.com/djzoom/EB1A/main/data/release_log.json")!
    private let cacheKey = "eb1a_schedule_cache"
    private let lastSeenKey = "eb1a_last_seen_bulletin"

    init() {
        if let data = UserDefaults.standard.data(forKey: cacheKey),
           let cached = try? JSONDecoder().decode(VisaSchedule.self, from: data) {
            schedule = cached
        } else {
            schedule = .bundled
        }
    }

    private var lastSeen: String {
        get { UserDefaults.standard.string(forKey: lastSeenKey) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: lastSeenKey) }
    }

    func requestAuthorization() async {
        _ = try? await UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// Fetch the log, rebuild the schedule, cache it, and notify on a newer bulletin.
    func check(notify: Bool) async {
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let entries = try JSONDecoder().decode([ReleaseLogEntry].self, from: data)
            guard let newSchedule = VisaSchedule.from(entries: entries) else { return }

            let previous = lastSeen
            schedule = newSchedule
            if let encoded = try? JSONEncoder().encode(newSchedule) {
                UserDefaults.standard.set(encoded, forKey: cacheKey)
            }

            if newSchedule.bulletinMonth != previous {
                if notify && !previous.isEmpty { await postNotification(newSchedule) }
                lastSeen = newSchedule.bulletinMonth
            }
        } catch {
            // Non-fatal: keep using cached/bundled schedule; retry next foreground.
        }
    }

    private func postNotification(_ s: VisaSchedule) async {
        let content = UNMutableNotificationContent()
        content.title = "📢 新签证公告已发布"
        content.body = "\(monthLabel(s.bulletinMonth)) · 表A \(s.fad) / 表B \(s.dff)"
        content.sound = .default
        let req = UNNotificationRequest(
            identifier: "bulletin-\(s.bulletinMonth)", content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(req)
    }

    /// "2026-07" -> "2026年7月".
    private func monthLabel(_ bulletin: String) -> String {
        let p = bulletin.split(separator: "-")
        guard p.count == 2, let y = Int(p[0]), let m = Int(p[1]) else { return bulletin }
        return "\(y)年\(m)月"
    }
}
