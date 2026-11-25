using System.Diagnostics;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static partial class Program
{
    internal static string Language { get; set; } = "en";
    private static Dictionary<string, string>? translations;
    internal static string T(string source)
    {
        if (Language == "es") return source;
        if (translations == null)
        {
            var root = InstalledLayout.ApplicationRoot();
            try { using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "ui", "translations.json"))); translations = doc.RootElement.GetProperty("text").Deserialize<Dictionary<string, string>>()!; }
            catch (Exception error) when (error is IOException or JsonException) { translations = new(); }
        }
        return translations.GetValueOrDefault(source, source);
    }
    internal static void LoadLanguage(string path)
    {
        if (!File.Exists(path)) return;
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        Language = doc.RootElement.TryGetProperty("language", out var value) && value.GetString() == "es" ? "es" : "en";
    }

    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        var languageIndex = Array.IndexOf(args, "--config");
        var languageConfig = languageIndex >= 0 && languageIndex + 1 < args.Length ? args[languageIndex + 1] : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "StageContentManager", "manager.json");
        try { LoadLanguage(languageConfig); } catch (Exception error) when (error is IOException or JsonException) { Language = "en"; }
        using var mutex = new Mutex(true, @"Local\STAGE_CONTENT_MANAGER", out var first);
        if (!first) { MessageBox.Show(Program.T("El gestor ya está abierto."), "ACR Pak Manager"); return; }
        try
        {
            var root = InstalledLayout.ApplicationRoot();
            var configIndex = Array.IndexOf(args, "--config");
            var config = configIndex >= 0 && configIndex + 1 < args.Length ? Path.GetFullPath(args[configIndex + 1]) : Configure(root);
            if (config != null) Application.Run(new ContentWindow(root, config, args.Contains("--no-sync")));
        }
        catch (Exception error) { MessageBox.Show(error.Message, "ACR Pak Manager", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }


}

internal sealed class ContentWindow : Form
{
    private readonly WebView2 browser = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.FromArgb(21, 23, 25) };
    private readonly HttpClient client = new() { Timeout = TimeSpan.FromSeconds(3) };
    private readonly string root, config, data;
    private readonly bool noSync;
    private string origin = "", token = "";
    private Process? worker;
    private bool closing, allowClose;

    public ContentWindow(string root, string config, bool noSync)
    {
        this.root = root; this.config = config; this.noSync = noSync; Program.LoadLanguage(config);
        using var settings = JsonDocument.Parse(File.ReadAllText(config));
        data = settings.RootElement.GetProperty("state").GetString()!;
        Directory.CreateDirectory(data);
        Text = "ACR Pak Manager"; BackColor = Color.FromArgb(21, 23, 25);
        ClientSize = new Size(1240, 850); MinimumSize = new Size(970, 710); StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(browser);
        var iconFile = Path.Combine(root, "ui", "assets", "app.ico");
        if (File.Exists(iconFile)) Icon = new Icon(iconFile);
        Shown += async (_, _) => await Initialize(); FormClosing += OnClosing;
    }

    protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); int dark = 1; DwmSetWindowAttribute(Handle, 20, ref dark, sizeof(int)); }

    private async Task<bool> ReadRuntime()
    {
        var file = Path.Combine(data, "ui-runtime.json"); if (!File.Exists(file)) return false;
        try
        {
            using var document = JsonDocument.Parse(await File.ReadAllTextAsync(file));
            var address = document.RootElement.GetProperty("origin").GetString()!;
            var secret = document.RootElement.GetProperty("token").GetString()!;
            if (!Uri.TryCreate(address, UriKind.Absolute, out var uri) || uri.Scheme != "http" || uri.Host != "127.0.0.1" || uri.UserInfo.Length != 0) return false;
            using var request = new HttpRequestMessage(HttpMethod.Get, address + "/api/state"); request.Headers.Add("X-App-Token", secret);
            using var response = await client.SendAsync(request); if (!response.IsSuccessStatusCode) return false;
            using var state = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            using var expected = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "app_release.json")));
            var expectedName = expected.RootElement.TryGetProperty("name", out var brand) ? brand.GetString() : "ACR Mod Manager";
            if (state.RootElement.GetProperty("app").GetString() != expectedName || state.RootElement.GetProperty("release").GetProperty("version").GetString() != expected.RootElement.GetProperty("version").GetString()) return false;
            origin = address; token = secret; return true;
        }
        catch (Exception error) when (error is IOException or HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException) { return false; }
    }

    private async Task Initialize()
    {
        try
        {
            if (!await ReadRuntime())
            {
                var python = Path.Combine(root, "python", "python.exe");
                if (!File.Exists(python)) throw new IOException(Program.T("Falta el runtime Python independiente del gestor."));
                var start = new ProcessStartInfo(python) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true };
                start.ArgumentList.Add(Path.Combine(root, "wr_content_app.py")); start.ArgumentList.Add("--config"); start.ArgumentList.Add(config);
                if (noSync) start.ArgumentList.Add("--no-sync");
                var logFile = Path.Combine(data, "startup-error.log");
                worker = new Process { StartInfo = start };
                worker.ErrorDataReceived += (_, e) => { if (e.Data != null) try { File.AppendAllText(logFile, e.Data + Environment.NewLine); } catch (IOException) { } };
                if (!worker.Start()) throw new IOException(Program.T("No se pudo iniciar el motor local."));
                worker.BeginErrorReadLine();
                for (int i = 0; i < 60 && !await ReadRuntime(); i++) { if (worker.HasExited) throw new IOException(Program.T("El motor local no pudo iniciarse.")); await Task.Delay(200); }
                if (origin.Length == 0) throw new IOException(Program.T("El motor local no respondió a tiempo."));
            }
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(data, "webview"));
            await browser.EnsureCoreWebView2Async(environment);
            browser.CoreWebView2.Settings.AreDevToolsEnabled = false; browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
            browser.CoreWebView2.NavigationStarting += (_, e) => { if (!e.Uri.StartsWith(origin + "/", StringComparison.Ordinal)) e.Cancel = true; };
            browser.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
            browser.CoreWebView2.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
            browser.CoreWebView2.NavigationCompleted += (_, args) =>
            {
                if (args.IsSuccess) try { InstalledLayout.MarkHealthy(root); } catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException) { }
            };
            browser.CoreWebView2.WebMessageReceived += OnMessage; browser.Source = new Uri(origin + "/#" + token);
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error); allowClose = true; Close(); }
    }

    private async Task<HttpResponseMessage> Post(string path, object body)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, origin + path);
        request.Headers.Add("X-App-Token", token); request.Headers.Add("Origin", origin);
        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        return await client.SendAsync(request);
    }

    private async void OnMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (!e.Source.StartsWith(origin + "/", StringComparison.Ordinal)) return;
        try
        {
            using var document = JsonDocument.Parse(e.WebMessageAsJson); var action = document.RootElement.GetProperty("action").GetString();
            if (action == "language")
            {
                var language = document.RootElement.GetProperty("language").GetString();
                if (language is "en" or "es") Program.Language = language;
                return;
            }
            if (action is "records" or "contact" or "release")
            {
                var address = action switch {
                    "records" => "https://acrsplits.online/",
                    "contact" => "https://discord.com/users/180799704412585984",
                    _ => "https://github.com/Faviogames/ACR-Mod-Manager/releases/latest"
                };
                Process.Start(new ProcessStartInfo(address) { UseShellExecute = true });
                return;
            }
            if (action == "copy-support")
            {
                var text = document.RootElement.GetProperty("text").GetString() ?? "";
                if (text.Length is 0 or > 8192) throw new IOException("Invalid contact template");
                Clipboard.SetText(text);
                browser.CoreWebView2.PostWebMessageAsJson("{\"copied\":true}");
                return;
            }
            string path;
            if (action == "install")
            { using var dialog = new FolderBrowserDialog { Description = Program.T("Selecciona la carpeta con los archivos .pak, .utoc y .ucas del tramo oficial"), UseDescriptionForTitle = true }; if (dialog.ShowDialog(this) != DialogResult.OK) return; path = dialog.SelectedPath; }
            else if (action == "restore")
            { using var dialog = new OpenFileDialog { Title = Program.T("Restaurar respaldo del gestor"), InitialDirectory = Path.Combine(data, "backups"), Filter = Program.T("Diario de respaldo (journal.json)|journal.json") }; if (dialog.ShowDialog(this) != DialogResult.OK) return; path = dialog.FileName; }
            else return;
            using var response = await Post("/api/action", new { action, path });
            browser.CoreWebView2.PostWebMessageAsJson(await response.Content.ReadAsStringAsync());
        }
        catch (Exception error) when (error is IOException or HttpRequestException or JsonException or KeyNotFoundException or ExternalException or System.ComponentModel.Win32Exception)
        { browser.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { error = error.Message })); }
    }

    private async void OnClosing(object? sender, FormClosingEventArgs e)
    {
        if (allowClose) return; e.Cancel = true; if (closing) return; closing = true;
        try
        {
            if (origin.Length > 0)
            {
                using var response = await Post("/api/shutdown", new { });
                if (!response.IsSuccessStatusCode) { MessageBox.Show(this, Program.T("Espera a que termine la operación antes de cerrar."), Text); closing = false; return; }
            }
            if (worker is { HasExited: false }) { using var wait = new CancellationTokenSource(TimeSpan.FromSeconds(5)); await worker.WaitForExitAsync(wait.Token); }
            allowClose = true; browser.Dispose(); client.Dispose(); worker?.Dispose(); Close();
        }
        catch (Exception error) when (error is HttpRequestException or OperationCanceledException)
        { closing = false; MessageBox.Show(this, Program.T("No se confirmó el cierre del motor. Conserva la ventana abierta.") + "\n" + error.Message, Text); }
    }
    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr icon);
}
