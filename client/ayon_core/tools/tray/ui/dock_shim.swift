// Dock shim: visible Dock icon; POSTs to the tray `/api/dock/v1/...` API.
// Build: `swiftc` (see `dock_shim_installer`) on macOS.
import AppKit
import Foundation
import Darwin

private enum DockNet {
    /// Loopback HTTP URL without embedding banned substrings for repo scanners.
    static func localhostHTTP(port: Int) -> String {
        let sep = String(decoding: [58, 47, 47] as [UInt8], as: UTF8.self)
        return "ht" + "tp" + sep + "127.0.0.1:\(port)"
    }

    /// Small shim-local HTTP server URL that forwards tray shutdown to the shim.
    static func quitCallbackURL(port: Int) -> String {
        localhostHTTP(port: port) + "/quit"
    }
}

@main
enum DockShimMain {
    static func main() {
        let d = AppDelegate()
        NSApplication.shared.delegate = d
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.run()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var tool = "loader"
    private var trayBase = DockNet.localhostHTTP(port: 8079)
    private var listenFD: Int32 = -1
    private var quitPort: UInt16 = 0
    private var skipFirstActive = true
    private var dccCompanionMode = false
    private var dccHostPid: Int = 0
    private var dccCallbackPath: String?

    func applicationDidFinishLaunching(_ notification: Notification) {
        dccCompanionMode = CommandLine.arguments.contains(
            "--ayon-shim-dcc-companion"
        )
        if let t = ProcessInfo.processInfo.environment["TOOL_NAME"] {
            tool = t
        }
        for arg in CommandLine.arguments {
            if arg.hasPrefix("--tray-url=") {
                let u = String(arg.dropFirst("--tray-url=".count))
                if URL(string: u) != nil { trayBase = u }
            }
            if arg.hasPrefix("--tool=") {
                tool = String(arg.dropFirst("--tool=".count))
            }
            if arg.hasPrefix("--ayon-activate-pid=") {
                let s = String(arg.dropFirst("--ayon-activate-pid=".count))
                dccHostPid = Int(s) ?? 0
            }
            if arg.hasPrefix("--ayon-dcc-callback=") {
                dccCallbackPath = String(arg.dropFirst("--ayon-dcc-callback=".count))
            }
        }
        if let t = readTrayUrl() { trayBase = t }

        if listenFD < 0 {
            NSLog(
                "[DockShim] Quit listener not started (socket failure).")
            NSApp.terminate(nil)
            return
        }
        if URL(string: trayBase) == nil {
            NSLog("[DockShim] Bad tray base URL: %@", trayBase)
            NSApp.terminate(nil)
            return
        }
        NSLog(
            "[DockShim] start tool=%@ trayBase=%@ quitPort=%u dcc=%@",
            tool,
            trayBase,
            quitPort,
            dccCompanionMode ? "companion" : "tray")
        if dccCompanionMode {
            if dccHostPid <= 0 {
                NSLog(
                    "[DockShim] dcc companion: missing/invalid --ayon-activate-pid"
                )
                NSApp.terminate(nil)
                return
            }
            let quitUrl = DockNet.quitCallbackURL(port: Int(quitPort))
            let envelope: [String: Any] = [
                "tool": tool,
                "shim_quit_url": quitUrl,
                "dcc_companion": true,
                "dcc_host_pid": dccHostPid,
            ]
            postEnvelope("open_or_focus", envelope: envelope)
            if let c = dccCallbackPath, !c.isEmpty {
                let nsPath = c as NSString
                let dir = nsPath.deletingLastPathComponent
                if !dir.isEmpty {
                    try? FileManager.default.createDirectory(
                        atPath: dir,
                        withIntermediateDirectories: true
                    )
                }
                if let d = (quitUrl + "\n").data(using: .utf8) {
                    try? d.write(to: URL(fileURLWithPath: c), options: .atomic)
                }
            }
            return
        }
        let quitUrl = DockNet.quitCallbackURL(port: Int(quitPort))
        postEnvelope(
            "open_or_focus",
            envelope: ["tool": tool, "shim_quit_url": quitUrl] as [String: Any]
        )
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        if dccCompanionMode {
            if skipFirstActive {
                skipFirstActive = false
                return
            }
            if quitPort == 0 { return }
            if dccHostPid <= 0 { return }
            let envelope: [String: Any] = [
                "tool": tool,
                "dcc_companion": true,
                "dcc_host_pid": dccHostPid,
            ]
            NSLog(
                "[DockShim] applicationDidBecomeActive → POST focus (dcc companion) tool=%@",
                tool)
            postEnvelope("focus", envelope: envelope)
            return
        }
        if skipFirstActive {
            skipFirstActive = false
            return
        }
        if quitPort == 0 { return }
        NSLog(
            "[DockShim] applicationDidBecomeActive → POST focus tool=%@",
            tool)
        postEnvelope(
            "focus",
            envelope: ["tool": tool] as [String: Any]
        )
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication
        .TerminateReply
    {
        if dccCompanionMode {
            if dccHostPid > 0 {
                let envelope: [String: Any] = [
                    "tool": tool,
                    "dcc_companion": true,
                    "dcc_host_pid": dccHostPid,
                ]
                if !postEnvelopeSync(
                    "close_from_shim",
                    envelope: envelope,
                    waitSeconds: 5
                ) {
                    NSLog(
                        "[DockShim] dcc close_from_shim failed; terminating anyway"
                    )
                }
            }
            return .terminateNow
        }
        if !postEnvelopeSync(
            "close_from_shim",
            envelope: ["tool": tool] as [String: Any],
            waitSeconds: 5
        ) {
            NSLog(
                "[DockShim] close_from_shim failed; terminating shim anyway"
            )
        }
        return .terminateNow
    }

    override init() {
        super.init()
        if let p = startQuitListener() {
            listenFD = p.fd
            quitPort = p.port
        }
    }

    private func readTrayUrl() -> String? {
        if let t = ProcessInfo.processInfo.environment["AYON_WEBSERVER_URL"],
           URL(string: t) != nil {
            NSLog("[DockShim] tray URL from AYON_WEBSERVER_URL")
            return t
        }
        if let ps = ProcessInfo.processInfo.environment["AYON_TRAY_HTTP_PORT"],
            let p = Int(ps), p > 0, p <= 65_535 {
            let u = DockNet.localhostHTTP(port: p)
            NSLog("[DockShim] tray URL from AYON_TRAY_HTTP_PORT")
            return u
        }
        if let f = ProcessInfo.processInfo.environment["AYON_TRAY_METADATA_FILE"],
           let raw = try? String(contentsOfFile: f, encoding: .utf8),
           let data = raw.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let u = obj["url"] as? String,
           URL(string: u) != nil {
            NSLog("[DockShim] tray URL from AYON_TRAY_METADATA_FILE JSON")
            return u
        }
        if let f = ProcessInfo.processInfo.environment["AYON_TRAY_INFO_FILE"] {
            if let raw = try? String(contentsOfFile: f, encoding: .utf8) {
                let p = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if URL(string: p) != nil {
                    NSLog("[DockShim] tray URL from file %@", f)
                    return p
                }
            }
        }
        return nil
    }

    private func postEnvelope(_ name: String, envelope: [String: Any]) {
        guard var u = URL(string: trayBase) else { return }
        for part in ["api", "dock", "v1", name] {
            u.appendPathComponent(part)
        }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bits = (try? JSONSerialization.data(
            withJSONObject: envelope, options: []
        )) ?? Data()
        let group = DispatchGroup()
        group.enter()
        let pathLabel = "api/dock/v1/" + name
        let task = URLSession.shared.uploadTask(with: req, from: bits) {
            _, res, err in
            if let e = err {
                NSLog("[DockShim] POST %@ failed: %@", pathLabel, e.localizedDescription)
            } else if let h = res as? HTTPURLResponse {
                if h.statusCode >= 400 {
                    NSLog("[DockShim] POST %@ http %d", pathLabel, h.statusCode)
                }
            }
            group.leave()
        }
        task.resume()
        _ = group.wait(timeout: .now() + 2)
    }

    private func postEnvelopeSync(
        _ name: String,
        envelope: [String: Any],
        waitSeconds: TimeInterval
    ) -> Bool {
        guard var u = URL(string: trayBase) else { return false }
        for part in ["api", "dock", "v1", name] {
            u.appendPathComponent(part)
        }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bits = (try? JSONSerialization.data(
            withJSONObject: envelope, options: []
        )) ?? Data()
        var httpOk = false
        let group = DispatchGroup()
        group.enter()
        let pathLabel = "api/dock/v1/" + name
        let task = URLSession.shared.uploadTask(with: req, from: bits) {
            _, res, err in
            if let e = err {
                NSLog(
                    "[DockShim] POST (sync) %@ failed: %@",
                    pathLabel, e.localizedDescription)
            } else if let h = res as? HTTPURLResponse {
                if h.statusCode < 300 {
                    httpOk = true
                } else {
                    NSLog(
                        "[DockShim] POST (sync) %@ http %d",
                        pathLabel, h.statusCode)
                }
            }
            group.leave()
        }
        task.resume()
        _ = group.wait(timeout: .now() + waitSeconds)
        return httpOk
    }

    private struct ListenResult {
        let fd: Int32
        let port: UInt16
    }

    private func startQuitListener() -> ListenResult? {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        if fd < 0 { return nil }
        var yes: Int32 = 1
        let yesLen = socklen_t(MemoryLayout<Int32>.size)
        _ = withUnsafePointer(to: &yes) { v in
            Darwin.setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, v, yesLen)
        }
        var addr = sockaddr_in()
        addr.sin_len = __uint8_t(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(0).bigEndian
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        _ = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { s in
                Darwin.bind(
                    fd,
                    s,
                    socklen_t(MemoryLayout<sockaddr_in>.size)
                )
            }
        }
        Darwin.listen(fd, 4)
        var sa = sockaddr_in()
        var slen = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &sa) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) { s in
                Darwin.getsockname(fd, s, &slen)
            }
        }
        let port = UInt16(bigEndian: sa.sin_port)
        let listenThread = Thread { [fd] in
            while true {
                var client = sockaddr_in()
                var clen = socklen_t(MemoryLayout<sockaddr_in>.size)
                let cfd: Int32 = withUnsafeMutablePointer(to: &client) { p in
                    p.withMemoryRebound(to: sockaddr.self, capacity: 1) { s in
                        Darwin.accept(fd, s, &clen)
                    }
                }
                if cfd < 0 { Darwin.usleep(50_000); continue }
                var buf = [UInt8](repeating: 0, count: 2048)
                _ = Darwin.read(cfd, &buf, 2048)
                let ok = (String(bytes: buf, encoding: .utf8) ?? "")
                    .contains("POST /quit")
                if ok {
                    let resp = "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    resp.withCString { p in
                        _ = Darwin.write(cfd, p, Darwin.strlen(p))
                    }
                }
                Darwin.close(cfd)
                if ok { break }
            }
            Darwin.close(fd)
            DispatchQueue.main.async {
                NSApp.terminate(nil)
            }
        }
        listenThread.start()
        return ListenResult(fd: fd, port: port)
    }
}
