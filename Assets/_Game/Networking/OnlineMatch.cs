using System;
using System.Text;
using System.Threading.Tasks;
using Unity.Collections;
using Unity.Netcode;
using Unity.Netcode.Transports.UTP;
using Unity.Services.Core;
using Unity.Services.Authentication;
using Unity.Services.Relay;
using Unity.Services.Relay.Models;
using UnityEngine;

namespace FightingGame
{
    // Small, host-authoritative two-player protocol. No client supplies combat state.
    public sealed class OnlineMatch : MonoBehaviour
    {
        const string InputMessage = "fg.input.v1", StateMessage = "fg.state.v1";
        public bool Online { get; private set; }
        public bool Ready { get; private set; }
        public bool IsHost => manager != null && manager.IsHost;
        public readonly RemoteFighterInput RemoteInput = new RemoteFighterInput();
        NetworkManager manager;
        UnityTransport transport;
        GameManager game;
        HumanInput local;
        string code = "", status = "Play online with a friend", joinText = "";
        bool busy, stopping;
        int generation;
        float nextInput, nextState, started, lastState;
        byte pendingPresses;
        bool smoke; string smokeCodePath, smokeReport; float smokeStarted;
        void Start() {
            var args = Environment.GetCommandLineArgs();
            for(int i=0;i<args.Length;i++) {
                if(args[i]=="-network-smoke") smoke=true;
                if(args[i]=="-host-code-file" && i+1<args.Length) smokeCodePath=args[++i];
                if(args[i]=="-join-code" && i+1<args.Length) joinText=args[++i];
                if(args[i]=="-network-report" && i+1<args.Length) smokeReport=args[++i];
            }
            if(smoke) { smokeStarted=Time.realtimeSinceStartup; Connect(!string.IsNullOrEmpty(smokeCodePath)); }
        }
        void Update() {
            if(!smoke) return;
            if(IsHost && !string.IsNullOrEmpty(code) && !string.IsNullOrEmpty(smokeCodePath)) System.IO.File.WriteAllText(smokeCodePath,code);
            if(Ready && !string.IsNullOrEmpty(smokeReport)) System.IO.File.WriteAllText(smokeReport,JsonUtility.ToJson(game.CaptureSnapshot()));
            if(Time.realtimeSinceStartup-smokeStarted>40) Application.Quit();
        }
        ulong guest;
        const byte Protocol = 1;

        public void Initialize(GameManager owner) { game = owner; local = new HumanInput(true); }

        void CreateNetwork()
        {
            var go = new GameObject("FightingGame Network");
            transport = go.AddComponent<UnityTransport>();
            manager = go.AddComponent<NetworkManager>();
            Application.runInBackground = true;
            manager.NetworkConfig = new NetworkConfig {
                NetworkTransport = transport, EnableSceneManagement = false,
                ConnectionApproval = true, ConnectionData = new byte[] { Protocol }, TickRate = 30
            };
            manager.ConnectionApprovalCallback = (request, response) => {
                response.Approved = request.Payload.Length == 1 && request.Payload[0] == Protocol && manager.ConnectedClientsIds.Count < 2;
                response.CreatePlayerObject = false;
                response.Reason = "Room full or incompatible game version.";
            };
            manager.OnClientConnectedCallback += Connected;
            manager.OnClientDisconnectCallback += Disconnected;
            manager.OnTransportFailure += () => Stop("Connection failed. Try hosting a new room.");
        }

        async void Connect(bool host)
        {
            if (busy || Online) return;
            string requestedCode = joinText.Trim().ToUpperInvariant();
            if (!host && (requestedCode.Length < 4 || requestedCode.Length > 12)) { status = "Enter a valid join code."; return; }
            busy = true; Online = true; Ready = false; int attempt = ++generation;
            status = host ? "Creating room..." : "Joining room...";
            try {
                if (string.IsNullOrEmpty(Application.cloudProjectId)) throw new InvalidOperationException("Link this project in Unity Services settings first.");
                await UnityServices.InitializeAsync();
                if (!AuthenticationService.Instance.IsSignedIn) await AuthenticationService.Instance.SignInAnonymouslyAsync();
                if (attempt != generation || this == null) return;
                CreateNetwork();
                if (host) {
                    var allocation = await RelayService.Instance.CreateAllocationAsync(1);
                    if (attempt != generation || this == null) return;
                    transport.SetRelayServerData(AllocationUtils.ToRelayServerData(allocation, "dtls"));
                    code = await RelayService.Instance.GetJoinCodeAsync(allocation.AllocationId);
                    if (attempt != generation || this == null) return;
                    if (!manager.StartHost()) throw new InvalidOperationException("Could not start host.");
                    status = "Waiting for your friend. You play VOLT.";
                } else {
                    var allocation = await RelayService.Instance.JoinAllocationAsync(requestedCode);
                    if (attempt != generation || this == null) return;
                    transport.SetRelayServerData(AllocationUtils.ToRelayServerData(allocation, "dtls"));
                    if (!manager.StartClient()) throw new InvalidOperationException("Could not start client.");
                    code = requestedCode;
                }
                manager.CustomMessagingManager.RegisterNamedMessageHandler(InputMessage, ReceiveInput);
                manager.CustomMessagingManager.RegisterNamedMessageHandler(StateMessage, ReceiveState);
                started = lastState = Time.realtimeSinceStartup;
            } catch (Exception ex) {
                if (attempt == generation && this != null) { Debug.LogWarning("Online connection: " + ex.ToString()); Stop("Could not connect: " + ex.Message); }
            } finally { if (attempt == generation) busy = false; }
        }

        void Connected(ulong id)
        {
            if (IsHost && id != NetworkManager.ServerClientId) {
                guest = id; Ready = true; RemoteInput.Clear(); game.BeginOnlineMatch();
                status = "Online: you are VOLT. Host can press R for a rematch.";
            } else if (!IsHost && id == manager.LocalClientId) {
                status = "Connected: you are EMBER. Waiting for match state...";
                lastState = Time.realtimeSinceStartup;
            }
        }
        void Disconnected(ulong id)
        {
            if (stopping || !Online) return;
            if (!IsHost || id == guest) Stop("Player disconnected. Host a new room to play again.");
        }
        public void Stop(string message = "Disconnected")
        {
            if (stopping) return;
            stopping = true; ++generation; Online = Ready = busy = false; code = ""; pendingPresses = 0;
            RemoteInput.Clear(); local?.ClearBuffer();
            if (manager != null) { manager.Shutdown(); Destroy(manager.gameObject); manager = null; }
            status = message; if (game != null) game.EndOnlineMatch(); stopping = false;
        }
        void OnDestroy() { game = null; Stop(); }

        public void PollClient()
        {
            if (!Online || manager == null || IsHost) return;
            if (!manager.IsConnectedClient) {
                if (!busy && Time.realtimeSinceStartup - started > 20) Stop("Join timed out. Check the code and try again.");
                return;
            }
            if (Time.realtimeSinceStartup - lastState > 10) { Stop("Host stopped responding."); return; }
            local.Poll(); byte held = 0;
            for (int i = 0; i < 7; i++) {
                if (local.Held((FAction)i)) held |= (byte)(1 << i);
                if (local.Pressed((FAction)i)) pendingPresses |= (byte)(1 << i);
            }
            if (smoke && Ready) {
                held = game.P2.X > game.P1.X + 1 ? (byte)1 : (byte)0;
                if(held == 0 && Time.frameCount % 12 == 0) pendingPresses |= (byte)(1 << (int)FAction.Punch);
            }
            if (Time.unscaledTime < nextInput) return;
            nextInput = Time.unscaledTime + 1f / 30;
            using var writer = new FastBufferWriter(2, Allocator.Temp);
            writer.WriteValueSafe(held); writer.WriteValueSafe(pendingPresses);
            manager.CustomMessagingManager.SendNamedMessage(InputMessage, NetworkManager.ServerClientId, writer, NetworkDelivery.ReliableSequenced);
            pendingPresses = 0;
        }
        void ReceiveInput(ulong sender, FastBufferReader reader)
        {
            if (!IsHost || !Ready || sender != guest) return;
            if (reader.Length - reader.Position < 2) return;
            reader.ReadValueSafe(out byte held); reader.ReadValueSafe(out byte pressed);
            RemoteInput.Set(held, pressed);
        }
        void ReceiveState(ulong sender, FastBufferReader reader)
        {
            if (IsHost || !Online || sender != NetworkManager.ServerClientId || reader.Length > 32000) return;
            reader.ReadValueSafe(out string json);
            var state = JsonUtility.FromJson<MatchSnapshot>(json);
            if (state == null || state.fighters == null || state.fighters.Length != 2) return;
            game.ApplySnapshot(state); Ready = true; lastState = Time.realtimeSinceStartup;
            status = "Online: you are EMBER. Use A/D, W, S, J/K/L or a controller.";
        }
        void LateUpdate()
        {
            if (!Online || !Ready || !IsHost || Time.unscaledTime < nextState) return;
            nextState = Time.unscaledTime + 1f / 30;
            string json = JsonUtility.ToJson(game.CaptureSnapshot());
            using var writer = new FastBufferWriter(32000, Allocator.Temp);
            writer.WriteValueSafe(json);
            manager.CustomMessagingManager.SendNamedMessage(StateMessage, guest, writer, NetworkDelivery.ReliableFragmentedSequenced);
        }
        void OnGUI()
        {
            float width = Mathf.Min(440, Screen.width - 24);
            GUILayout.BeginArea(new Rect(12, 130, width, 220), GUI.skin.box);
            GUILayout.Label("ONLINE VERSUS"); GUILayout.Label(status);
            GUI.enabled = !busy && (manager == null || !manager.ShutdownInProgress);
            if (!Online) {
                GUILayout.BeginHorizontal();
                if (GUILayout.Button("Host Game", GUILayout.Height(30))) Connect(true);
                joinText = GUILayout.TextField(joinText, 12, GUILayout.Width(100));
                if (GUILayout.Button("Join Code", GUILayout.Height(30))) Connect(false);
                GUILayout.EndHorizontal();
            } else {
                if (!string.IsNullOrEmpty(code)) { GUILayout.Label("Join code: " + code); if (GUILayout.Button("Copy code")) GUIUtility.systemCopyBuffer = code; }
                if (GUILayout.Button("Leave room")) Stop();
            }
            GUI.enabled = true; GUILayout.EndArea();
        }
    }

    public sealed class RemoteFighterInput : IFighterInput
    {
        byte held; float received;
        readonly float[] presses = new float[7];
        public RemoteFighterInput() { Clear(); }
        public void Clear() { held = 0; for (int i = 0; i < 7; i++) presses[i] = -100; }
        public void Set(byte h, byte p) { held = (byte)(h & 127); received = Time.unscaledTime; for (int i = 0; i < 7; i++) if ((p & (1 << i)) != 0) presses[i] = received; }
        public bool Held(FAction a) => Time.unscaledTime - received < .5f && (held & (1 << (int)a)) != 0;
        public bool Pressed(FAction a) { int i = (int)a; bool yes = Time.unscaledTime - presses[i] < .15f; presses[i] = -100; return yes; }
    }
    [Serializable] public class FighterSnapshot { public float x,y,vx,vy,hp,lag,meter,t,comboT,flash; public int facing,state,combo,move; }
    [Serializable] public class OrbSnapshot { public float x,y; public int owner,dir; }
    [Serializable] public class MatchSnapshot {
        public FighterSnapshot[] fighters; public OrbSnapshot[] orbs;
        public int phase,round,w1,w2,comboOwner; public float timer,clock,comboHide;
        public string text,sub; public Color color;
    }
}







