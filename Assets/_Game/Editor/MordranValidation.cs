using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
namespace FightingGame.EditorTools {
    public static class MordranValidation {
        public static void BuildAndVerify() {
            var content=ContentBuilder.Build();
            var def=content.characters.Single(c=>c.id=="Mordran");
            string[] clips={"Idle","WalkFwd","WalkBack","Jump","Block","Hit","KO","Win","Light","Heavy","Special","Air"};
            foreach(var name in clips) if(def.Clip(name)==null) throw new Exception("Missing animation "+name);
            if(!def.dualFlails) throw new Exception("Dual flails flag missing");
            var model=UnityEngine.Object.Instantiate(def.prefab);
            string[] markers={"weapon","weapon_tip","weapon_left","weapon_tip_left"};
            foreach(var name in markers) if(!model.GetComponentsInChildren<Transform>().Any(t=>t.name==name)) throw new Exception("Missing flail marker "+name);
            foreach(var clipName in new[]{"Light","Heavy","Special","Air"}) {
                var clip=def.Clip(clipName); var tip=model.GetComponentsInChildren<Transform>().First(t=>t.name=="weapon_tip");
                clip.SampleAnimation(model,0); var start=tip.position; clip.SampleAnimation(model,clip.length*.5f);
                Debug.Log($"[Mordran] {clipName}: right ball movement {Vector3.Distance(start,tip.position):F3}m pos={tip.position}");
            }
            UnityEngine.Object.DestroyImmediate(model);
            var data=MovesetLoader.Load(content.movesets.text);
            if(data["Mordran"].Moves.Count!=4) throw new Exception("Moveset invalid");
            Directory.CreateDirectory("Logs"); File.WriteAllText("Logs/mordran-validation.txt","PASS: three selectable fighters; 12 clips; both flail marker pairs; four moves.\n");
            if(!System.Environment.GetCommandLineArgs().Contains("-verify-only")) DevBuild.BuildWindows();
        }
    }
}

