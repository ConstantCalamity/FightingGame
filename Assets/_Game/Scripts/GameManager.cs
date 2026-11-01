using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>
    /// Runs the game: character/stage select, best-of-3 matches, both fighters ticked in order, hitstop and slow-mo,
    /// projectiles, map lighting/effects, camera, HUD and the hitbox debug view.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        enum Phase { Select, Intro, Fight, KO, Between, Over }

        [SerializeField] Material glowTemplate;
        [SerializeField] Camera cam;
        [SerializeField] GameContent content;
        [SerializeField] Material overlayMaterial;

        [Tooltip("Show hurtboxes / hitboxes. Toggle in game with F1 or the on-screen button.")]
        public bool ShowHitboxes;
        [Tooltip("When on, P2 is controlled by the CPU. Toggle in game with 2.")]
        public bool CpuP2 = true;
        public float RoundTime = 60;

        public Fighter P1 { get; private set; }
        public Fighter P2 { get; private set; }

        Dictionary<string, CharacterData> characterData;
        readonly List<Projectile> projectiles = new List<Projectile>();
        HumanInput input1, input2;
        AIController ai2, ai1;
        Effects fx;
        HitboxDebug debugView;
        Sfx sfx;

        Phase phase = Phase.Select;
        float phaseT, timer, clock;
        int round = 1;
        readonly int[] wins = new int[2];
        Fighter winner;
        bool fightShown;
        int pick1, pick2 = 1, pickMap;
        int shown1 = -1, shown2 = -1, shownMap = -1;

        float freeze, shakeAmt, timeScale = 1, slowmoT;
        Vector3 camBase, camLook;

        string bigText = "", subText = "";
        Color bigColor = Color.white;
        float comboHide;
        Fighter comboOwner;

        // stage state
        GameObject mapInstance, trainingArena, trainingSky;
        Light sun;
        readonly List<Light> rimLights = new List<Light>();
        DefaultLighting training;
        struct DefaultLighting
        {
            public Quaternion sunRot; public Color sunColor; public float sunIntensity;
            public Color sky, equator, ground, fog, background; public float fogStart, fogEnd;
        }

        // Automated smoke test: run the player with -autotest to watch CPU vs CPU, screenshot and quit.
        bool autotest;
        string shotPath;
        int shotsTaken;
        bool toggleAfterShot, projectileShot, selectShot, specialTest, bladeShot, parryTest, fireShot;
        Vector3? fireShotTarget;
        int bladeShotFrame;
        float eventShotAt;
        string eventShotTag;
        readonly HashSet<string> eventShotsTaken = new HashSet<string>();

        /// <summary>Autotest: grab a screenshot a couple of frames after a notable event (once per kind).</summary>
        void EventShot(string tag)
        {
            // skip the round intro (the FIGHT! banner covers the fighters) and capture without the hitbox overlay
            if (!autotest || string.IsNullOrEmpty(shotPath) || eventShotsTaken.Contains(tag) || clock < 2.5f) return;
            eventShotsTaken.Add(tag);
            ShowHitboxes = false;
            eventShotTag = tag;
            eventShotAt = Time.unscaledTime + 0.1f;   // let the spark spray open up
        }
        float autotestStart;

        void Awake()
        {
            if (cam == null) cam = Camera.main;
            characterData = MovesetLoader.Load(content.movesets.text);
            StageFX.ParticleMaterial = content.particleTemplate;
            StageFX.FlameMaterial = content.flameMaterial;
            StageFX.SmokeMaterial = content.smokeMaterial;
            input1 = new HumanInput(true);
            input2 = new HumanInput(false);
            ai1 = new AIController();
            ai2 = new AIController();
            fx = new Effects(glowTemplate, content.particleTemplate, cam.transform);
            debugView = new HitboxDebug(overlayMaterial != null ? overlayMaterial : glowTemplate);
            sfx = new Sfx(gameObject);

            trainingArena = GameObject.Find("Arena");
            trainingSky = GameObject.Find("Sky");
            foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None))
            {
                if (l.type == LightType.Directional && l.name == "Sun") sun = l;
                else if (l.name.StartsWith("Rim")) rimLights.Add(l);
            }
            training = new DefaultLighting
            {
                sunRot = sun ? sun.transform.rotation : Quaternion.identity, sunColor = sun ? sun.color : Color.white,
                sunIntensity = sun ? sun.intensity : 1, sky = RenderSettings.ambientSkyColor, equator = RenderSettings.ambientEquatorColor,
                ground = RenderSettings.ambientGroundColor, fog = RenderSettings.fogColor, fogStart = RenderSettings.fogStartDistance,
                fogEnd = RenderSettings.fogEndDistance, background = cam.backgroundColor,
            };

            var args = System.Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "-autotest") autotest = true;
                if (args[i] == "-selectshot") selectShot = true;
                if (args[i] == "-specialtest") specialTest = true;
                if (args[i] == "-fireshot") fireShot = true;
                if (args[i] == "-parrytest") { parryTest = true; ai2.ParryChance = 1f; }
                if (args[i] == "-shot" && i + 1 < args.Length) shotPath = args[i + 1];
                if (args[i] == "-map" && i + 1 < args.Length) int.TryParse(args[i + 1], out pickMap);
                if (args[i] == "-p1" && i + 1 < args.Length) pick1 = IndexOf(args[i + 1]);
                if (args[i] == "-p2" && i + 1 < args.Length) pick2 = IndexOf(args[i + 1]);
            }
            camBase = new Vector3(0, 2.6f, -9);
            camLook = new Vector3(0, 1.2f, 0);
            if (autotest)
            {
                ShowHitboxes = true;
                autotestStart = Time.realtimeSinceStartup;
                BeginMatch();
            }
        }

        int IndexOf(string id)
        {
            for (int i = 0; i < content.characters.Length; i++)
                if (content.characters[i].id == id) return i;
            return 0;
        }

        int MapCount => content.maps.Length + 1;    // + the original training arena
        string MapName(int i) => i < content.maps.Length ? content.maps[i].displayName : "Training Grounds";

        // ---------- Match flow ----------

        void BeginMatch()
        {
            if (P1 == null || pick1 != shown1 || pick2 != shown2) SpawnFighters();
            if (pickMap != shownMap) LoadMap(pickMap);
            wins[0] = wins[1] = 0;
            round = 1;
            StartRound();
        }

        void SpawnFighters()
        {
            if (P1) Destroy(P1.gameObject);
            if (P2) Destroy(P2.gameObject);
            var d1 = content.characters[pick1];
            var d2 = content.characters[pick2];
            P1 = Fighter.Create(this, d1, characterData[d1.id], glowTemplate, "P1_" + d1.id);
            P2 = Fighter.Create(this, d2, characterData[d2.id], glowTemplate, "P2_" + d2.id);
            shown1 = pick1; shown2 = pick2;
        }

        void LoadMap(int index)
        {
            LoadMapContent(index);
            // one realtime reflection capture of the stage so polished steel reflects its surroundings
            var probeGo = new GameObject("StageReflections");
            probeGo.transform.SetParent(mapInstance.transform, false);
            probeGo.transform.position = new Vector3(0, 2.5f, -1.5f);
            var probe = probeGo.AddComponent<ReflectionProbe>();
            probe.mode = ReflectionProbeMode.Realtime;
            probe.refreshMode = ReflectionProbeRefreshMode.ViaScripting;
            probe.timeSlicingMode = ReflectionProbeTimeSlicingMode.NoTimeSlicing;
            probe.size = new Vector3(120, 60, 120);
            probe.resolution = 256;
            probe.hdr = true;
            probe.importance = 1;
            probe.RenderProbe();
        }

        void LoadMapContent(int index)
        {
            shownMap = index;
            if (mapInstance) Destroy(mapInstance);
            bool training_ = index >= content.maps.Length;
            if (trainingArena) trainingArena.SetActive(training_);
            if (trainingSky) trainingSky.SetActive(training_);
            if (training_)
            {
                if (sun) { sun.transform.rotation = training.sunRot; sun.color = training.sunColor; sun.intensity = training.sunIntensity; }
                RenderSettings.ambientSkyColor = training.sky; RenderSettings.ambientEquatorColor = training.equator;
                RenderSettings.ambientGroundColor = training.ground; RenderSettings.fogColor = training.fog;
                RenderSettings.fogStartDistance = training.fogStart; RenderSettings.fogEndDistance = training.fogEnd;
                cam.backgroundColor = training.background;
                foreach (var l in rimLights) l.intensity = 6;
                mapInstance = new GameObject("TrainingFX");
                StageFX.Weather(mapInstance.transform, "embers", new Vector3(0, 1, 2), 0.6f, content.particleTemplate);
                return;
            }
            var map = content.maps[index];
            mapInstance = new GameObject("Map_" + map.displayName);
            // The FBX import maps Blender (x, y, z) to Unity (x, z, y); turning the map 180° gives the
            // (-x, z, -y) layout the maps (and their light/FX markers) were authored for.
            if (map.prefab) Instantiate(map.prefab, mapInstance.transform).transform.localRotation = Quaternion.Euler(0, 180, 0);
            if (sun)
            {
                sun.transform.rotation = Quaternion.Euler(map.sunEuler);
                sun.color = map.sunColor;
                sun.intensity = map.sunIntensity;
            }
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = map.ambientSky;
            RenderSettings.ambientEquatorColor = map.ambientEquator;
            RenderSettings.ambientGroundColor = map.ambientGround;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = map.fogColor;
            RenderSettings.fogStartDistance = map.fogStart;
            RenderSettings.fogEndDistance = map.fogEnd;
            cam.backgroundColor = map.background;
            foreach (var l in rimLights) l.intensity = 4f;
            foreach (var p in map.pointLights)
                StageFX.PointLight(mapInstance.transform, p.position, p.color, p.intensity, p.range, true);
            foreach (var f in map.fx)
            {
                if (f.type == "fire") StageFX.Fire(mapInstance.transform, f.position, f.scale, content.particleTemplate);
                else StageFX.Weather(mapInstance.transform, f.type, f.position, f.scale, content.particleTemplate);
            }
        }

        void StartRound()
        {
            P1.ResetFor(-3, 1);
            P2.ResetFor(3, -1);
            while (projectiles.Count > 0) RemoveProjectile(projectiles[0]);
            phase = Phase.Intro; phaseT = 0; timer = RoundTime; winner = null; fightShown = false;
            timeScale = 1; slowmoT = 0;
            input1.ClearBuffer(); input2.ClearBuffer();
            Announce($"ROUND {round}");
        }

        void Announce(string text, string sub = "", Color? color = null)
        {
            bigText = text; subText = sub; bigColor = color ?? Color.white;
        }

        void UpdateGame(float real)
        {
            phaseT += real;
            switch (phase)
            {
                case Phase.Intro:
                    if (phaseT > 1.2f) { Announce("FIGHT!"); fightShown = true; phase = Phase.Fight; phaseT = 0; }
                    break;
                case Phase.Fight:
                    if (fightShown && phaseT > 0.7f) { Announce(""); fightShown = false; }
                    timer -= real;
                    if (timer <= 0)
                    {
                        timer = 0; phase = Phase.KO; phaseT = 0;
                        winner = Mathf.Approximately(P1.HP, P2.HP) ? null : (P1.HP / P1.Data.Hp > P2.HP / P2.Data.Hp ? P1 : P2);
                        Announce("TIME");
                    }
                    break;
                case Phase.KO:
                    if (phaseT > 2f)
                    {
                        if (winner != null) { wins[winner == P1 ? 0 : 1]++; winner.Celebrate(); }
                        if (wins[0] >= 2 || wins[1] >= 2)
                        {
                            phase = Phase.Over;
                            Announce($"{winner.DisplayName} WINS", "Enter: rematch  ·  Esc: character select");
                        }
                        else
                        {
                            phase = Phase.Between; phaseT = 0;
                            Announce(winner != null ? $"{winner.DisplayName} WINS" : "DRAW");
                        }
                    }
                    break;
                case Phase.Between:
                    if (phaseT > 2.2f) { round++; StartRound(); }
                    break;
            }
        }

        // ---------- Main loop ----------

        void Update()
        {
            float real = Mathf.Min(Time.unscaledDeltaTime, 1f / 20f);
            HandleMetaKeys();
            input1.Poll();
            input2.Poll();

            if (phase == Phase.Select)
            {
                SelectInput();
                // live preview: the picked fighters idle on the picked stage behind the menu
                if (pick1 != shown1 || pick2 != shown2 || P1 == null)
                {
                    SpawnFighters();
                    P1.ResetFor(-1.5f, 1); P2.ResetFor(1.5f, -1);
                }
                if (pickMap != shownMap) LoadMap(pickMap);
                clock += real;
                P1.UpdateVisual(real, real);
                P2.UpdateVisual(real, real);
                UpdateCamera(real, false);
                if (selectShot && Time.frameCount > 30)
                {
                    if (Time.frameCount == 31) ScreenCapture.CaptureScreenshot(shotPath);
                    else if (Time.frameCount > 40) Application.Quit();
                }
                return;
            }

            if (slowmoT > 0) { slowmoT -= real; if (slowmoT <= 0) timeScale = 1; }
            float dt = real * timeScale;
            clock += dt;

            float simDt = 0;
            if (freeze > 0) freeze -= real;
            else
            {
                simDt = dt;
                bool fighting = phase == Phase.Fight;
                if (autotest) ai1.Think(dt, P1, P2, projectiles);
                if (CpuP2) ai2.Think(dt, P2, P1, projectiles);
                IFighterInput in1 = !fighting ? NoInput.Instance : autotest ? ai1 : input1;
                IFighterInput in2 = !fighting ? NoInput.Instance : CpuP2 ? ai2 : input2;
                P1.Tick(dt, in1, P2);
                P2.Tick(dt, in2, P1);
                Separate();
                UpdateProjectiles(dt);
            }

            if (comboHide > 0) comboHide -= real;
            for (int i = popups.Count - 1; i >= 0; i--)
                if ((popups[i].Life -= real) <= 0) popups.RemoveAt(i);
            UpdateGame(real);
            P1.UpdateVisual(simDt, real);
            P2.UpdateVisual(simDt, real);
            if (simDt > 0)
            {
                // sword hitboxes come from the animation just sampled, so resolve melee hits after the visuals
                P1.ResolveHits(P2);
                P2.ResolveHits(P1);
            }
            fx.Tick(dt);
            UpdateCamera(real, false);
            debugView.Tick(ShowHitboxes, P1, P2, projectiles);
            if (autotest) AutotestStep();
        }

        void HandleMetaKeys()
        {
            var kb = Keyboard.current;
            if (kb == null) return;
            if (kb[Key.F1].wasPressedThisFrame) ShowHitboxes = !ShowHitboxes;
            if (kb[Key.Digit2].wasPressedThisFrame) CpuP2 = !CpuP2;
            if (phase == Phase.Select) return;
            if (kb[Key.R].wasPressedThisFrame) { wins[0] = wins[1] = 0; round = 1; StartRound(); }
            if (kb[Key.Escape].wasPressedThisFrame) GoToSelect();
            if (phase == Phase.Over && (kb[Key.Enter].wasPressedThisFrame || kb[Key.NumpadEnter].wasPressedThisFrame))
            {
                wins[0] = wins[1] = 0; round = 1; StartRound();
            }
        }

        void GoToSelect()
        {
            phase = Phase.Select;
            Announce("");
            while (projectiles.Count > 0) RemoveProjectile(projectiles[0]);
        }

        void SelectInput()
        {
            var kb = Keyboard.current;
            if (kb == null) return;
            int n = content.characters.Length;
            if (kb[Key.A].wasPressedThisFrame) pick1 = (pick1 + n - 1) % n;
            if (kb[Key.D].wasPressedThisFrame) pick1 = (pick1 + 1) % n;
            if (kb[Key.LeftArrow].wasPressedThisFrame) pick2 = (pick2 + n - 1) % n;
            if (kb[Key.RightArrow].wasPressedThisFrame) pick2 = (pick2 + 1) % n;
            if (kb[Key.Q].wasPressedThisFrame) pickMap = (pickMap + MapCount - 1) % MapCount;
            if (kb[Key.E].wasPressedThisFrame) pickMap = (pickMap + 1) % MapCount;
            if (kb[Key.Enter].wasPressedThisFrame || kb[Key.NumpadEnter].wasPressedThisFrame || kb[Key.Space].wasPressedThisFrame)
                BeginMatch();
        }

        void Separate()
        {
            if (P1.State == FState.KO || P2.State == FState.KO) return;
            float d = P2.X - P1.X;
            float min = (P1.PushboxWidth + P2.PushboxWidth) / 2;
            if (Mathf.Abs(d) < min && Mathf.Abs(P1.Y - P2.Y) < 1.4f)
            {
                float s = (min - Mathf.Abs(d)) / 2 * (d == 0 ? P1.Facing : Mathf.Sign(d));
                P1.X = Mathf.Clamp(P1.X - s, -Fighter.StageHalfWidth, Fighter.StageHalfWidth);
                P2.X = Mathf.Clamp(P2.X + s, -Fighter.StageHalfWidth, Fighter.StageHalfWidth);
            }
        }

        // ---------- Combat callbacks ----------

        public void OnHit(Fighter victim, Fighter attacker, MoveData m, Vector3 pos)
        {
            bool heavy = m.Damage > 9;
            Color c = m.Id == "Projectile" ? attacker.Accent * 1.6f : new Color(1.6f, 1.0f, 0.3f);
            var away = new Vector3(Mathf.Sign(victim.X - attacker.X), 0.35f, 0);
            fx.Spark(pos, c, heavy ? 30 : 18, heavy ? 1.4f : 1f, away);
            Hitstop(heavy ? 0.1f : 0.06f);
            Shake(m.Damage * 0.02f);
            sfx.Play(heavy ? Sfx.Kind.Heavy : Sfx.Kind.Hit);
            if (attacker.Combo >= 2) { comboOwner = attacker; comboHide = 1.2f; }
        }

        /// <summary>wear: 0 for a fresh block, toward 1 for one held a long time (sparks get hotter and heavier).</summary>
        public void OnBlock(Vector3 pos, float wear)
        {
            var c = Color.Lerp(new Color(0.6f, 0.85f, 1.3f), new Color(1.6f, 0.7f, 0.2f), wear);
            fx.Spark(pos, c, 8 + Mathf.RoundToInt(14 * wear), 0.6f + 0.5f * wear);
            Hitstop(0.04f + 0.03f * wear);
            Shake(0.04f + 0.1f * wear);
            sfx.Play(Sfx.Kind.Block);
        }

        public void OnParry(Fighter defender, Fighter attacker, Vector3 pos)
        {
            // the payoff: a steel clash, sparks flying off the blades, a beat of stillness, then slow-mo
            fx.ClashSparks(pos, defender.Facing);
            Hitstop(0.16f);
            timeScale = 0.45f; slowmoT = 0.32f;
            Shake(0.16f);
            sfx.Play(Sfx.Kind.Parry);
            Popup("PARRY!", defender, new Color(1f, 0.86f, 0.35f));
            EventShot("parry");
            Debug.Log($"[combat] PARRY by {defender.Data.Id}");
        }

        public void OnGuardBreak(Fighter f, Vector3 pos)
        {
            fx.Spark(pos, new Color(0.9f, 1.2f, 1.8f), 36, 1.5f, new Vector3(0, 0.5f, 0));
            fx.Ring(pos, new Color(1.8f, 0.3f, 0.2f), 0.3f, 5f, 0.3f, 0.1f);
            fx.FlashLight(pos + Vector3.back * 0.4f, new Color(0.7f, 0.8f, 1f), 10f, 5f, 0.15f);
            Hitstop(0.12f);
            Shake(0.35f);
            sfx.Play(Sfx.Kind.GuardBreak);
            Popup("GUARD BREAK!", f, new Color(1f, 0.3f, 0.25f));
            EventShot("guardbreak");
            Debug.Log($"[combat] GUARD BREAK on {f.Data.Id}");
        }

        // ---------- floating combat text ----------

        class PopupText { public string Text; public Fighter Who; public Color Color; public float Life; }
        readonly List<PopupText> popups = new List<PopupText>();

        void Popup(string text, Fighter who, Color c) => popups.Add(new PopupText { Text = text, Who = who, Color = c, Life = 0.9f });

        public void OnArmor(Fighter f, Vector3 pos)
        {
            fx.Spark(pos, new Color(1.4f, 0.9f, 0.5f), 10, 0.8f);
            Hitstop(0.05f);
            Shake(0.1f);
            sfx.Play(Sfx.Kind.Block);
        }

        public void OnKO(Fighter loser)
        {
            sfx.Play(Sfx.Kind.KO);
            if (phase != Phase.Fight) return;
            phase = Phase.KO; phaseT = 0;
            winner = loser == P1 ? P2 : P1;
            timeScale = 0.3f; slowmoT = 1.2f;
            Shake(0.35f);
            Announce("K.O.", "", new Color(1f, 0.88f, 0.3f));
        }

        void Hitstop(float t) => freeze = Mathf.Max(freeze, t);
        void Shake(float a) => shakeAmt = Mathf.Max(shakeAmt, a);

        // ---------- Projectiles ----------

        public void FireProjectile(Fighter f, ProjectileSpec spec)
        {
            var go = new GameObject("Projectile_" + spec.Style);
            go.transform.position = new Vector3(f.X + f.Facing * spec.SpawnX, f.Y + spec.Height, 0);
            var p = new Projectile { Go = go, Owner = f, Spec = spec, Dir = f.Facing, Life = spec.Life };
            if (spec.Style == "knife" && f.Def.projectilePrefab)
            {
                var spin = new GameObject("Spin").transform;
                spin.SetParent(go.transform, false);
                spin.localRotation = Quaternion.Euler(0, 0, -90 * f.Facing);   // knife model points +Y; aim it along travel
                var knife = Instantiate(f.Def.projectilePrefab, spin);
                knife.transform.localPosition = new Vector3(0, -0.1f, 0);
                p.Spin = spin;
                var trail = knife.AddComponent<TrailRenderer>();
                trail.time = 0.12f; trail.widthMultiplier = 0.05f;
                trail.widthCurve = AnimationCurve.Linear(0, 1, 1, 0);
                trail.material = new Material(glowTemplate);
                trail.material.SetColor("_BaseColor", f.Def.trailColor);
                trail.shadowCastingMode = ShadowCastingMode.Off;
                sfx.Play(Sfx.Kind.Block);
            }
            else
            {
                StageFX.AshWave(go.transform, content.particleTemplate, glowTemplate, f.Facing);
                Shake(0.2f);
                sfx.Play(Sfx.Kind.Orb);
            }
            projectiles.Add(p);
        }

        void RemoveProjectile(Projectile p)
        {
            projectiles.Remove(p);
            if (p.Go) Destroy(p.Go);
        }

        void UpdateProjectiles(float dt)
        {
            for (int i = projectiles.Count - 1; i >= 0; i--)
            {
                if (i >= projectiles.Count) continue;
                var p = projectiles[i];
                var pos = p.Go.transform.position;
                pos.x += p.Dir * p.Spec.Speed * dt;
                p.Go.transform.position = pos;
                p.Life -= dt;
                if (p.Spin) p.Spin.Rotate(0, 1400 * dt, 0, Space.Self);

                var other = projectiles.Find(q => q.Owner != p.Owner && Mathf.Abs(q.X - pos.x) < q.Spec.Radius + p.Spec.Radius);
                if (other != null)
                {
                    fx.Spark(pos, Color.white * 1.5f, 20, 1.2f);
                    Shake(0.15f);
                    sfx.Play(Sfx.Kind.Heavy);
                    RemoveProjectile(p);
                    RemoveProjectile(other);
                    continue;
                }

                var target = p.Owner == P1 ? P2 : P1;
                if (target.State != FState.KO && target.Overlaps(p.Pos2D, p.Pos2D, p.Spec.Radius, out var contact))
                {
                    target.TakeHit(p.Owner, p.Spec.Hit, new Vector3(contact.x, contact.y, 0), p.Dir, projectile: true);
                    RemoveProjectile(p);
                    continue;
                }
                if (p.Life <= 0 || Mathf.Abs(pos.x) > 13) RemoveProjectile(p);
            }
        }

        // ---------- Camera ----------

        void UpdateCamera(float dt, bool selectScreen)
        {
            float mid = 0, sep = 6;
            if (!selectScreen && P1 && P2) { mid = (P1.X + P2.X) / 2; sep = Mathf.Abs(P1.X - P2.X); }
            float k = 1 - Mathf.Pow(0.02f, dt);
            float fit = Mathf.Max(1, 1.7f / cam.aspect);
            var targetPos = new Vector3(mid * 0.85f + Mathf.Sin(clock * 0.15f) * 1.0f, 1.85f + sep * 0.06f, -(4.9f + sep * 0.5f) * fit);
            if (selectScreen) targetPos = new Vector3(Mathf.Sin(Time.time * 0.1f) * 3f, 3.2f, -13f);
            camBase = Vector3.Lerp(camBase, targetPos, k);
            camLook = Vector3.Lerp(camLook, new Vector3(mid, selectScreen ? 2.2f : 1.15f, 0), k);

            var pos = camBase;
            if (shakeAmt > 0)
            {
                pos += new Vector3(Random.value - 0.5f, Random.value - 0.5f, 0) * shakeAmt;
                shakeAmt = Mathf.Max(0, shakeAmt - dt * 1.5f);
            }
            cam.transform.position = pos;
            cam.transform.LookAt(camLook);
            if (fireShotTarget.HasValue)
            {
                // autotest close-up of a stage fire
                var f = fireShotTarget.Value;
                cam.transform.position = f + new Vector3(-0.9f, 0.5f, -1.6f);
                cam.transform.LookAt(f + Vector3.up * 0.45f);
            }
        }

        // ---------- HUD (IMGUI keeps the prototype self-contained) ----------

        GUIStyle nameStyle, titleStyle, timerStyle, bigStyle, subStyle, comboStyle, helpStyle, debugStyle, buttonStyle, cardStyle, popupStyle;

        void OnGUI()
        {
            float w = Screen.width, h = Screen.height, s = h / 720f;
            BuildStyles(s);
            if (phase == Phase.Select) { DrawSelect(w, h, s); return; }

            float pad = 24 * s, barH = 22 * s, top = 48 * s;
            float barW = (w - pad * 2 - 100 * s) / 2;
            DrawSide(P1, 0, new Rect(pad, top, barW, barH), s, false);
            DrawSide(P2, 1, new Rect(w - pad - barW, top, barW, barH), s, true);
            Shadowed(new Rect(w / 2 - 50 * s, top - 16 * s, 100 * s, 50 * s), Mathf.CeilToInt(timer).ToString(), timerStyle, Color.white, s);

            if (!string.IsNullOrEmpty(bigText))
            {
                Shadowed(new Rect(0, h * 0.32f, w, 140 * s), bigText, bigStyle, bigColor, s * 3);
                if (!string.IsNullOrEmpty(subText))
                    Shadowed(new Rect(0, h * 0.32f + 140 * s, w, 40 * s), subText, subStyle, Color.white, s);
            }

            if (comboHide > 0 && comboOwner != null)
            {
                comboStyle.alignment = comboOwner == P1 ? TextAnchor.MiddleLeft : TextAnchor.MiddleRight;
                Shadowed(new Rect(pad, 118 * s, w - pad * 2, 40 * s), $"{comboOwner.Combo} HIT COMBO!", comboStyle, new Color(1f, 0.82f, 0.25f), s);
            }

            string mode = CpuP2 ? "CPU" : "P2";
            GUI.color = new Color(0, 0, 0, 0.55f);
            var helpRect = new Rect(pad * 0.6f, h - 96 * s, 680 * s, 82 * s);
            GUI.DrawTexture(helpRect, Texture2D.whiteTexture);
            GUI.color = Color.white;
            GUI.Label(new Rect(helpRect.x + 10 * s, helpRect.y + 6 * s, helpRect.width, helpRect.height),
                "P1  A/D move · W jump · S block · J light · K heavy · L special (meter)\n" +
                "P2  Arrows move/jump/block · , light · . heavy · / special\n" +
                $"Tap block just before a hit to PARRY · holding block wears your guard down\n" +
                $"2: P2 is {mode} · R: restart · Esc: character select · F1: hitboxes", helpStyle);

            foreach (var p in popups)
            {
                float k = p.Life / 0.9f;                       // 1 -> 0
                float pop = 1f + 0.6f * Mathf.Clamp01((k - 0.8f) / 0.2f);
                var sp = cam.WorldToScreenPoint(new Vector3(p.Who.X, p.Who.Y + 2.15f + (1 - k) * 0.35f, 0));
                if (sp.z < 0) continue;
                popupStyle.fontSize = Mathf.RoundToInt(30 * s * pop);
                var c = p.Color; c.a = Mathf.Clamp01(k * 2.5f);
                Shadowed(new Rect(sp.x - 220 * s, Screen.height - sp.y - 30 * s, 440 * s, 60 * s), p.Text, popupStyle, c, s);
            }

            HitboxButton(w, h, s, pad);
            if (ShowHitboxes)
            {
                DebugLabel(P1, s);
                DebugLabel(P2, s);
                GUI.Label(new Rect(w - pad - 480 * s, h - 92 * s, 480 * s, 26 * s),
                    "green hurtbox · blue pushbox · yellow startup · red active", debugStyle);
            }
        }

        void HitboxButton(float w, float h, float s, float pad)
        {
            var btn = new Rect(w - pad - 210 * s, h - 62 * s, 210 * s, 44 * s);
            GUI.backgroundColor = ShowHitboxes ? new Color(1f, 0.35f, 0.35f) : new Color(0.5f, 0.55f, 0.7f);
            if (GUI.Button(btn, ShowHitboxes ? "Hitboxes: ON  (F1)" : "Hitboxes: OFF  (F1)", buttonStyle))
                ShowHitboxes = !ShowHitboxes;
            GUI.backgroundColor = Color.white;
        }

        void DrawSelect(float w, float h, float s)
        {
            Fill(new Rect(0, 0, w, h), new Color(0, 0, 0, 0.2f));
            Shadowed(new Rect(0, 24 * s, w, 70 * s), "CHOOSE YOUR FIGHTERS", bigStyle, Color.white, s * 2);
            float cw = 330 * s, ch = 200 * s, cy = 110 * s;
            Card(new Rect(w * 0.17f - cw / 2, cy, cw, ch), "PLAYER 1", content.characters[pick1], "A / D", ref pick1, s);
            Card(new Rect(w * 0.83f - cw / 2, cy, cw, ch), CpuP2 ? "CPU" : "PLAYER 2", content.characters[pick2], "← / →", ref pick2, s);

            var stageRect = new Rect(w / 2 - 260 * s, h - 250 * s, 520 * s, 70 * s);
            Fill(stageRect, new Color(0.05f, 0.06f, 0.1f, 0.85f));
            GUI.Label(new Rect(stageRect.x, stageRect.y + 6 * s, stageRect.width, 24 * s), "STAGE  (Q / E)", titleStyle);
            if (GUI.Button(new Rect(stageRect.x + 10 * s, stageRect.y + 30 * s, 40 * s, 32 * s), "<", buttonStyle))
                pickMap = (pickMap + MapCount - 1) % MapCount;
            if (GUI.Button(new Rect(stageRect.xMax - 50 * s, stageRect.y + 30 * s, 40 * s, 32 * s), ">", buttonStyle))
                pickMap = (pickMap + 1) % MapCount;
            Shadowed(new Rect(stageRect.x, stageRect.y + 28 * s, stageRect.width, 36 * s), MapName(pickMap).ToUpper(), cardStyle, new Color(1f, 0.85f, 0.5f), s);

            if (GUI.Button(new Rect(w / 2 - 120 * s, stageRect.yMax + 18 * s, 240 * s, 52 * s), "FIGHT  (Enter)", buttonStyle))
                BeginMatch();
            if (GUI.Button(new Rect(w / 2 - 120 * s, stageRect.yMax + 78 * s, 240 * s, 34 * s), CpuP2 ? "P2: CPU  (2)" : "P2: Human  (2)", buttonStyle))
                CpuP2 = !CpuP2;
        }

        void Card(Rect r, string who, CharacterDef def, string keys, ref int pick, float s)
        {
            var data = characterData[def.id];
            Fill(r, new Color(0.05f, 0.06f, 0.1f, 0.85f));
            Fill(new Rect(r.x, r.y, r.width, 4 * s), def.accent);
            GUI.Label(new Rect(r.x, r.y + 10 * s, r.width, 24 * s), $"{who}  ({keys})", titleStyle);
            Shadowed(new Rect(r.x, r.y + 40 * s, r.width, 50 * s), data.DisplayName, cardStyle, Color.white, s);
            GUI.Label(new Rect(r.x, r.y + 88 * s, r.width, 24 * s), data.Title, titleStyle);
            var moves = $"{data.Move("Light")?.Name} · {data.Move("Heavy")?.Name} · {data.Move("Special")?.Name}";
            GUI.Label(new Rect(r.x + 10 * s, r.y + 120 * s, r.width - 20 * s, 60 * s), moves, helpStyle);
            int n = content.characters.Length;
            if (GUI.Button(new Rect(r.x + 10 * s, r.yMax - 44 * s, 40 * s, 34 * s), "<", buttonStyle)) pick = (pick + n - 1) % n;
            if (GUI.Button(new Rect(r.xMax - 50 * s, r.yMax - 44 * s, 40 * s, 34 * s), ">", buttonStyle)) pick = (pick + 1) % n;
        }

        void DrawSide(Fighter f, int idx, Rect bar, float s, bool right)
        {
            nameStyle.alignment = right ? TextAnchor.LowerRight : TextAnchor.LowerLeft;
            string label = f == P2 ? $"{f.DisplayName} ({(CpuP2 ? "CPU" : "P2")})" : f.DisplayName;
            Shadowed(new Rect(bar.x, bar.y - 28 * s, bar.width, 24 * s), label, nameStyle, Color.white, s);

            for (int n = 0; n < 2; n++)
            {
                float pip = 12 * s, gap = 6 * s;
                float x = right ? bar.x + n * (pip + gap) : bar.xMax - (n + 1) * pip - n * gap;
                Fill(new Rect(x, bar.y - 20 * s, pip, pip), Color.white);
                Fill(new Rect(x + 2 * s, bar.y - 18 * s, pip - 4 * s, pip - 4 * s), wins[idx] > n ? new Color(1f, 0.82f, 0.25f) : new Color(0.1f, 0.1f, 0.15f));
            }

            float b = 2 * s;
            Fill(new Rect(bar.x - b, bar.y - b, bar.width + b * 2, bar.height + b * 2), Color.white);
            Fill(bar, new Color(0.1f, 0.02f, 0.03f));
            Fill(Portion(bar, f.LagHP / f.Data.Hp, right), new Color(0.88f, 0.16f, 0.24f));
            Fill(Portion(bar, f.HP / f.Data.Hp, right), new Color(1f, 0.78f, 0.15f));

            // guard bar: white when healthy, orange then red as it drains; flashes red while broken
            var guard = new Rect(bar.x, bar.yMax + 4 * s, bar.width, 5 * s);
            float gk = f.Guard / Fighter.GuardMax;
            Fill(guard, new Color(0.05f, 0.05f, 0.07f, 0.85f));
            Color gc = f.GuardBroken ? (Mathf.Repeat(Time.time * 8, 1) < 0.5f ? new Color(1f, 0.2f, 0.15f) : new Color(0.4f, 0.05f, 0.05f))
                : Color.Lerp(new Color(1f, 0.3f, 0.2f), Color.Lerp(new Color(1f, 0.65f, 0.2f), new Color(0.9f, 0.92f, 1f), Mathf.InverseLerp(0.35f, 0.8f, gk)), Mathf.InverseLerp(0.1f, 0.35f, gk));
            Fill(Portion(guard, f.GuardBroken ? 1f : gk, right), gc);

            var special = f.Data.Move("Special");
            float cost = special != null ? special.Cost : 50;
            var meter = new Rect(right ? bar.xMax - bar.width * 0.55f : bar.x, guard.yMax + 5 * s, bar.width * 0.55f, 8 * s);
            float glow = f.MeterFlash > 0 ? Mathf.Clamp01(f.MeterFlash / 0.6f) : 0f;
            if (glow > 0)
                Fill(new Rect(meter.x - 4 * s, meter.y - 4 * s, meter.width + 8 * s, meter.height + 8 * s), new Color(1f, 0.85f, 0.35f, glow));
            Fill(new Rect(meter.x - 1, meter.y - 1, meter.width + 2, meter.height + 2), f.Meter >= cost ? new Color(0.5f, 0.9f, 1f) : new Color(0.4f, 0.55f, 0.9f));
            Fill(meter, new Color(0.05f, 0.08f, 0.2f));
            Fill(Portion(meter, f.Meter / 100f, right), Color.Lerp(new Color(0.3f, 0.65f, 1f), new Color(1f, 0.9f, 0.5f), glow));
            float tick = meter.x + meter.width * (right ? 1 - cost / 100f : cost / 100f);
            Fill(new Rect(tick - 1, meter.y - 2, 2, meter.height + 4), Color.white);
        }

        void DebugLabel(Fighter f, float s)
        {
            var sp = cam.WorldToScreenPoint(new Vector3(f.X, f.Y + 2.3f, 0));
            if (sp.z < 0) return;
            string move = f.State == FState.Attack && f.Move != null ? $" {f.Move.Name}" : "";
            string text = $"{f.State}{move}  f{Mathf.FloorToInt(f.T * 60)}";
            debugStyle.alignment = TextAnchor.MiddleCenter;
            Shadowed(new Rect(sp.x - 140 * s, Screen.height - sp.y - 12 * s, 280 * s, 24 * s), text, debugStyle, new Color(0.7f, 1f, 0.7f), s);
            debugStyle.alignment = TextAnchor.MiddleRight;
        }

        static Rect Portion(Rect r, float frac, bool fromRight)
        {
            float wdt = r.width * Mathf.Clamp01(frac);
            return new Rect(fromRight ? r.xMax - wdt : r.x, r.y, wdt, r.height);
        }

        static void Fill(Rect r, Color c)
        {
            GUI.color = c;
            GUI.DrawTexture(r, Texture2D.whiteTexture);
            GUI.color = Color.white;
        }

        static void Shadowed(Rect r, string text, GUIStyle style, Color c, float offset)
        {
            var o = Mathf.Max(1, 2 * offset);
            style.normal.textColor = new Color(0, 0, 0, 0.8f);
            GUI.Label(new Rect(r.x + o, r.y + o, r.width, r.height), text, style);
            style.normal.textColor = c;
            GUI.Label(r, text, style);
        }

        void BuildStyles(float s)
        {
            if (nameStyle == null)
            {
                nameStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold };
                titleStyle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Italic };
                timerStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
                bigStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.BoldAndItalic, alignment = TextAnchor.MiddleCenter };
                subStyle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter };
                comboStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.BoldAndItalic };
                helpStyle = new GUIStyle(GUI.skin.label) { richText = false, wordWrap = true };
                debugStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleRight };
                buttonStyle = new GUIStyle(GUI.skin.button) { fontStyle = FontStyle.Bold };
                cardStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
                popupStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.BoldAndItalic, alignment = TextAnchor.MiddleCenter };
            }
            nameStyle.fontSize = Mathf.RoundToInt(18 * s);
            titleStyle.fontSize = Mathf.RoundToInt(15 * s);
            titleStyle.normal.textColor = new Color(0.8f, 0.82f, 0.9f);
            timerStyle.fontSize = Mathf.RoundToInt(42 * s);
            bigStyle.fontSize = Mathf.RoundToInt((phase == Phase.Select ? 46 : 110) * s);
            subStyle.fontSize = Mathf.RoundToInt(22 * s);
            comboStyle.fontSize = Mathf.RoundToInt(28 * s);
            helpStyle.fontSize = Mathf.RoundToInt(14 * s);
            helpStyle.normal.textColor = new Color(0.82f, 0.86f, 1f);
            debugStyle.fontSize = Mathf.RoundToInt(13 * s);
            buttonStyle.fontSize = Mathf.RoundToInt(16 * s);
            cardStyle.fontSize = Mathf.RoundToInt(34 * s);
        }

        // ---------- Autotest ----------

        void AutotestStep()
        {
            // game-clock based so a slow first frame (shader compilation) doesn't eat the test window
            float t = clock;
            if (Mathf.Repeat(t, 4f) < 0.02f) { P1.Meter = 100; P2.Meter = 100; }   // make sure specials get exercised
            if (!bladeShot && !string.IsNullOrEmpty(shotPath) && t > 2f)
            {
                // capture the first frame where a sword hitbox is live, with the overlay on
                foreach (var f in new[] { P1, P2 })
                    if (f.GetHitbox(out _, out _, out _, out var live) && live)
                    {
                        ShowHitboxes = true;
                        bladeShot = true;
                        bladeShotFrame = Time.frameCount + 1;
                        break;
                    }
            }
            if (bladeShotFrame > 0 && Time.frameCount == bladeShotFrame)
                ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", "_blade.png"));
            if (eventShotAt > 0) ShowHitboxes = false;
            if (eventShotAt > 0 && Time.unscaledTime >= eventShotAt)
            {
                ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", $"_{eventShotTag}.png"));
                eventShotAt = 0;
            }
            if (parryTest && phase == Phase.Fight)
            {
                // P1 keeps swinging from close range; the CPU always tries to parry; P2 holds block at times
                if (Mathf.Abs(P1.X - P2.X) > 1.4f) { P1.X = P2.X - 1.3f * Mathf.Sign(P2.X - P1.X + 0.001f); }
                if (P1.State == FState.Idle || P1.State == FState.Walk)
                    P1.ForceMove(Mathf.Repeat(t, 3f) < 1.5f ? "Light" : "Heavy");
                if (t > 9f && !ai2.AlwaysBlock) Debug.Log($"[combat] P2 now holding block, guard={P2.Guard:F0}");
                ai2.AlwaysBlock = t > 9f;
            }
            if (fireShot && phase == Phase.Fight)
            {
                // frame the stage fire nearest the fighters for a second, then capture it
                if (t >= 4f && t < 5f && fireShotTarget == null)
                {
                    float best = float.MaxValue;
                    foreach (var ps in mapInstance.GetComponentsInChildren<ParticleSystem>())
                    {
                        if (ps.name != "FlameOuter") continue;
                        var p = ps.transform.position;
                        float d = p.magnitude;
                        if (p.z > -0.5f && d < best) { best = d; fireShotTarget = p; }
                    }
                }
                if (fireShotTarget.HasValue && t >= 5f)
                {
                    if (t < 5.02f) ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", "_fire.png"));
                    else if (t > 5.3f) { fireShotTarget = null; fireShot = false; }
                }
            }
            if (specialTest)
            {
                // space the fighters out and fire each special on its own (they'd cancel each other mid-stage),
                // capturing the projectile in flight
                float[] fireAt = { 2.5f, 7f };
                foreach (var ft in fireAt)
                {
                    if (t >= ft && t < ft + 0.02f && phase == Phase.Fight)
                    {
                        P1.X = -4.5f; P2.X = 4.5f; P1.Facing = 1; P2.Facing = -1;
                        (ft < 5f ? P1 : P2).ForceMove("Special");
                    }
                    if (t >= ft + 0.95f && t < ft + 0.97f) ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", $"_special{ft:F0}.png"));
                }
            }
            if (!projectileShot && projectiles.Count > 0 && projectiles[0].Life < projectiles[0].Spec.Life - 0.12f && !string.IsNullOrEmpty(shotPath))
            {
                projectileShot = true;
                ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", "_projectile.png"));
            }
            if (Time.frameCount % 60 == 0)
                Debug.Log($"[autotest] t={t:F1} phase={phase} round={round} " +
                          $"P1 {P1.Data.Id} {P1.State} {P1.Move?.Id} hp={P1.HP:F0} x={P1.X:F2} | " +
                          $"P2 {P2.Data.Id} {P2.State} {P2.Move?.Id} hp={P2.HP:F0} x={P2.X:F2} | proj={projectiles.Count} wins={wins[0]}-{wins[1]}");

            if (!string.IsNullOrEmpty(shotPath))
            {
                float[] at = { 3f, 5.5f, 8f, 11f };
                if (shotsTaken < at.Length && t > at[shotsTaken])
                {
                    ScreenCapture.CaptureScreenshot(shotPath.Replace(".png", $"_{shotsTaken}.png"));
                    shotsTaken++;
                    toggleAfterShot = true;
                }
                else if (toggleAfterShot)
                {
                    toggleAfterShot = false;
                    ShowHitboxes = !ShowHitboxes; // alternate so both views get captured
                }
            }
            if (t > 20f || Time.realtimeSinceStartup - autotestStart > 80f)
            {
                Debug.Log("[autotest] done");
                Application.Quit();
            }
        }
    }
}
