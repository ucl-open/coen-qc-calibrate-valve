using Bonsai;
using Harp.Behavior;
using OpenRigs.Core;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reactive.Linq;
using YamlDotNet.RepresentationModel;

// The valve calibration's rig model (plan v11, W1): what it reads from this machine's rig.yml, read
// untyped, so one workflow serves the domes, the behaviour boxes and the arena, and a key it does
// not read is never refused. It needs only the board's port and its RewardValve lines in wiring
// (not the dome's ZapitTrigger), and the lick spout stage's two drivers when the rig has one.
// Compiled by Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    /// <summary>A lick spout stage driver's rig.yml entry, as HarpLickSpoutStage maps it (Settings.PortName).</summary>
    public class StageDriverSettings
    {
        /// <summary>The driver's serial port.</summary>
        public string PortName { get; set; }
    }

    /// <summary>What the valve calibration takes from rig.yml.</summary>
    public class ValveRig
    {
        /// <summary>Where every refusal's rule lives.</summary>
        public const string Where = "(valve calibration rig model, coen-qc-calibrate-valve src\\Extensions\\ValveRig.cs)";

        /// <summary>The path of rig.yml.</summary>
        public string RigFile { get; set; }

        /// <summary>behaviorBoard: main: portName.</summary>
        public string PortName { get; set; }

        /// <summary>The DO lines wiring gives a RewardValve, 1 to 3, in line order.</summary>
        public int[] Valves { get; set; }

        /// <summary>The valve lines, as the PulseController pulses them: nothing else on the board is pulsed.</summary>
        public DigitalOutputs OutputPulseEnable
        {
            get
            {
                var lines = default(DigitalOutputs);
                foreach (var valve in Valves) lines |= (DigitalOutputs)Enum.Parse(typeof(DigitalOutputs), "DO" + valve);
                return lines;
            }
        }

        /// <summary>Whether rig.yml has a lick spout stage (stepperDriver: a: and b:).</summary>
        public bool HasStage { get; set; }

        /// <summary>The stage's first driver, StepperDriver-A; null without a stage.</summary>
        public NamedDevice<StageDriverSettings> StepperDriverA { get; set; }

        /// <summary>The stage's second driver, StepperDriver-B; null without a stage.</summary>
        public NamedDevice<StageDriverSettings> StepperDriverB { get; set; }

        /// <summary>Refuses any line that is not one of rig.yml's RewardValves.</summary>
        public void Check(int[] lines)
        {
            foreach (var line in lines)
            {
                if (!Valves.Contains(line))
                {
                    throw new InvalidOperationException(string.Format(
                        "DO{0} is not a reward valve: rig.yml's behaviorBoard: main: wiring gives RewardValve only to {1} {2}.",
                        line, string.Join(", ", Valves.Select(v => "DO" + v).ToArray()), Where));
                }
            }
        }

        /// <summary>Reads rig.yml, or throws naming what is missing.</summary>
        public static ValveRig Read(string rigFile)
        {
            if (!File.Exists(rigFile)) throw new FileNotFoundException("No rig.yml at " + rigFile + " " + Where, rigFile);
            var yaml = new YamlStream();
            using (var reader = new StreamReader(rigFile)) yaml.Load(reader);
            var root = yaml.Documents.Count > 0 ? yaml.Documents[0].RootNode as YamlMappingNode : null;
            var board = Child(Child(root, "behaviorBoard"), "main") as YamlMappingNode;
            if (board == null) throw new InvalidOperationException(rigFile + " has no behaviorBoard: main:, the board whose valves are calibrated " + Where);

            var rig = new ValveRig { RigFile = rigFile, PortName = Value(Child(board, "portName")) };
            if (string.IsNullOrEmpty(rig.PortName)) throw new InvalidOperationException(rigFile + " gives no behaviorBoard: main: portName " + Where);

            var valves = new List<int>();
            var wiring = Child(board, "wiring") as YamlMappingNode;
            if (wiring != null)
            {
                foreach (var entry in wiring.Children)
                {
                    if (Value(Child(entry.Value, "device")) != "RewardValve") continue;
                    var name = Value(entry.Key) ?? "";
                    int line;
                    if (!name.StartsWith("DO", StringComparison.Ordinal) || !int.TryParse(name.Substring(2), NumberStyles.None, CultureInfo.InvariantCulture, out line) || line < 1 || line > 3)
                    {
                        throw new InvalidOperationException(string.Format("{0}'s wiring puts a RewardValve on {1}; a RewardValve goes on DO1, DO2 or DO3 {2}", rigFile, name, Where));
                    }
                    valves.Add(line);
                }
            }
            if (valves.Count == 0)
            {
                throw new InvalidOperationException(rigFile + "'s behaviorBoard: main: wiring has no RewardValve, so there is no valve to calibrate: add each valve's line, such as DO1: { device: RewardValve, side: left } " + Where);
            }
            valves.Sort();
            rig.Valves = valves.ToArray();

            var drivers = Child(root, "stepperDriver") as YamlMappingNode;
            if (drivers != null && drivers.Children.Count > 0)
            {
                rig.HasStage = true;
                rig.StepperDriverA = Driver(rigFile, drivers, "a");
                rig.StepperDriverB = Driver(rigFile, drivers, "b");
            }
            return rig;
        }

        static NamedDevice<StageDriverSettings> Driver(string rigFile, YamlMappingNode drivers, string entry)
        {
            var port = Value(Child(Child(drivers, entry), "portName"));
            if (string.IsNullOrEmpty(port))
            {
                throw new InvalidOperationException(string.Format(
                    "{0} has a stepperDriver section but no stepperDriver: {1}: portName; a lick spout stage is stepperDriver: a: and b: {2}", rigFile, entry, Where));
            }
            return new NamedDevice<StageDriverSettings>("StepperDriver-" + entry.ToUpperInvariant(), new StageDriverSettings { PortName = port });
        }

        static YamlNode Child(YamlNode node, string key)
        {
            var map = node as YamlMappingNode;
            YamlNode child;
            return map != null && map.Children.TryGetValue(new YamlScalarNode(key), out child) ? child : null;
        }

        static string Value(YamlNode node)
        {
            var scalar = node as YamlScalarNode;
            if (scalar == null || string.IsNullOrWhiteSpace(scalar.Value)) return null;
            var text = scalar.Value.Trim();
            return text == "~" || text.Equals("null", StringComparison.OrdinalIgnoreCase) ? null : text;
        }
    }

    [Combinator]
    [Description("Reads <RigConfigDirectory>\\rig.yml for the valve calibration: the board's port, its RewardValve lines from wiring and, when it has one, the lick spout stage's two drivers. Stops the workflow, saying what is missing, if rig.yml has no board, no port or no RewardValve.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ReadValveRig
    {
        public IObservable<ValveRig> Process(IObservable<string> source)
        {
            return source.Select(directory => ValveRig.Read(Path.Combine(directory, "rig.yml")));
        }
    }
}
