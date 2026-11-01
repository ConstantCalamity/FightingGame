using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
namespace FightingGame.EditorTools {
    public static class NetworkBuildCheck {
        [InitializeOnLoadMethod] static void Schedule() { EditorApplication.delayCall += RunRequested; }
        static void RunRequested() {
            const string request="Temp/network-build.request";
            if(!File.Exists(request)) return;
            if(EditorApplication.isCompiling || EditorApplication.isUpdating) { EditorApplication.delayCall += RunRequested; return; }
            File.Delete(request);
            Directory.CreateDirectory("Logs");
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes=new[]{SceneBuilder.ScenePath}, locationPathName="Builds/Windows/FightingGame.exe",
                target=BuildTarget.StandaloneWindows64, options=BuildOptions.Development
            });
            File.WriteAllText("Logs/network-build-result.txt", report.summary.result+" errors="+report.summary.totalErrors);
        }
    }
}
