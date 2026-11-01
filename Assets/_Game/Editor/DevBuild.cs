using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace FightingGame.EditorTools
{
    /// <summary>Windows development build into Builds/Windows (git-ignored).</summary>
    public static class DevBuild
    {
        const string Output = "Builds/Windows/FightingGame.exe";

        [MenuItem("Fighting Game/Build Windows (dev)")]
        public static void BuildWindows()
        {
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { SceneBuilder.ScenePath },
                locationPathName = Output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.Development,
            });
            Debug.Log($"[DevBuild] {report.summary.result} → {Output} ({report.summary.totalErrors} errors)");
            if (Application.isBatchMode && report.summary.result != BuildResult.Succeeded) EditorApplication.Exit(1);
        }
    }
}
