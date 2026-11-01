using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace FightingGame
{
    /// <summary>
    /// Runs a best-of-3 match: spawns both fighters, ticks them in order, handles hitstop / slow-mo,
    /// projectiles, camera, HUD and the hitbox debug view.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        enum Phase { Intro, Fight, KO, Between, Over }

        [SerializeField] Material litTemplate;
        [SerializeField] Material glowTemplate;
        [SerializeField] Camera cam;

        [Tooltip("Show hurtboxes / hitboxes. Toggle in game with F1 or the on-screen button.")]
        public bool ShowHitboxes;
        [Tooltip("When on, P2 is controlled by the CPU. Toggle in game with 2.")]
        public bool CpuP2 = true;
        public float RoundTime = 60;

        public Fighter P1 { get; private set; }
        public Fighter P2 { get; private set; }

        readonly List<Orb> orbs = new List<Orb>();
        OnlineMatch online;
        HumanInput input1, input2;
        AIController ai2, ai1;
        Effects fx;
        HitboxDebug debugView;
        Sfx sfx;

        Phase phase;
        float phaseT, timer, clock;
        int round = 1;
        readonly int[] wins = new int[2];
        Fighter winner;
        bool fightShown;

        float freeze, shakeAmt, timeScale = 1, slowmoT;
        Vector3 camBase, camLook;

        string bigText = "", subText = "";
        Color bigColor = Color.white;
        float comboHide;
        Fighter comboOwner;

        // Automated smoke test: run the player with -autotest to watch CPU vs CPU, screenshot and quit.
        bool autotest;
        string shotPath;
        int shotsTaken;
        bool toggleAfterShot;

        void Awake()
        {
            if (cam == null) cam = Camera.main;
            P1 = Fighter.Create(this, "VOLT", new Color(0.18f, 0.44f, 1f), new Color(0.34f, 0.84f, 1f), litTemplate, 0);
            P2 = Fighter.Create(this, "EMBER", new Color(0.85f, 0.16f, 0.25f), new Color(1f, 0.63f, 0.25f), litTemplate, 1.6f);
            input1 = new HumanInput(true);
            input2 = new HumanInput(false);
            ai1 = new AIController();
            ai2 = new AIController();
            fx = new Effects(glowTemplate, cam.transform);
            debugView = new HitboxDebug(glowTemplate);
            sfx = new Sfx(gameObject);

            var args = System.Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "-autotest") autotest = true;
                if (args[i] == "-shot" && i + 1 < args.Length) shotPath = args[i + 1];
            }
            if (autotest) ShowHitboxes = true;

            camBase = new Vector3(0, 2.6f, -9);
            camLook = new Vector3(0, 1.2f, 0);
            StartMatch();
            online = gameObject.AddComponent<OnlineMatch>();
            online.Initialize(this);
        }

        // ---------- Match flow ----------

        void StartMatch()
        {
            wins[0] = wins[1] = 0;
            round = 1;
            StartRound();
        }

        void StartRound()
        {
            P1.ResetFor(-3, 1);
            P2.ResetFor(3, -1);
            while (orbs.Count > 0) RemoveOrb(orbs[0]);
            phase = Phase.Intro; phaseT = 0; timer = RoundTime; winner = null; fightShown = false;
            timeScale = 1; slowmoT = 0;
            input1.ClearBuffer(); input2.ClearBuffer();
            online?.RemoteInput.Clear();
            freeze = shakeAmt = comboHide = 0;
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
                        winner = Mathf.Approximately(P1.HP, P2.HP) ? null : (P1.HP > P2.HP ? P1 : P2);
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
                            Announce($"{winner.DisplayName} WINS", "Press Enter for a rematch");
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
            online.PollClient();
            if (online.Online && (!online.IsHost || !online.Ready)) {
                P1.UpdateVisual(real, clock); P2.UpdateVisual(real, clock);
                fx.Tick(real); UpdateCamera(real); debugView.Tick(ShowHitboxes, P1, P2, orbs);
                return;
            }
            HandleMetaKeys();
            input1.Poll();
            input2.Poll();

            if (slowmoT > 0) { slowmoT -= real; if (slowmoT <= 0) timeScale = 1; }
            float dt = real * timeScale;
            clock += dt;

            if (freeze > 0) freeze -= real;
            else
            {
                bool fighting = phase == Phase.Fight;
                if (autotest) ai1.Think(dt, P1, P2, orbs);
                if (CpuP2) ai2.Think(dt, P2, P1, orbs);
                IFighterInput in1 = !fighting ? NoInput.Instance : autotest ? ai1 : input1;
                IFighterInput in2 = !fighting ? NoInput.Instance : online.Online ? online.RemoteInput : CpuP2 ? ai2 : input2;
                P1.Tick(dt, in1, P2);
                P2.Tick(dt, in2, P1);
                Separate();
                UpdateOrbs(dt);
            }

            if (comboHide > 0) comboHide -= real;
            UpdateGame(real);
            P1.UpdateVisual(real, clock);
            P2.UpdateVisual(real, clock);
            fx.Tick(dt);
            UpdateCamera(real);
            debugView.Tick(ShowHitboxes, P1, P2, orbs);
            if (autotest) AutotestStep();
        }

        void HandleMetaKeys()
        {
            var kb = Keyboard.current;
            if (kb == null) return;
            if (kb[Key.F1].wasPressedThisFrame) ShowHitboxes = !ShowHitboxes;
            if (!online.Online && kb[Key.Digit2].wasPressedThisFrame) CpuP2 = !CpuP2;
            if (kb[Key.R].wasPressedThisFrame) StartMatch();
            if (phase == Phase.Over && (kb[Key.Enter].wasPressedThisFrame || kb[Key.NumpadEnter].wasPressedThisFrame)) StartMatch();
        }

        void Separate()
        {
            if (P1.State == FState.KO || P2.State == FState.KO) return;
            float d = P2.X - P1.X;
            if (Mathf.Abs(d) < Fighter.PushboxWidth && Mathf.Abs(P1.Y - P2.Y) < 1.4f)
            {
                float s = (Fighter.PushboxWidth - Mathf.Abs(d)) / 2 * (d == 0 ? P1.Facing : Mathf.Sign(d));
                P1.X = Mathf.Clamp(P1.X - s, -Fighter.StageHalfWidth, Fighter.StageHalfWidth);
                P2.X = Mathf.Clamp(P2.X + s, -Fighter.StageHalfWidth, Fighter.StageHalfWidth);
            }
        }

        // ---------- Combat callbacks ----------

        public void OnHit(Fighter victim, Fighter attacker, MoveData m, Vector3 pos)
        {
            bool heavy = m.Damage > 8;
            fx.Spark(pos, m == MoveData.Orb ? attacker.Accent * 1.5f : new Color(1.6f, 1.0f, 0.3f), heavy ? 22 : 14, heavy ? 1.3f : 1f);
            Hitstop(heavy ? 0.09f : 0.06f);
            Shake(m.Damage * 0.022f);
            sfx.Play(heavy ? Sfx.Kind.Heavy : Sfx.Kind.Hit);
            if (attacker.Combo >= 2) { comboOwner = attacker; comboHide = 1.2f; }
        }

        public void OnBlock(Vector3 pos)
        {
            fx.Spark(pos, new Color(0.5f, 0.8f, 1.2f), 8, 0.6f);
            Hitstop(0.04f);
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

        public void FireOrb(Fighter f)
        {
            var go = new GameObject("Orb");
            go.transform.position = new Vector3(f.X + f.Facing * 0.8f, f.Y + 1.45f, 0);
            Glow(PrimitiveType.Sphere, go.transform, 0.4f, Color.white * 2);
            var halo = Glow(PrimitiveType.Sphere, go.transform, 0.84f, f.Accent * 0.6f);
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = f.Accent;
            light.range = 6;
            light.intensity = 4;
            orbs.Add(new Orb { Go = go, Halo = halo, Owner = f, Dir = f.Facing });
            if (online == null || !online.Online || online.IsHost) sfx.Play(Sfx.Kind.Orb);
        }

        Transform Glow(PrimitiveType type, Transform parent, float size, Color c)
        {
            var g = GameObject.CreatePrimitive(type);
            Destroy(g.GetComponent<Collider>());
            var r = g.GetComponent<MeshRenderer>();
            r.sharedMaterial = glowTemplate;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            var mpb = new MaterialPropertyBlock();
            mpb.SetColor("_BaseColor", c);
            r.SetPropertyBlock(mpb);
            g.transform.SetParent(parent, false);
            g.transform.localScale = Vector3.one * size;
            return g.transform;
        }

        void UpdateOrbs(float dt)
        {
            for (int i = orbs.Count - 1; i >= 0; i--)
            {
                if (i >= orbs.Count) continue;
                var o = orbs[i];
                var p = o.Go.transform.position;
                p.x += o.Dir * Orb.Speed * dt;
                o.Go.transform.position = p;
                o.Life -= dt;
                o.Halo.localScale = Vector3.one * 0.84f * (1 + Mathf.Sin(clock * 30) * 0.15f);
                o.TrailTimer -= dt;
                if (o.TrailTimer <= 0) { o.TrailTimer = 0.03f; fx.Trail(p, o.Owner.Accent); }

                var other = orbs.Find(q => q.Owner != o.Owner && Mathf.Abs(q.X - p.x) < 0.6f);
                if (other != null)
                {
                    fx.Spark(p, Color.white * 1.5f, 20, 1.2f);
                    Shake(0.15f);
                    sfx.Play(Sfx.Kind.Heavy);
                    RemoveOrb(o);
                    RemoveOrb(other);
                    continue;
                }

                var target = o.Owner == P1 ? P2 : P1;
                if (target.State != FState.KO && target.Overlaps(o.Pos2D, MoveData.Orb.HitboxRadius))
                {
                    target.TakeHit(o.Owner, MoveData.Orb, p, o.Dir);
                    RemoveOrb(o);
                    continue;
                }
                if (o.Life <= 0 || Mathf.Abs(p.x) > 13) RemoveOrb(o);
            }
        }

        void RemoveOrb(Orb o)
        {
            orbs.Remove(o);
            Destroy(o.Go);
        }

        // ---------- Camera ----------

        void UpdateCamera(float dt)
        {
            float mid = (P1.X + P2.X) / 2, sep = Mathf.Abs(P1.X - P2.X);
            float k = 1 - Mathf.Pow(0.02f, dt);
            float fit = Mathf.Max(1, 1.7f / cam.aspect); // pull back on narrow windows
            var targetPos = new Vector3(mid * 0.85f + Mathf.Sin(clock * 0.15f) * 1.3f, 2.4f + sep * 0.08f, -(7 + sep * 0.6f) * fit);
            camBase = Vector3.Lerp(camBase, targetPos, k);
            camLook = Vector3.Lerp(camLook, new Vector3(mid, 1.25f, 0), k);

            var pos = camBase;
            if (shakeAmt > 0)
            {
                pos += new Vector3(Random.value - 0.5f, Random.value - 0.5f, 0) * shakeAmt;
                shakeAmt = Mathf.Max(0, shakeAmt - dt * 1.5f);
            }
            cam.transform.position = pos;
            cam.transform.LookAt(camLook);
        }

        // ---------- HUD (IMGUI keeps the prototype self-contained) ----------

        GUIStyle nameStyle, timerStyle, bigStyle, subStyle, comboStyle, helpStyle, debugStyle, buttonStyle;

        void OnGUI()
        {
            float w = Screen.width, h = Screen.height, s = h / 720f;
            BuildStyles(s);

            float pad = 24 * s, barH = 22 * s, top = 44 * s;
            float barW = (w - pad * 2 - 100 * s) / 2;
            DrawSide(P1, 0, new Rect(pad, top, barW, barH), s, false);
            DrawSide(P2, 1, new Rect(w - pad - barW, top, barW, barH), s, true);
            Shadowed(new Rect(w / 2 - 50 * s, top - 14 * s, 100 * s, 50 * s), Mathf.CeilToInt(timer).ToString(), timerStyle, Color.white, s);

            if (!string.IsNullOrEmpty(bigText))
            {
                Shadowed(new Rect(0, h * 0.32f, w, 140 * s), bigText, bigStyle, bigColor, s * 3);
                if (!string.IsNullOrEmpty(subText))
                    Shadowed(new Rect(0, h * 0.32f + 140 * s, w, 40 * s), subText, subStyle, Color.white, s);
            }

            if (comboHide > 0 && comboOwner != null)
            {
                comboStyle.alignment = comboOwner == P1 ? TextAnchor.MiddleLeft : TextAnchor.MiddleRight;
                Shadowed(new Rect(pad, 110 * s, w - pad * 2, 40 * s), $"{comboOwner.Combo} HIT COMBO!", comboStyle, new Color(1f, 0.82f, 0.25f), s);
            }

            string mode = online.Online ? "ONLINE" : CpuP2 ? "CPU" : "P2";
            GUI.color = new Color(0, 0, 0, 0.55f);
            var helpRect = new Rect(pad * 0.6f, h - 78 * s, 640 * s, 64 * s);
            GUI.DrawTexture(helpRect, Texture2D.whiteTexture);
            GUI.color = Color.white;
            GUI.Label(new Rect(helpRect.x + 10 * s, helpRect.y + 6 * s, helpRect.width, helpRect.height),
                "P1  A/D move · W jump · S block · J punch · K kick · L orb (½ meter)\n" +
                "P2  Arrows move/jump/block · , punch · . kick · / orb\n" +
                $"2: P2 is {mode} (toggle) · R: restart · F1: hitboxes", helpStyle);

            var btn = new Rect(w - pad - 210 * s, h - 62 * s, 210 * s, 44 * s);
            GUI.backgroundColor = ShowHitboxes ? new Color(1f, 0.35f, 0.35f) : new Color(0.5f, 0.55f, 0.7f);
            if (GUI.Button(btn, ShowHitboxes ? "Hitboxes: ON  (F1)" : "Hitboxes: OFF  (F1)", buttonStyle))
                ShowHitboxes = !ShowHitboxes;
            GUI.backgroundColor = Color.white;

            if (ShowHitboxes)
            {
                DebugLabel(P1, s);
                DebugLabel(P2, s);
                GUI.Label(new Rect(w - pad - 480 * s, h - 92 * s, 480 * s, 26 * s),
                    "green hurtbox · blue pushbox · yellow startup · red active", debugStyle);
            }
        }

        void DrawSide(Fighter f, int idx, Rect bar, float s, bool right)
        {
            nameStyle.alignment = right ? TextAnchor.LowerRight : TextAnchor.LowerLeft;
            string label = f == P2 ? $"{f.DisplayName} ({(CpuP2 ? "CPU" : "P2")})" : f.DisplayName;
            Shadowed(new Rect(bar.x, bar.y - 26 * s, bar.width, 24 * s), label, nameStyle, Color.white, s);

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
            Fill(Portion(bar, f.LagHP / 100f, right), new Color(0.88f, 0.16f, 0.24f));
            Fill(Portion(bar, f.HP / 100f, right), new Color(1f, 0.78f, 0.15f));

            var meter = new Rect(right ? bar.xMax - bar.width * 0.55f : bar.x, bar.yMax + 8 * s, bar.width * 0.55f, 8 * s);
            Fill(new Rect(meter.x - 1, meter.y - 1, meter.width + 2, meter.height + 2), f.Meter >= MoveData.Special.Cost ? new Color(0.5f, 0.9f, 1f) : new Color(0.4f, 0.55f, 0.9f));
            Fill(meter, new Color(0.05f, 0.08f, 0.2f));
            Fill(Portion(meter, f.Meter / 100f, right), new Color(0.3f, 0.65f, 1f));
        }

        void DebugLabel(Fighter f, float s)
        {
            var sp = cam.WorldToScreenPoint(new Vector3(f.X, f.Y + 2.55f, 0));
            if (sp.z < 0) return;
            string move = f.State == FState.Attack && f.Move != null ? $" {f.Move.Name}" : "";
            string text = $"{f.State}{move}  f{Mathf.FloorToInt(f.T * 60)}";
            debugStyle.alignment = TextAnchor.MiddleCenter;
            Shadowed(new Rect(sp.x - 120 * s, Screen.height - sp.y - 12 * s, 240 * s, 24 * s), text, debugStyle, new Color(0.7f, 1f, 0.7f), s);
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
                timerStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
                bigStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.BoldAndItalic, alignment = TextAnchor.MiddleCenter };
                subStyle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter };
                comboStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.BoldAndItalic };
                helpStyle = new GUIStyle(GUI.skin.label) { richText = false };
                debugStyle = new GUIStyle(GUI.skin.label) { fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleRight };
                buttonStyle = new GUIStyle(GUI.skin.button) { fontStyle = FontStyle.Bold };
            }
            nameStyle.fontSize = Mathf.RoundToInt(17 * s);
            timerStyle.fontSize = Mathf.RoundToInt(42 * s);
            bigStyle.fontSize = Mathf.RoundToInt(110 * s);
            subStyle.fontSize = Mathf.RoundToInt(22 * s);
            comboStyle.fontSize = Mathf.RoundToInt(28 * s);
            helpStyle.fontSize = Mathf.RoundToInt(14 * s);
            helpStyle.normal.textColor = new Color(0.82f, 0.86f, 1f);
            debugStyle.fontSize = Mathf.RoundToInt(13 * s);
            buttonStyle.fontSize = Mathf.RoundToInt(16 * s);
        }

        public void BeginOnlineMatch() { CpuP2 = false; autotest = false; StartMatch(); }
        public void EndOnlineMatch() { CpuP2 = true; StartMatch(); }
        public MatchSnapshot CaptureSnapshot() {
            var shots = new OrbSnapshot[orbs.Count];
            for (int i=0; i<shots.Length; i++) shots[i] = new OrbSnapshot { x=orbs[i].Go.transform.position.x, y=orbs[i].Go.transform.position.y, owner=orbs[i].Owner==P1 ? 0 : 1, dir=orbs[i].Dir };
            return new MatchSnapshot { fighters=new[] {P1.CaptureNetwork(), P2.CaptureNetwork()}, orbs=shots,
                phase=(int)phase, round=round, w1=wins[0], w2=wins[1], timer=timer, clock=clock,
                text=bigText, sub=subText, color=bigColor, comboHide=comboHide, comboOwner=comboOwner==P1 ? 0 : 1 };
        }
        public void ApplySnapshot(MatchSnapshot s) {
            CpuP2=false;
            for(int i=0; i<2; i++) {
                var f=i==0 ? P1 : P2;
                if (s.fighters[i].hp < f.HP) { fx.Spark(new Vector3(s.fighters[i].x, s.fighters[i].y+1.5f,0), Color.yellow, 12, 1); sfx.Play(Sfx.Kind.Hit); }
                f.ApplyNetwork(s.fighters[i]);
            }
            phase=(Phase)s.phase; round=s.round; wins[0]=s.w1; wins[1]=s.w2; timer=s.timer; clock=s.clock;
            bigText=s.text; subText=phase==Phase.Over ? "Host can start a rematch" : s.sub; bigColor=s.color;
            comboHide=s.comboHide; comboOwner=s.comboOwner==0 ? P1 : P2;
            int count=s.orbs==null ? 0 : s.orbs.Length;
            while(orbs.Count>count) RemoveOrb(orbs[orbs.Count-1]);
            for(int i=0; i<count; i++) {
                var shot=s.orbs[i]; var owner=shot.owner==0 ? P1 : P2;
                if(i>=orbs.Count) FireOrb(owner);
                orbs[i].Owner=owner; orbs[i].Dir=shot.dir;
                orbs[i].Go.transform.position=new Vector3(shot.x,shot.y,0);
            }
        }

        // ---------- Autotest ----------

        void AutotestStep()
        {
            if (Time.frameCount % 60 == 0)
                Debug.Log($"[autotest] t={Time.unscaledTime:F1} phase={phase} round={round} " +
                          $"P1 {P1.State} hp={P1.HP:F0} x={P1.X:F2} | P2 {P2.State} hp={P2.HP:F0} x={P2.X:F2} | orbs={orbs.Count} wins={wins[0]}-{wins[1]}");

            if (!string.IsNullOrEmpty(shotPath))
            {
                float[] at = { 4f, 7f, 10f };
                if (shotsTaken < at.Length && Time.unscaledTime > at[shotsTaken])
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
            if (Time.unscaledTime > 25f)
            {
                Debug.Log("[autotest] done");
                Application.Quit();
            }
        }
    }
}
