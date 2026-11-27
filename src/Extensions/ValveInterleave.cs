using Bonsai;
using OpenRigs.Core.Calibration;
using OpenRigs.Devices;
using OpenRigs.Devices.Rigs;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using System.Reactive.Linq;

// Calibrating every valve in one run, interleaved (Pip, 7 Nov 2026: "an option to calibrate all
// valves (interleave left and right for each burst, obviously double number of calibrations) or each
// individual valve"). One container on one balance under every spout: each burst is weighed by
// difference before the next valve fires, so each valve's gain is its own.
//
// A valve is named by its piece, RewardValve-Left, and found on its board and line by lib-open-rigs'
// WiredRewardValve, as LabRig.reward_valves() finds it in Python. The procedure is expanded once, at
// load, so everything that follows the bursts (OpenRigs.Devices ManualBalance, which counts the pulses
// fired; RunCalibration; the weights file) sees one sample per valve per burst, in the order they fire.
// Every burst is a PulseTrain for OpenRigs.Core FirePulses, which fires it on the Harp clock at the
// procedure's one pulseGapMs, the gap a rig then fires its rewards at. Compiled by Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    /// <summary>A sample of the expanded procedure: the procedure's own, on one valve.</summary>
    public class ValveSample : DispenseSample
    {
        /// <summary>The valve this burst fires, such as RewardValve-Left.</summary>
        public string Valve { get; set; }

        /// <summary>The behavior board line the valve is wired on, such as DO1.</summary>
        public string Line { get; set; }
    }

    /// <summary>One train of pulses, mapped onto OpenRigs.Core FirePulses' properties (InputMapping).</summary>
    public class PulseTrain
    {
        public string Line { get; set; }
        public int PulseWidthMs { get; set; }
        public int Pulses { get; set; }
        public int PulseGapMs { get; set; }

        public static PulseTrain Of(DispenseSample sample, int count)
        {
            return new PulseTrain { Line = Valves.Sample(sample).Line, PulseWidthMs = sample.PulseWidthMs, Pulses = count, PulseGapMs = sample.PulseGapMs };
        }
    }

    /// <summary>The valves of a run, from the Valves launch property or, when that is empty, Valve.</summary>
    public static class Valves
    {
        /// <summary>The one board the workflow fires valves through: a valve wired on another stops it.</summary>
        public const string Board = "BehaviorBoard-Main";

        /// <summary>A valve's wiring on Board, by its piece name (RewardValve-Left); refuses one rig.yml does not wire there.</summary>
        public static RewardValveWiring Find(LabRig rig, string valve)
        {
            return WiredRewardValve.Find(rig, (valve ?? "").Trim(), Board);
        }

        /// <summary>The valves named in `valves` (comma or space separated), or the one `valve` when that is empty.</summary>
        public static RewardValveWiring[] Parse(LabRig rig, string valves, string valve)
        {
            var parts = (valves ?? "").Split(new[] { ',', ' ', ';' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0) return new[] { Find(rig, valve) };
            var parsed = new List<RewardValveWiring>();
            foreach (var part in parts)
            {
                RewardValveWiring wired;
                try { wired = Find(rig, part); }
                catch (Exception error)
                {
                    throw new InvalidOperationException(string.Format("Valves '{0}': {1}", valves, error.Message));
                }
                if (parsed.Any(v => v.Valve == wired.Valve))
                {
                    throw new InvalidOperationException(string.Format("Valves '{0}' names {1} twice.", valves, wired.Valve));
                }
                parsed.Add(wired);
            }
            return parsed.ToArray();
        }

        /// <summary>A sample of the expanded procedure; refuses one that names no valve.</summary>
        public static ValveSample Sample(DispenseSample sample)
        {
            var valve = sample as ValveSample;
            if (valve == null) throw new InvalidOperationException("A sample names no valve: the procedure was not expanded over the valves (InterleaveValves).");
            return valve;
        }

        /// <summary>The valves of an expanded procedure, in the order they fire.</summary>
        public static ValveSample[] Of(DispenseProcedure procedure)
        {
            var found = new List<ValveSample>();
            foreach (var sample in procedure.Samples)
            {
                var valve = sample as ValveSample;
                if (valve != null && !found.Any(v => v.Valve == valve.Valve)) found.Add(valve);
            }
            return found.ToArray();
        }

        /// <summary>The procedure's one pulseGapMs; refuses samples at different gaps, since the
        /// calibration file records one and a rig fires every reward at it.</summary>
        public static int Gap(DispenseProcedure procedure)
        {
            var gaps = procedure.Samples.Select(sample => sample.PulseGapMs).Distinct().OrderBy(gap => gap).ToArray();
            if (gaps.Length != 1)
            {
                throw new InvalidOperationException(string.Format(
                    "config\\valve-calibration.yml's samples are fired at {0} gaps ({1} ms); give every sample one pulseGapMs, the gap a rig fires its rewards at.",
                    gaps.Length, string.Join(", ", gaps.Select(gap => gap.ToString(CultureInfo.InvariantCulture)).ToArray())));
            }
            return gaps[0];
        }
    }

    [Combinator]
    [Description("Expands the valve calibration's procedure over the valves to calibrate: each round (each width's first sample, then each width's second, ...) in a new random order every run, each sample once per valve, in turn (RewardValve-Left's burst, weighed, then RewardValve-Right's, weighed, and so on), and the priming pulses once per valve. Valves lists them by piece name (RewardValve-Left, RewardValve-Right); empty, the one Valve. Input: (the settings, the lab rig model, RigConfigs); stops the workflow if a valve is not wired on BehaviorBoard-Main or the samples are at different pulseGapMs.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class InterleaveValves
    {
        string valve = "RewardValve-Left";
        string valves = "";

        [Description("The one valve to calibrate, by its piece name, such as RewardValve-Left, when Valves is empty.")]
        public string Valve
        {
            get { return valve; }
            set { valve = value; }
        }

        [Description("The valves to calibrate together, interleaved, such as RewardValve-Left, RewardValve-Right. Empty: only Valve.")]
        public string Valves
        {
            get { return valves; }
            set { valves = value; }
        }

        public IObservable<DispenseCalibration> Process(IObservable<Tuple<DispenseCalibration, LabRig>> source)
        {
            return source.Select(input => Expand(input.Item1, CoenQcCalibrateValve.Valves.Parse(input.Item2, Valves, Valve), new Random()));
        }

        /// <summary>The settings with each sample once per valve, in turn, and the priming pulses once per valve.
        /// With `random`, each round is shuffled first (Pip, 11 Nov 2026: "Shuffle every round"): round k holds
        /// each width's k-th sample, the rounds stay in turn, and a new order is drawn every run. Without it,
        /// the samples as written.</summary>
        public static DispenseCalibration Expand(DispenseCalibration settings, RewardValveWiring[] valves, Random random)
        {
            var procedure = settings.Procedure;
            if (procedure == null || procedure.Samples == null || procedure.Samples.Count == 0)
            {
                throw new InvalidOperationException("The valve calibration's procedure has no samples.");
            }
            CoenQcCalibrateValve.Valves.Gap(procedure);
            var expanded = new List<DispenseSample>();
            foreach (var sample in random == null ? procedure.Samples : Shuffled(procedure.Samples, random))
            {
                foreach (var wired in valves)
                {
                    expanded.Add(new ValveSample
                    {
                        PulseWidthMs = sample.PulseWidthMs,
                        Pulses = sample.Pulses,
                        PulseGapMs = sample.PulseGapMs,
                        Valve = wired.Valve,
                        Line = wired.Line.ToString()
                    });
                }
            }
            procedure.Samples = expanded;
            // ManualBalance counts the priming pulses as one burst: every valve's.
            procedure.PrimingPulses = procedure.PrimingPulses * valves.Length;
            return settings;
        }

        /// <summary>The samples by round (each width's first, then each width's second, ...), each round shuffled.</summary>
        public static List<DispenseSample> Shuffled(IList<DispenseSample> samples, Random random)
        {
            var seen = new Dictionary<int, int>();
            var rounds = new List<List<DispenseSample>>();
            foreach (var sample in samples)
            {
                int round;
                seen.TryGetValue(sample.PulseWidthMs, out round);
                seen[sample.PulseWidthMs] = round + 1;
                while (rounds.Count <= round) rounds.Add(new List<DispenseSample>());
                rounds[round].Add(sample);
            }
            var order = new List<DispenseSample>();
            foreach (var round in rounds)
            {
                for (int i = round.Count - 1; i > 0; i--)
                {
                    int j = random.Next(i + 1);
                    var swap = round[i]; round[i] = round[j]; round[j] = swap;
                }
                order.AddRange(round);
            }
            return order;
        }
    }

    [Combinator]
    [Description("Each sample of the expanded procedure as its burst: its pulses at its width on its valve, at its pulseGapMs. Fed the procedure, the priming bursts: an equal share of the priming pulses on each valve in turn, at the priming pulse width and the procedure's pulseGapMs.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ValveTrains
    {
        public IObservable<PulseTrain> Process(IObservable<DispenseSample> source)
        {
            return source.Select(sample => PulseTrain.Of(sample, sample.Pulses));
        }

        public IObservable<PulseTrain> Process(IObservable<DispenseProcedure> source)
        {
            return source.SelectMany(procedure => Priming(procedure));
        }

        public static PulseTrain[] Priming(DispenseProcedure procedure)
        {
            if (procedure.Samples == null || procedure.Samples.Count == 0)
            {
                throw new InvalidOperationException("The dispense procedure has no samples to take the priming pulse width from.");
            }
            var valves = Valves.Of(procedure);
            if (valves.Length == 0) throw new InvalidOperationException("The dispense procedure names no valve: it was not expanded over the valves (InterleaveValves).");
            int width = procedure.PrimingPulseWidthMs ?? procedure.Samples.Max(sample => sample.PulseWidthMs);
            int gap = Valves.Gap(procedure);
            int each = procedure.PrimingPulses / valves.Length;
            return valves.Select(valve => new PulseTrain { Line = valve.Line, PulseWidthMs = width, Pulses = each, PulseGapMs = gap }).ToArray();
        }
    }

    // Drips (Pip, 8 Nov 2026): a drop can hang on the spout after a burst and fall into the next
    // weighing, so once a weight is due app-rig-control fires short bursts of the width tested, one Drip
    // command at a time, until the balance's display moves, and only then reads it. A sample's drip
    // pulses are its own: they are added to its row's pulses.
    [Combinator]
    [Description("Each Drip command as a burst: its text is the pulse count and, for the baseline, the valve (such as '1 RewardValve-Right'). With a sample (second input), at the sample's width on its valve; with the procedure, at its largest sample's width on the valve named, else its first valve. At the procedure's pulseGapMs. Third input: the lab rig model (RigConfigs); stops the workflow if the valve named is not wired on BehaviorBoard-Main.")]
    [WorkflowElementCategory(ElementCategory.Combinator)]
    public class DripTrains
    {
        public IObservable<PulseTrain> Process(IObservable<string> commands, IObservable<DispenseSample> sample, IObservable<LabRig> rig)
        {
            return sample.Take(1).SelectMany(s => commands.Select(text => PulseTrain.Of(s, Parse(text).Item1)));
        }

        public IObservable<PulseTrain> Process(IObservable<string> commands, IObservable<DispenseProcedure> procedure, IObservable<LabRig> rig)
        {
            return procedure.Take(1).SelectMany(p => rig.Take(1).SelectMany(wired => commands.Select(text =>
            {
                var drip = Parse(text);
                var valves = Valves.Of(p);
                string line;
                if (drip.Item2 != null) line = Valves.Find(wired, drip.Item2).Line.ToString();
                else if (valves.Length > 0) line = valves[0].Line;
                else throw new InvalidOperationException(string.Format("Drip '{0}' names no valve, and the procedure has none.", text));
                return new PulseTrain { Line = line, PulseWidthMs = p.Samples.Max(x => x.PulseWidthMs), Pulses = drip.Item1, PulseGapMs = Valves.Gap(p) };
            })));
        }

        /// <summary>A Drip command's (pulses, valve), the valve null when not named.</summary>
        public static Tuple<int, string> Parse(string text)
        {
            var parts = (text ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            int pulses;
            if (parts.Length < 1 || parts.Length > 2 || !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out pulses)
                || pulses < 1 || pulses > 100)
            {
                throw new InvalidOperationException(string.Format(
                    "Drip '{0}' is not a drip: give its pulses, 1 to 100, and for the baseline the valve, such as 1 RewardValve-Right.", text));
            }
            return Tuple.Create(pulses, parts.Length == 2 ? parts[1] : null);
        }
    }

    // A minimum width per rig (Pip, 12 Nov 2026: "set different min/max of calibration on different
    // rigs"; "Max opening should be 5 x min, so all just scale"): the procedure's widths are written
    // for a 20 ms minimum and scaled at Go to the task file's minPulseWidthMs; the pulses stay as written.
    [Combinator]
    [Description("The procedure's widths scaled at Go so the smallest is MinPulseWidthMs, each times MinPulseWidthMs over the smallest written, rounded half away from zero; pulses, gaps and priming as written. Input: (MinPulseWidthMs as text, the settings). In place, and idempotent, so every subscriber of the settings scales them alike.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ScaleWidths
    {
        public const int Lowest = 5, Highest = 100;

        public IObservable<DispenseCalibration> Process(IObservable<Tuple<string, DispenseCalibration>> source)
        {
            return source.Select(input => Scale(input.Item2, ParseMin(input.Item1)));
        }

        public static int ParseMin(string text)
        {
            int min;
            if (!int.TryParse((text ?? "").Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out min) || min < Lowest || min > Highest)
            {
                throw new InvalidOperationException(string.Format(
                    "MinPulseWidthMs '{0}' is not a minimum width: give whole ms, {1} to {2}.", text, Lowest, Highest));
            }
            return min;
        }

        public static DispenseCalibration Scale(DispenseCalibration settings, int min)
        {
            var samples = settings.Procedure.Samples;
            int smallest = samples.Min(sample => sample.PulseWidthMs);
            foreach (var sample in samples)
            {
                sample.PulseWidthMs = (int)Math.Round((double)(sample.PulseWidthMs * min) / smallest, MidpointRounding.AwayFromZero);
            }
            return settings;
        }
    }

    // Testing a width before Start (Pip, 12 Nov 2026: "test the min opening time in the calibration
    // window before starting (and then can edit)"): pulses on BehaviorBoard-Main.TriggerCalibratedPulse alone, never on
    // BurstPulses, so ManualBalance does not count them.
    [Combinator]
    [Description("Each Test command as a burst: its text is the width in ms, the pulses and the valve, such as '20 10 RewardValve-Left', at the procedure's pulseGapMs. Input: ((the command's text, the settings), the lab rig model, RigConfigs); stops the workflow if the valve is not wired on BehaviorBoard-Main.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class TestTrain
    {
        public IObservable<PulseTrain> Process(IObservable<Tuple<Tuple<string, DispenseCalibration>, LabRig>> source)
        {
            return source.Select(input =>
            {
                var test = Parse(input.Item1.Item1);
                var line = Valves.Find(input.Item2, test.Item3).Line.ToString();
                return new PulseTrain { Line = line, PulseWidthMs = test.Item1, Pulses = test.Item2, PulseGapMs = Valves.Gap(input.Item1.Item2.Procedure) };
            });
        }

        /// <summary>A Test command's (width ms, pulses, valve).</summary>
        public static Tuple<int, int, string> Parse(string text)
        {
            var parts = (text ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            int width, pulses;
            if (parts.Length != 3
                || !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out width) || width < 1 || width > 5 * ScaleWidths.Highest
                || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out pulses) || pulses < 1 || pulses > 100)
            {
                throw new InvalidOperationException(string.Format(
                    "Test '{0}' is not a test: give the width in ms (1 to {1}), the pulses (1 to 100) and the valve, such as 20 10 RewardValve-Left.", text, 5 * ScaleWidths.Highest));
            }
            return Tuple.Create(width, pulses, parts[2]);
        }
    }

    [Combinator]
    [Description("The valves of the expanded procedure as the run's target says them, such as RewardValve-Left, RewardValve-Right.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class DescribeValves
    {
        public IObservable<string> Process(IObservable<DispenseCalibration> source)
        {
            return source.Select(settings => string.Join(", ", Valves.Of(settings.Procedure).Select(v => v.Valve).ToArray()));
        }
    }

    /// <summary>One row of the weights file, its columns camelCase with their units (lib-open-rigs specs\logging.md).</summary>
    public class ValveWeighing
    {
        public double pulseWidthMs { get; set; }
        public int pulses { get; set; }
        public double beforeG { get; set; }
        public double afterG { get; set; }
        public string valve { get; set; }
        public int pulseGapMs { get; set; }
    }

    [Combinator]
    [Description("Each weighed burst as a row of the weights file: its pulse width in ms, its pulses (its drips included), the grams before and after it, the valve it fired (RewardValve-Left) and its pulseGapMs. Input: (((grams after, grams before), its sample), its drip pulses), RunCalibration's output with SampleDrips.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ValveWeighingRow
    {
        public IObservable<ValveWeighing> Process(IObservable<Tuple<Tuple<Tuple<double, double>, DispenseSample>, int>> source)
        {
            return source.Select(input =>
            {
                var weighed = input.Item1;
                return new ValveWeighing
                {
                    pulseWidthMs = weighed.Item2.PulseWidthMs,
                    pulses = weighed.Item2.Pulses + input.Item2,
                    beforeG = weighed.Item1.Item2,
                    afterG = weighed.Item1.Item1,
                    valve = Valves.Sample(weighed.Item2).Valve,
                    pulseGapMs = weighed.Item2.PulseGapMs
                };
            });
        }
    }
}
