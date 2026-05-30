import SwiftUI

@main
struct EB1AApp: App {
    @StateObject private var watcher = BulletinWatcher()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(watcher)
        }
    }
}
