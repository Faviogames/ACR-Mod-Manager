using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

internal static class InstalledLayout
{
    internal const string AppName="ACR Pak Manager", Executable="ACR Pak Manager.exe";
    // Keep the existing data/install identity so an update does not lose settings or backups.
    internal static string Home=>Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ACRModManager");
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)] static extern bool CreateHardLink(string name,string existing,IntPtr security);
    internal static string ApplicationRoot()
    {
        var directory=Path.GetFullPath(AppContext.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar);
        if(string.Equals(directory,Home,StringComparison.OrdinalIgnoreCase))
        {
            var version=File.ReadAllText(Path.Combine(Home,"current.txt")).Trim();
            if(!Version.TryParse(version,out _))throw new IOException("Invalid installed version");
            var root=Path.Combine(Home,"versions",version);
            if(!File.Exists(Path.Combine(root,"wr_content_app.py")))throw new IOException("Incomplete installed application");
            return root;
        }
        return File.Exists(Path.Combine(directory,"wr_content_app.py"))?directory:Path.GetFullPath(Path.Combine(directory,".."));
    }
    internal static void PublishAlias(string root,string name,string source)
    {
        if(Path.GetFileName(name)!=name||!File.Exists(source))throw new IOException("Invalid launcher");
        var target=Path.Combine(root,name);var temporary=target+".new-"+Guid.NewGuid().ToString("N");
        try{if(!CreateHardLink(temporary,source,IntPtr.Zero))File.Copy(source,temporary);File.Move(temporary,target,true);}
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
    internal static void MarkHealthy(string root)
    {
        var versions=Path.Combine(Home,"versions");
        if(!string.Equals(Directory.GetParent(root)?.FullName,versions,StringComparison.OrdinalIgnoreCase))return;
        var version=Path.GetFileName(root);
        using var manifest=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"app_release.json")));
        if(manifest.RootElement.GetProperty("version").GetString()!=version)return;
        File.WriteAllText(Path.Combine(root,".validated.json"),JsonSerializer.Serialize(new{version}));
        Maintain(root);
    }
    static bool Reparse(string path)=>(File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0;
    static List<string>? PlainFiles(string folder)
    {
        if(Reparse(folder))return null;
        var result=new List<string>();var pending=new Stack<string>();pending.Push(folder);
        while(pending.Count>0)
        foreach(var path in Directory.EnumerateFileSystemEntries(pending.Pop()))
        {
            if(Reparse(path))return null;
            if(Directory.Exists(path))pending.Push(path);else result.Add(Path.GetRelativePath(folder,path).Replace('\\','/'));
        }
        return result;
    }
    static bool OwnedVersion(string folder)
    {
        var index=Path.Combine(folder,".install-files.json");if(!File.Exists(index))return false;
        var files=PlainFiles(folder);if(files==null)return false;
        var known=JsonSerializer.Deserialize<HashSet<string>>(File.ReadAllText(index))!;
        known.Add(".install-files.json");known.Add(".validated.json");
        return files.All(name=>known.Contains(name)||name=="bin/retoc/oo2core_9_win64.dll"||name.Split('/').Contains("__pycache__")&&name.EndsWith(".pyc",StringComparison.OrdinalIgnoreCase));
    }
    internal static void Maintain(string current, string? installHome = null)
    {
        try
        {
            var home=installHome ?? Home;
            var versions=Path.Combine(home,"versions");
            if(!string.Equals(Directory.GetParent(current)?.FullName,versions,StringComparison.OrdinalIgnoreCase)||!File.Exists(Path.Combine(current,".validated.json")))return;
            var currentVersion=Version.Parse(Path.GetFileName(current));
            var older=Directory.EnumerateDirectories(versions).Where(p=>Version.TryParse(Path.GetFileName(p),out var v)&&v<currentVersion&&!Reparse(p)).OrderByDescending(p=>Version.Parse(Path.GetFileName(p))).ToList();
            // Prefer a previous healthy version over a newer installation that never started.
            var previous=older.FirstOrDefault(p=>File.Exists(Path.Combine(p,".validated.json"))) ?? older.FirstOrDefault();
            foreach(var folder in older.Where(p=>p!=previous))if(OwnedVersion(folder)&&string.Equals(Directory.GetParent(Path.GetFullPath(folder))?.FullName,versions,StringComparison.OrdinalIgnoreCase))Directory.Delete(folder,true);
            var legacy=Path.Combine(home,"ACR Mod Manager.exe");
            if(File.Exists(legacy)&&!Reparse(legacy))
            {
                using var stream=File.OpenRead(legacy);var hash=Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();stream.Close();
                if(hash=="e23fea8d181fe84b2936ad9047d9a7df61f5d1198939c83cd5ace383c262ba71")PublishAlias(home,"ACR Mod Manager.exe",Path.Combine(current,"desktop-bin",Executable));
            }
        }
        catch(Exception error) when(error is IOException or UnauthorizedAccessException or JsonException or FormatException){/* Keep recovery data if cleanup cannot be proved safe. */}
    }
}
