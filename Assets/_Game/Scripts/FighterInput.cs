using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace FightingGame
{
    public enum FAction { Left, Right, Jump, Block, Punch, Kick, Special }

    public interface IFighterInput
    {
        bool Held(FAction a);
        /// <summary>True once per press; presses are buffered briefly so they survive hitstop.</summary>
        bool Pressed(FAction a);
    }

    public sealed class NoInput : IFighterInput
    {
        public static readonly NoInput Instance = new NoInput();
        public bool Held(FAction a) => false;
        public bool Pressed(FAction a) => false;
    }

    /// <summary>Keyboard controls for P1 or P2. P1 also accepts the first gamepad.</summary>
    public sealed class HumanInput : IFighterInput
    {
        const float BufferTime = 0.15f;
        const int ActionCount = 7;

        static readonly Key[][] P1Keys =
        {
            new[] { Key.A }, new[] { Key.D }, new[] { Key.W, Key.Space }, new[] { Key.S },
            new[] { Key.J }, new[] { Key.K }, new[] { Key.L },
        };
        static readonly Key[][] P2Keys =
        {
            new[] { Key.LeftArrow }, new[] { Key.RightArrow }, new[] { Key.UpArrow }, new[] { Key.DownArrow },
            new[] { Key.Comma, Key.Numpad1 }, new[] { Key.Period, Key.Numpad2 }, new[] { Key.Slash, Key.Numpad3 },
        };

        readonly Key[][] keys;
        readonly bool useGamepad;
        readonly float[] pressTime = new float[ActionCount];

        public HumanInput(bool player1)
        {
            keys = player1 ? P1Keys : P2Keys;
            useGamepad = player1;
            for (int i = 0; i < ActionCount; i++) pressTime[i] = -1;
        }

        /// <summary>Call every rendered frame so no press is missed.</summary>
        public void Poll()
        {
            for (int i = 0; i < ActionCount; i++)
                if (Check(i, pressed: true)) pressTime[i] = Time.unscaledTime;
        }

        public bool Held(FAction a) => Check((int)a, pressed: false);

        public bool Pressed(FAction a)
        {
            int i = (int)a;
            if (pressTime[i] >= 0 && Time.unscaledTime - pressTime[i] < BufferTime)
            {
                pressTime[i] = -1;
                return true;
            }
            return false;
        }

        public void ClearBuffer()
        {
            for (int i = 0; i < ActionCount; i++) pressTime[i] = -1;
        }

        bool Check(int i, bool pressed)
        {
            var kb = Keyboard.current;
            if (kb != null)
                foreach (var k in keys[i])
                    if (pressed ? kb[k].wasPressedThisFrame : kb[k].isPressed) return true;

            var gp = useGamepad ? Gamepad.current : null;
            if (gp != null)
                foreach (var b in PadButtons(gp, (FAction)i))
                    if (pressed ? b.wasPressedThisFrame : b.isPressed) return true;
            return false;
        }

        static ButtonControl[] PadButtons(Gamepad g, FAction a) => a switch
        {
            FAction.Left => new[] { g.dpad.left, g.leftStick.left },
            FAction.Right => new[] { g.dpad.right, g.leftStick.right },
            FAction.Jump => new[] { g.buttonSouth, g.dpad.up },
            FAction.Block => new[] { g.leftShoulder, g.rightShoulder },
            FAction.Punch => new[] { g.buttonWest },
            FAction.Kick => new[] { g.buttonNorth },
            _ => new[] { g.buttonEast },
        };
    }
}
