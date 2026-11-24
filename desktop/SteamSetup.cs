using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

internal static partial class Program
{
    static bool ValidStock(string? path) => path != null && File.Exists(Path.Combine(path,"global.utoc")) && File.Exists(Path.Combine(path,"global.ucas")) && File.Exists(Path.GetFullPath(Path.Combine(path,"..","..","..","acr","Binaries","Win64","acr.exe")));

    static List<string> FindSteamGames(string root,string? steam = null)
    {
        var start=new ProcessStartInfo(Path.Combine(root,"python","python.exe")){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
        start.ArgumentList.Add(Path.Combine(root,"wr_content_steam.py"));
        if(steam!=null){start.ArgumentList.Add("--steam-root");start.ArgumentList.Add(steam);}
        try
        {
            using var process=Process.Start(start) ?? throw new IOException("Steam detection could not start");
            var output=process.StandardOutput.ReadToEndAsync();var errors=process.StandardError.ReadToEndAsync();
            if(!process.WaitForExit(15000)){process.Kill();return new();}
            if(process.ExitCode!=0)return new();
            using var data=JsonDocument.Parse(output.GetAwaiter().GetResult());
            return data.RootElement.GetProperty("installations").EnumerateArray().Select(item=>item.GetProperty("game_paks").GetString()!).Where(ValidStock).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        }
        catch(Exception error) when(error is IOException or System.ComponentModel.Win32Exception or JsonException or InvalidOperationException or KeyNotFoundException){return new();}
    }

    static string? ChooseGame(List<string> games)
    {
        if(games.Count==0)return null;if(games.Count==1)return games[0];
        using var window=new Form{Text=T("Selecciona la instalación de ACR"),Width=780,Height=230,StartPosition=FormStartPosition.CenterScreen,MinimizeBox=false,MaximizeBox=false};
        var list=new ListBox{Dock=DockStyle.Fill};foreach(var path in games)list.Items.Add(path);list.SelectedIndex=0;
        var buttons=new FlowLayoutPanel{Dock=DockStyle.Bottom,Height=45,FlowDirection=FlowDirection.RightToLeft};
        var cancel=new Button{Text=T("Cancelar"),DialogResult=DialogResult.Cancel};var ok=new Button{Text=T("Usar esta instalación"),DialogResult=DialogResult.OK,AutoSize=true};
        buttons.Controls.Add(cancel);buttons.Controls.Add(ok);window.Controls.Add(list);window.Controls.Add(buttons);window.AcceptButton=ok;window.CancelButton=cancel;
        return window.ShowDialog()==DialogResult.OK?games[list.SelectedIndex]:null;
    }

    static string? LocateGame(string root)
    {
        var games=FindSteamGames(root);
        if(games.Count>0)return ChooseGame(games);
        using var steam=new FolderBrowserDialog{Description=T("Selecciona la carpeta de Steam; buscaremos ACR en todas sus bibliotecas"),UseDescriptionForTitle=true};
        if(steam.ShowDialog()!=DialogResult.OK)return null;
        games=FindSteamGames(root,steam.SelectedPath);
        if(games.Count>0)return ChooseGame(games);
        if(MessageBox.Show(T("No se ha encontrado ACR en las bibliotecas de Steam. ¿Quieres seleccionar su carpeta manualmente?"),"ACR Pak Manager",MessageBoxButtons.YesNo,MessageBoxIcon.Information)!=DialogResult.Yes)return null;
        using var manual=new FolderBrowserDialog{Description=T("Selecciona la carpeta de Assetto Corsa Rally o su carpeta Paks"),UseDescriptionForTitle=true};
        if(manual.ShowDialog()!=DialogResult.OK)return null;
        var stock=File.Exists(Path.Combine(manual.SelectedPath,"global.utoc"))?manual.SelectedPath:Path.Combine(manual.SelectedPath,"acr","Content","Paks");
        if(!ValidStock(stock))throw new IOException(T("No se encuentran los paks originales de ACR en esa carpeta."));
        return stock;
    }

    static string? Configure(string root)
    {
        var home=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"StageContentManager");
        var path=Path.Combine(home,"manager.json");
        var saved=File.Exists(path)?JsonSerializer.Deserialize<Dictionary<string,JsonElement>>(File.ReadAllText(path))!:new Dictionary<string,JsonElement>();
        var old=saved.TryGetValue("game_paks",out var oldPath)?oldPath.GetString():null;
        var stock=ValidStock(old)?old!:LocateGame(root);if(stock==null)return null;
        stock=Path.GetFullPath(stock);
        var compatibility=JsonSerializer.Deserialize<Dictionary<string,JsonElement>>(File.ReadAllText(Path.Combine(root,"compatibility.json")))!;
        foreach(var pair in compatibility)saved[pair.Key]=pair.Value.Clone();
        void Set(string key,object value)=>saved[key]=JsonSerializer.SerializeToElement(value);
        Set("game_paks",stock);Set("mods",Path.Combine(stock,"~mods"));
        if(!saved.ContainsKey("state"))
        {
            var key=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(stock.ToLowerInvariant())))[..24].ToLowerInvariant();
            Set("state",Path.Combine(home,key));
        }
        if(!saved.TryGetValue("disabled",out var disabled)||!Directory.Exists(disabled.GetString()))Set("disabled",Path.Combine(Directory.GetParent(stock)!.FullName,"StageContentDisabled"));
        if(!saved.ContainsKey("native_cache")||!string.Equals(old,stock,StringComparison.OrdinalIgnoreCase))Set("native_cache",Path.Combine(Directory.GetParent(stock)!.FullName,"StageContentNative"));
        Set("mapping",Path.Combine(root,"bin","acr_stage.usmap"));Set("retoc",Path.Combine(root,"bin","retoc","retoc.exe"));Set("uatool",Path.Combine(root,"bin","uatool","UaTool.exe"));
        if(!saved.ContainsKey("cleanup"))Set("cleanup",new{enabled=true,keep_backups=3,max_backup_mb=512,temp_max_age_hours=24,pinned_journals=Array.Empty<string>()});
        Directory.CreateDirectory(home);File.WriteAllText(path+".tmp",JsonSerializer.Serialize(saved,new JsonSerializerOptions{WriteIndented=true}));File.Move(path+".tmp",path,true);
        return path;
    }
}
