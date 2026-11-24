using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;

internal static class Program
{
    static readonly string ReleaseVersion = Assembly.GetExecutingAssembly().GetName().Version!.ToString(3);
    static readonly string Home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ACRModManager");
    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            if (args.Length == 2 && args[0] == "--self-test") { SelfTest(Path.GetFullPath(args[1])); return; }
            if (args.Length == 2 && args[0] == "--replace")
            {
                if (!int.TryParse(args[1], out var pid)) throw new IOException("Invalid update process");
                try { using var previous = Process.GetProcessById(pid); if (!previous.WaitForExit(30000)) throw new IOException("Close the running app before updating."); } catch (ArgumentException) { }
            }
            try
            {
                using var running = Mutex.OpenExisting(@"Local\STAGE_CONTENT_MANAGER");
                if (!running.WaitOne(0)) { MessageBox.Show("Close ACR Pak Manager before updating.", "ACR Pak Manager"); return; }
                running.ReleaseMutex();
            }
            catch (WaitHandleCannotBeOpenedException) { }
            using var mutex = new Mutex(true, @"Local\ACR_MOD_MANAGER_LAUNCHER", out var first);
            if (!first) { MessageBox.Show("Close ACR Pak Manager before running the installer again.", "ACR Pak Manager"); return; }
            Directory.CreateDirectory(Home);
            var versionFile = Path.Combine(Home, "current.txt");
            var version = File.Exists(versionFile) ? File.ReadAllText(versionFile).Trim() : "0.0.0";
            if (!Version.TryParse(version, out var installed)) throw new IOException("Invalid installed version");
            if (installed < Version.Parse(ReleaseVersion))
            {
                Install(Home);
                version = ReleaseVersion;
                File.WriteAllText(versionFile + ".tmp", version);
                File.Move(versionFile + ".tmp", versionFile, true);
            }
            var folder = Path.Combine(Home, "versions", version);
            var native = Path.Combine(folder, "desktop-bin", InstalledLayout.Executable);
            var launcher = Path.Combine(Home, InstalledLayout.Executable);
            InstalledLayout.PublishAlias(Home, InstalledLayout.Executable, native);
            Shortcut(launcher);
            var start = new ProcessStartInfo(launcher) { WorkingDirectory = folder, UseShellExecute = false };
            using var app = Process.Start(start) ?? throw new IOException("Could not start ACR Pak Manager.");
            app.WaitForExit();
            InstalledLayout.Maintain(folder);
        }
        catch (Exception error) { MessageBox.Show(error.Message, "ACR Pak Manager", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
    static void Install(string root)
    {
        var target = Path.Combine(root, "versions", ReleaseVersion);
        if (Directory.Exists(target))
        {
            foreach (var file in new[] { "desktop-bin/ACR Pak Manager.exe", "python/python.exe", "wr_content_app.py", "app_release.json" })
                if (!File.Exists(Path.Combine(target, file))) throw new IOException("Existing application version is incomplete; kept for recovery.");
            return;
        }
        var staging = Path.Combine(root, "versions", ".staging-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip") ?? throw new IOException("Missing application payload");
            using var zip = new ZipArchive(stream);
            var entries = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in zip.Entries)
            {
                var name = entry.FullName.Replace('\\', '/');
                if (!entries.Add(name) || name is ".install-files.json" or ".validated.json" || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000) throw new IOException("Invalid or duplicate archive entry");
                var destination = SafeDestination(staging, name);
                if (name.EndsWith('/')) { Directory.CreateDirectory(destination); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                entry.ExtractToFile(destination, false);
            }
            foreach (var file in new[] { "desktop-bin/ACR Pak Manager.exe", "python/python.exe", "wr_content_app.py", "official_database.json", "app_release.json", "ui/index.html", "ui/translations.json", "bin/retoc/retoc.exe", "bin/uatool/UaTool.exe", "bin/acr_stage.usmap" })
                if (!File.Exists(Path.Combine(staging, file))) throw new IOException("Incomplete application payload: " + file);
            // Small native aliases preserve old launcher/shortcut paths; no embedded setup is retained.
            InstalledLayout.PublishAlias(Path.Combine(staging, "desktop-bin"), "ACR Mod Manager.exe", Path.Combine(staging, "desktop-bin", InstalledLayout.Executable));
            entries.Add("desktop-bin/ACR Mod Manager.exe");
            File.WriteAllText(Path.Combine(staging, ".install-files.json"), JsonSerializer.Serialize(entries.Where(name => !name.EndsWith('/'))));
            Directory.Move(staging, target);
        }
        finally { if (Directory.Exists(staging)) Directory.Delete(staging, true); }
    }
    static string SafeDestination(string staging, string name)
    {
        name = name.Replace('\\', '/');
        if (name.StartsWith('/') || name.Split('/').Any(part => part is ".." or ".") || name.Contains(':')) throw new IOException("Unsafe archive path");
        var destination = Path.GetFullPath(Path.Combine(staging, name));
        if (!destination.StartsWith(staging + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new IOException("Unsafe archive path");
        return destination;
    }
    static void Shortcut(string launcher)
    {
        var shellType = Type.GetTypeFromProgID("WScript.Shell"); if (shellType is null) return;
        dynamic shell = Activator.CreateInstance(shellType)!;
        var programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        foreach (var name in new[] { "ACR Pak Manager.lnk", "ACR Mod Manager.lnk" })
        {
            var path = Path.Combine(programs, name);
            if (name == "ACR Mod Manager.lnk" && !File.Exists(path)) continue;
            dynamic shortcut = shell.CreateShortcut(path);
            shortcut.TargetPath = launcher; shortcut.WorkingDirectory = Home;
            shortcut.Description = "ACR Pak Manager — community stages and mods"; shortcut.Save();
        }
    }
    static void SelfTest(string report)
    {
        var root = Path.Combine(Path.GetDirectoryName(report)!, ".install-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "data"));
            foreach (var bad in new[] { "../escape", "a/../../escape", "C:/escape", "/escape", "a\\..\\escape" })
            {
                try { SafeDestination(root, bad); throw new Exception("Unsafe archive accepted"); } catch (IOException) { }
            }
            var saved = Path.Combine(root, "data", "session-test.txt"); File.WriteAllText(saved, "preserved");
            Install(root); Install(root);
            if (File.ReadAllText(saved) != "preserved") throw new IOException("Data lost");
            var folder = Path.Combine(root, "versions", ReleaseVersion);
            var native = Path.Combine(folder, "desktop-bin", InstalledLayout.Executable);
            InstalledLayout.PublishAlias(root, InstalledLayout.Executable, native);
            if (new FileInfo(Path.Combine(root, InstalledLayout.Executable)).Length != new FileInfo(native).Length) throw new IOException("Launcher must be the native app, not the installer payload");
            foreach (var version in new[] { "0.0.1", "0.0.2", "0.0.3" })
            {
                var old = Path.Combine(root, "versions", version); Directory.CreateDirectory(old);
                File.WriteAllText(Path.Combine(old, "owned.txt"), "test");
                File.WriteAllText(Path.Combine(old, ".install-files.json"), "[\"owned.txt\"]");
                if (version == "0.0.2") File.WriteAllText(Path.Combine(old, ".validated.json"), "{}");
            }
            var legacy = Path.Combine(root, "versions", "0.0.0"); Directory.CreateDirectory(legacy);
            File.WriteAllText(Path.Combine(legacy, "unknown.txt"), "keep");
            File.WriteAllText(Path.Combine(folder, ".validated.json"), "{}");
            InstalledLayout.Maintain(folder, root);
            if (!Directory.Exists(Path.Combine(root, "versions", "0.0.2")) || !Directory.Exists(legacy)
                || Directory.Exists(Path.Combine(root, "versions", "0.0.1")) || Directory.Exists(Path.Combine(root, "versions", "0.0.3")))
                throw new IOException("Healthy previous version or unknown legacy files not protected");
            var start = new ProcessStartInfo(Path.Combine(folder, "python", "python.exe")) { WorkingDirectory = folder, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            start.ArgumentList.Add("-c"); start.ArgumentList.Add("import ssl,ctypes,sys,json; from pathlib import Path; from wr_content_catalog import official_catalog; import wr_content_app,wr_content_updates; c=official_catalog(); assert all(k in c for k in ['WrcgKeSS1','WrcgKeSS2','WrcgEsSS1','WrcgEsSS4']); assert 'tools' not in sys.modules; assert not Path('local').exists(); print('PASS standalone Python, TLS, Windows bindings, no exporter core, no private profile and',len(c),'official stage definitions')");
            using var python = Process.Start(start)!; var output = python.StandardOutput.ReadToEnd(); var errors = python.StandardError.ReadToEnd(); python.WaitForExit();
            if (python.ExitCode != 0) throw new IOException(errors);
            File.WriteAllText(report, JsonSerializer.Serialize(new { result = "PASS", version = ReleaseVersion, checks = new[] { "isolated extraction", "idempotent installation", "existing session preserved", "healthy previous version retained", "unknown legacy files protected", output.Trim() } }, Json));
        }
        catch (Exception error) { File.WriteAllText(report, JsonSerializer.Serialize(new { result = "FAIL", error = error.ToString() }, Json)); }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
}
